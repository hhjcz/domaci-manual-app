import dataclasses

import pytest
import yaml

from conftest import SAMPLE_DOCS
from domaci_manual import site
from domaci_manual.config import Options


@pytest.fixture
def docs_dir(tmp_path):
    import shutil

    target = tmp_path / "docs"
    shutil.copytree(SAMPLE_DOCS, target)
    return target


def test_config_has_no_site_url_so_urls_stay_relative(options, tmp_path):
    config = site.mkdocs_config(options, tmp_path / "docs", tmp_path / "site")
    assert "site_url" not in config
    assert config["use_directory_urls"] is True
    assert config["theme"]["name"] == "material"


def test_config_uses_the_configured_site_name_and_language(tmp_path):
    options = Options(repository="file:///x", site_name="Doma", language="cs")
    config = site.mkdocs_config(options, tmp_path / "docs", tmp_path / "site")
    assert config["site_name"] == "Doma"
    assert config["theme"]["language"] == "cs"


def test_written_config_is_loadable_yaml(options, paths, tmp_path):
    written = site.write_config(options, paths, tmp_path / "docs", tmp_path / "site")
    assert yaml.safe_load(written.read_text(encoding="utf-8"))["site_name"] == (
        options.site_name
    )


def test_readme_is_kept_as_the_landing_page(options, docs_dir):
    site.ensure_landing_page(options, docs_dir)
    assert not (docs_dir / "index.md").exists()


def test_landing_page_is_generated_when_missing(options, docs_dir):
    (docs_dir / "README.md").unlink()
    site.ensure_landing_page(options, docs_dir)
    assert options.site_name in (docs_dir / "index.md").read_text(encoding="utf-8")


def test_dotfiles_do_not_count_as_documentation(tmp_path):
    docs = tmp_path / "docs"
    (docs / ".obsidian").mkdir(parents=True)
    (docs / ".obsidian" / "notes.md").write_text("x", encoding="utf-8")
    assert site.count_markdown_files(docs) == 0


async def test_build_renders_the_sample_documentation(options, paths, docs_dir):
    built = await site.build(options, paths, docs_dir)

    index = (built / "index.html").read_text(encoding="utf-8")
    assert "Household manual" in index
    assert (built / "heating/heat-pump/index.html").is_file()
    assert (built / "404.html").is_file()
    assert list(built.glob("assets/javascripts/*.js"))


async def test_built_pages_reference_assets_relatively(options, paths, docs_dir):
    built = await site.build(options, paths, docs_dir)

    nested = (built / "heating/heat-pump/index.html").read_text(encoding="utf-8")
    assert 'href="../../assets/' in nested
    # An absolute asset path would break under the ingress prefix.
    assert 'href="/assets/' not in nested
    assert 'src="/assets/' not in nested


async def test_navigation_is_derived_from_the_directory_tree(options, paths, docs_dir):
    built = await site.build(options, paths, docs_dir)
    index = (built / "index.html").read_text(encoding="utf-8")

    for section in ("Heating", "Water", "Electricity", "Network"):
        assert section in index


async def test_markdown_tables_and_admonitions_render(options, paths, docs_dir):
    built = await site.build(options, paths, docs_dir)
    page = (built / "heating/heat-pump/index.html").read_text(encoding="utf-8")

    assert "<table>" in page
    assert "admonition warning" in page


async def test_each_build_lands_in_a_fresh_generation(options, paths, docs_dir):
    first = await site.build(options, paths, docs_dir)
    (docs_dir / "README.md").write_text("# Second build\n", encoding="utf-8")
    second = await site.build(options, paths, docs_dir)

    assert first != second
    assert "Second build" in (second / "index.html").read_text(encoding="utf-8")
    # Old generations are pruned so /data does not grow without bound.
    assert [p.name for p in paths.site_root.iterdir()] == [second.name]


async def test_empty_documentation_is_reported(options, paths, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(site.BuildError, match="No Markdown files"):
        await site.build(options, paths, empty)


async def test_build_failure_keeps_the_previous_site(options, paths, docs_dir):
    good = await site.build(options, paths, docs_dir)

    broken = dataclasses.replace(options, language="this-is-not-a-language")
    with pytest.raises(site.BuildError):
        await site.build(broken, paths, docs_dir)

    assert (good / "index.html").is_file()


async def test_no_external_font_requests(options, paths, docs_dir):
    """A household manual must not phone home to Google on every page load."""
    built = await site.build(options, paths, docs_dir)
    index = (built / "index.html").read_text(encoding="utf-8")
    assert "fonts.googleapis.com" not in index
    assert "fonts.gstatic.com" not in index


async def test_content_grid_is_widened(options, paths, docs_dir):
    """The theme override must survive into every rendered page."""
    built = await site.build(options, paths, docs_dir)
    for page in ("index.html", "heating/heat-pump/index.html"):
        markup = (built / page).read_text(encoding="utf-8")
        assert ".md-grid" in markup
        assert "max-width: 72rem" in markup


async def test_excluded_files_are_not_published(options, paths, docs_dir):
    (docs_dir / "drafts").mkdir()
    (docs_dir / "drafts" / "wip.md").write_text("# Work in progress\n", encoding="utf-8")
    (docs_dir / "heating" / "boiler.todo.md").write_text("# Todo\n", encoding="utf-8")

    excluding = dataclasses.replace(options, exclude=("drafts/", "*.todo.md"))
    built = await site.build(excluding, paths, docs_dir)

    assert not (built / "drafts").exists()
    assert not (built / "heating/boiler.todo/index.html").exists()
    # Still there: exclusion must not take the rest of the section with it.
    assert (built / "heating/heat-pump/index.html").is_file()


async def test_excluded_pages_leave_the_navigation_and_search_index(
    options, paths, docs_dir
):
    (docs_dir / "secret.md").write_text("# Alarm code\n\nThe code is 1234.\n", "utf-8")

    excluding = dataclasses.replace(options, exclude=("secret.md",))
    built = await site.build(excluding, paths, docs_dir)

    index = (built / "index.html").read_text(encoding="utf-8")
    search = (built / "search/search_index.json").read_text(encoding="utf-8")
    assert "Alarm code" not in index
    assert "Alarm code" not in search
    assert "1234" not in search


async def test_exclude_supports_re_inclusion(options, paths, docs_dir):
    (docs_dir / "drafts").mkdir()
    (docs_dir / "drafts" / "wip.md").write_text("# Wip\n", encoding="utf-8")
    (docs_dir / "drafts" / "keep.md").write_text("# Keep me\n", encoding="utf-8")

    excluding = dataclasses.replace(options, exclude=("drafts/*", "!drafts/keep.md"))
    built = await site.build(excluding, paths, docs_dir)

    assert not (built / "drafts/wip/index.html").exists()
    assert (built / "drafts/keep/index.html").is_file()


async def test_no_exclusions_by_default(options, paths, tmp_path):
    config = site.mkdocs_config(options, tmp_path / "docs", tmp_path / "site")
    assert config["exclude_docs"] == ""


async def test_excluding_the_landing_page_is_reported(options, paths, docs_dir):
    excluding = dataclasses.replace(options, exclude=("README.md",))

    with pytest.raises(site.BuildError, match="landing page"):
        await site.build(excluding, paths, docs_dir)
