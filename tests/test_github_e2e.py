"""Opt-in end-to-end test against a real private GitHub repository.

Skipped unless the environment describes a test repository, so the default
suite never depends on GitHub. Run it with:

    DOMACI_MANUAL_E2E_REPO=git@github.com:you/domaci-manual-test.git \
    DOMACI_MANUAL_E2E_DEPLOY_KEY=~/.ssh/domaci_manual_test_deploy \
    make e2e-github

Two different credentials are involved, on purpose:

* the *deploy key* the app uses, which must be read-only;
* your own GitHub credentials (ssh-agent or ~/.ssh/config), used to push the
  documentation change.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from domaci_manual import server
from domaci_manual.config import Options
from domaci_manual.coordinator import Coordinator
from domaci_manual.state import Phase, Status

pytestmark = pytest.mark.github

REPO = os.environ.get("DOMACI_MANUAL_E2E_REPO", "")
DEPLOY_KEY = os.environ.get("DOMACI_MANUAL_E2E_DEPLOY_KEY", "")
BRANCH = os.environ.get("DOMACI_MANUAL_E2E_BRANCH", "main")
MARKER_FILE = "e2e/marker.md"

needs_github = pytest.mark.skipif(
    not (REPO and DEPLOY_KEY),
    reason="Set DOMACI_MANUAL_E2E_REPO and DOMACI_MANUAL_E2E_DEPLOY_KEY to run",
)


def developer_git(*args: str, cwd: Path) -> str:
    """Run git with the developer's own credentials, not the deploy key."""
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def app_options() -> Options:
    return Options(
        repository=REPO,
        branch=BRANCH,
        sync_interval=1,
        deploy_key=Path(DEPLOY_KEY).expanduser().read_text(encoding="utf-8"),
        log_level="debug",
    )


@needs_github
async def test_change_pushed_by_a_developer_reaches_the_rendered_site(
    aiohttp_client, paths, tmp_path, app_options
):
    from conftest import write_options

    write_options(paths, app_options)
    status = Status()
    coordinator = Coordinator(paths, status)
    client = await aiohttp_client(server.create_app(status, coordinator.trigger))

    # 1. The app clones the private repository with its read-only deploy key.
    await coordinator._cycle()
    assert status.phase is Phase.READY, f"{status.message}\n{status.detail}"

    # 2. The developer pushes a change with their own credentials.
    workdir = tmp_path / "developer-clone"
    developer_git("clone", "--branch", BRANCH, REPO, str(workdir), cwd=tmp_path)
    marker = workdir / MARKER_FILE
    marker.parent.mkdir(parents=True, exist_ok=True)
    unique = os.urandom(8).hex()
    marker.write_text(f"# Marker\n\nRun {unique}\n", encoding="utf-8")
    developer_git("add", "-A", cwd=workdir)
    developer_git("commit", "-m", f"E2E marker {unique}", cwd=workdir)
    developer_git("push", "origin", BRANCH, cwd=workdir)

    # 3. The app pulls the change.
    await coordinator._cycle()
    assert status.commit_subject == f"E2E marker {unique}"

    # 4. The rendered documentation changed.
    page = await client.get("/e2e/marker/")
    assert page.status == 200
    assert unique in await page.text()


@needs_github
async def test_the_deploy_key_cannot_push(paths, tmp_path, app_options):
    """The app credential must stay read-only."""
    from domaci_manual.gitsync import Repository
    from domaci_manual.ssh import prepare

    credentials = prepare(app_options, paths)
    repository = Repository(app_options, paths, credentials)
    await repository.sync()

    (paths.repo_dir / "should-not-exist.md").write_text("nope", encoding="utf-8")
    env = dict(os.environ, GIT_SSH_COMMAND=credentials.git_ssh_command)
    for args in (["add", "-A"], ["commit", "-m", "should fail to push"]):
        subprocess.run(["git", *args], cwd=paths.repo_dir, check=True, env=env)

    push = subprocess.run(
        ["git", "push", "origin", f"HEAD:{BRANCH}"],
        cwd=paths.repo_dir,
        env=env,
        capture_output=True,
        text=True,
    )
    assert push.returncode != 0, "The deploy key must not have write access"
    assert "read-only" in push.stderr.lower() or "denied" in push.stderr.lower()
