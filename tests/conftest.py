"""Shared fixtures. Nothing here touches the network."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from domaci_manual.config import Options, Paths

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DOCS = REPO_ROOT / "sample-docs"
BUNDLED_KNOWN_HOSTS = (
    REPO_ROOT / "domaci_manual/rootfs/usr/share/domaci-manual/known_hosts"
)


def git(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(cwd),
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
        },
    )
    return result.stdout


@pytest.fixture
def paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Paths:
    monkeypatch.setenv("DOMACI_MANUAL_KNOWN_HOSTS", str(BUNDLED_KNOWN_HOSTS))
    layout = Paths(data=tmp_path / "data", addon_config=tmp_path / "addon_config")
    layout.ensure()
    layout.addon_config.mkdir(parents=True, exist_ok=True)
    return layout


@pytest.fixture
def docs_remote(tmp_path: Path) -> Path:
    """A bare Git repository seeded with the sample documentation."""
    work = tmp_path / "docs-work"
    bare = tmp_path / "docs.git"
    shutil.copytree(SAMPLE_DOCS, work)

    git("init", "-q", "--bare", "-b", "main", str(bare), cwd=tmp_path)
    git("init", "-q", "-b", "main", ".", cwd=work)
    git("add", "-A", cwd=work)
    git("commit", "-qm", "Initial documentation", cwd=work)
    git("remote", "add", "origin", str(bare), cwd=work)
    git("push", "-q", "origin", "main", cwd=work)
    return bare


@pytest.fixture
def docs_workdir(docs_remote: Path, tmp_path: Path) -> Path:
    return tmp_path / "docs-work"


@pytest.fixture
def options(docs_remote: Path) -> Options:
    return Options(
        repository=f"file://{docs_remote}",
        branch="main",
        sync_interval=1,
        site_name="Test manual",
        log_level="debug",
    )


def write_options(paths: Paths, options: Options, **overrides) -> None:
    payload = {
        "repository": options.repository,
        "branch": options.branch,
        "docs_subdir": options.docs_subdir,
        "sync_interval": options.sync_interval,
        "site_name": options.site_name,
        "language": options.language,
        "strict_host_key_checking": options.strict_host_key_checking,
        "extra_known_hosts": list(options.extra_known_hosts),
        "deploy_key": options.deploy_key,
        "log_level": options.log_level,
    }
    payload.update(overrides)
    paths.options_file.write_text(json.dumps(payload), encoding="utf-8")


def push_change(workdir: Path, relative: str, text: str) -> str:
    target = workdir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    git("add", "-A", cwd=workdir)
    git("commit", "-qm", f"Update {relative}", cwd=workdir)
    git("push", "-q", "origin", "main", cwd=workdir)
    return git("rev-parse", "HEAD", cwd=workdir).strip()
