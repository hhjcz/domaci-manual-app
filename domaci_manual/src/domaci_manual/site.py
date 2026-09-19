"""Turn the Markdown checkout into a static MkDocs Material site.

The documentation repository is a plain Markdown knowledge base; it owns no
MkDocs files. This module generates the whole MkDocs configuration, so the same
repository stays readable in GitHub, Obsidian or any Markdown viewer.

Navigation is MkDocs' own automatic nav, derived from the directory tree. That
is one less thing to maintain than a hand-rolled nav builder, and it already
does the right thing: ``README.md`` or ``index.md`` becomes a section index,
page titles come from the first heading.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
import sys
from pathlib import Path

import yaml

from .config import Options, Paths

_LOGGER = logging.getLogger(__name__)

_ANSI = re.compile(r"\x1b\[[0-9;]*m")

OVERRIDES_DIR = Path(__file__).parent / "web" / "overrides"

# Written into the docs root when the repository has no landing page, so the
# ingress entry point always resolves to a real page.
GENERATED_INDEX = "generated-index.md"
GENERATED_INDEX_BODY = """# {site_name}

This documentation repository has no `README.md` or `index.md` in its root, so
this page was generated automatically.

Use the navigation to browse the documentation. Add a `README.md` to the
repository root to replace this page.
"""

ROOT_INDEX_CANDIDATES = ("index.md", "README.md", "readme.md", "index.markdown")


class BuildError(Exception):
    def __init__(self, message: str, output: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.output = output

    @property
    def detail(self) -> str:
        return self.output.strip()


def mkdocs_config(options: Options, docs_dir: Path, site_dir: Path) -> dict:
    """The full MkDocs configuration, as a plain dict.

    Deliberately no ``site_url``: every generated URL stays relative, which is
    what makes the site work under the dynamic Home Assistant ingress prefix.
    """
    return {
        "site_name": options.site_name,
        "docs_dir": str(docs_dir),
        "site_dir": str(site_dir),
        "use_directory_urls": True,
        "strict": False,
        # gitignore-style patterns, applied to paths relative to docs_dir.
        # Excluded files are left out of the site entirely, so they are neither
        # linkable nor searchable.
        "exclude_docs": "\n".join(options.exclude),
        # Broken links are common in a hand-written knowledge base; warn, never
        # fail the build over them.
        "validation": {
            "links": {
                "not_found": "warn",
                "absolute_links": "ignore",
                "unrecognized_links": "warn",
            },
            "nav": {"omitted_files": "info", "not_found": "warn"},
        },
        "theme": {
            "name": "material",
            "custom_dir": str(OVERRIDES_DIR),
            "language": options.language,
            # Material otherwise pulls webfonts from Google on every page load:
            # unwanted for a private household manual, and broken offline.
            "font": False,
            "features": [
                "navigation.indexes",
                "navigation.top",
                "navigation.tracking",
                "search.highlight",
                "search.suggest",
                "content.code.copy",
                "toc.follow",
            ],
            "palette": [
                {
                    "media": "(prefers-color-scheme: light)",
                    "scheme": "default",
                    "primary": "indigo",
                    "accent": "indigo",
                    "toggle": {
                        "icon": "material/weather-night",
                        "name": "Switch to dark mode",
                    },
                },
                {
                    "media": "(prefers-color-scheme: dark)",
                    "scheme": "slate",
                    "primary": "indigo",
                    "accent": "indigo",
                    "toggle": {
                        "icon": "material/weather-sunny",
                        "name": "Switch to light mode",
                    },
                },
            ],
            "icon": {"repo": "fontawesome/brands/git-alt"},
        },
        "plugins": ["search"],
        "markdown_extensions": [
            "abbr",
            "admonition",
            "attr_list",
            "def_list",
            "footnotes",
            "md_in_html",
            "tables",
            {"toc": {"permalink": True}},
            "pymdownx.caret",
            "pymdownx.details",
            {"pymdownx.highlight": {"anchor_linenums": True}},
            "pymdownx.inlinehilite",
            "pymdownx.keys",
            # Obsidian's ==highlight== syntax.
            "pymdownx.mark",
            "pymdownx.smartsymbols",
            "pymdownx.superfences",
            {"pymdownx.tasklist": {"custom_checkbox": True}},
            "pymdownx.tilde",
        ],
    }


def write_config(options: Options, paths: Paths, docs_dir: Path, site_dir: Path) -> Path:
    config = mkdocs_config(options, docs_dir, site_dir)
    paths.mkdocs_config.write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    return paths.mkdocs_config


def ensure_landing_page(options: Options, docs_dir: Path) -> None:
    """Guarantee the site has a root page for the ingress entry point."""
    if any((docs_dir / name).is_file() for name in ROOT_INDEX_CANDIDATES):
        (docs_dir / GENERATED_INDEX).unlink(missing_ok=True)
        return
    _LOGGER.info("Repository has no root README.md; generating a landing page")
    (docs_dir / "index.md").write_text(
        GENERATED_INDEX_BODY.format(site_name=options.site_name), encoding="utf-8"
    )


def count_markdown_files(docs_dir: Path) -> int:
    return sum(
        1
        for path in docs_dir.rglob("*.md")
        # MkDocs skips dot-directories; do not count them either.
        if not any(part.startswith(".") for part in path.relative_to(docs_dir).parts)
    )


async def build(options: Options, paths: Paths, docs_dir: Path) -> Path:
    """Build the site into a fresh directory and return it.

    Each build lands in its own ``site/gen-N`` directory and only becomes
    visible once it is complete, so a failed build never replaces a working
    site with a broken one.
    """
    if not docs_dir.is_dir():
        raise BuildError(f"Documentation directory {docs_dir} does not exist.")
    if count_markdown_files(docs_dir) == 0:
        raise BuildError(
            f"No Markdown files found in {docs_dir}. Check the 'repository', "
            "'branch' and 'docs_subdir' options."
        )

    ensure_landing_page(options, docs_dir)

    staging = paths.site_root / "next"
    if staging.exists():
        shutil.rmtree(staging)

    config_file = write_config(options, paths, docs_dir, staging)
    _LOGGER.info("Building documentation from %s", docs_dir)

    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m", "mkdocs",
        "build",
        "--config-file", str(config_file),
        "--site-dir", str(staging),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    output, _ = await process.communicate()
    text = output.decode("utf-8", "replace")
    if process.returncode != 0:
        raise BuildError("MkDocs failed to build the documentation.", output=text)
    for line in text.splitlines():
        stripped = _ANSI.sub("", line).rstrip()
        if stripped:
            _LOGGER.debug("mkdocs: %s", stripped)

    _check_landing_page(staging, options)
    return _promote(paths, staging)


def _check_landing_page(staging: Path, options: Options) -> None:
    """The ingress entry point must resolve to something."""
    if (staging / "index.html").is_file():
        return
    raise BuildError(
        "The documentation built without a landing page, so the app would show "
        "a 404 when opened. This usually means the repository's root README.md "
        "or index.md is matched by one of the 'exclude' patterns: "
        f"{', '.join(options.exclude) or '(none configured)'}"
    )


def _promote(paths: Paths, staging: Path) -> Path:
    generation = _next_generation(paths.site_root)
    final = paths.site_root / f"gen-{generation}"
    staging.rename(final)
    _prune(paths.site_root, keep=final)
    _LOGGER.info("Documentation site ready at %s", final)
    return final


def _next_generation(site_root: Path) -> int:
    generations = [
        int(path.name.removeprefix("gen-"))
        for path in site_root.glob("gen-*")
        if path.name.removeprefix("gen-").isdigit()
    ]
    return max(generations, default=0) + 1


def _prune(site_root: Path, keep: Path) -> None:
    # Open file descriptors survive the removal, so in-flight responses from an
    # older generation still complete.
    for path in site_root.iterdir():
        if path != keep and path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
