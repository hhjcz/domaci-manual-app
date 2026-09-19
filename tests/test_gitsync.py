import dataclasses

import pytest

from conftest import git, push_change
from domaci_manual.gitsync import GitError, Repository
from domaci_manual.ssh import prepare


@pytest.fixture
def repository(options, paths):
    return Repository(options, paths, prepare(options, paths))


async def test_first_sync_clones(repository, paths):
    result = await repository.sync()

    assert result.changed is True
    assert result.subject == "Initial documentation"
    assert (paths.repo_dir / "README.md").is_file()
    assert (paths.repo_dir / "heating/heat-pump.md").is_file()


async def test_second_sync_reports_no_change(repository):
    await repository.sync()
    result = await repository.sync()
    assert result.changed is False


async def test_sync_picks_up_a_pushed_change(repository, docs_workdir, paths):
    await repository.sync()
    expected = push_change(docs_workdir, "water/main-shutoff.md", "# Moved\n\nCellar.\n")

    result = await repository.sync()

    assert result.changed is True
    assert result.commit == expected
    assert "Cellar." in (paths.repo_dir / "water/main-shutoff.md").read_text()


async def test_sync_picks_up_a_deleted_file(repository, docs_workdir, paths):
    await repository.sync()
    (docs_workdir / "network/network.md").unlink()
    git("add", "-A", cwd=docs_workdir)
    git("commit", "-qm", "Drop network page", cwd=docs_workdir)
    git("push", "-q", "origin", "main", cwd=docs_workdir)

    await repository.sync()
    assert not (paths.repo_dir / "network/network.md").exists()


async def test_local_edits_are_discarded(repository, docs_workdir, paths):
    await repository.sync()
    (paths.repo_dir / "README.md").write_text("tampered", encoding="utf-8")
    (paths.repo_dir / "stray.md").write_text("stray", encoding="utf-8")

    push_change(docs_workdir, "heating/heat-pump.md", "# Heat pump\n\nNew.\n")
    await repository.sync()

    assert "tampered" not in (paths.repo_dir / "README.md").read_text()
    assert not (paths.repo_dir / "stray.md").exists()


async def test_changing_the_branch_reclones(options, paths, docs_workdir):
    credentials = prepare(options, paths)
    await Repository(options, paths, credentials).sync()

    git("checkout", "-q", "-b", "winter", cwd=docs_workdir)
    push_change(docs_workdir, "README.md", "# Winter manual\n")
    git("push", "-q", "origin", "winter", cwd=docs_workdir)

    on_winter = dataclasses.replace(options, branch="winter")
    result = await Repository(on_winter, paths, credentials).sync()

    assert result.changed is True
    assert "Winter manual" in (paths.repo_dir / "README.md").read_text()


async def test_changing_the_repository_reclones(options, paths, tmp_path):
    credentials = prepare(options, paths)
    await Repository(options, paths, credentials).sync()

    other = tmp_path / "other.git"
    work = tmp_path / "other-work"
    work.mkdir()
    git("init", "-q", "--bare", "-b", "main", str(other), cwd=tmp_path)
    git("init", "-q", "-b", "main", ".", cwd=work)
    (work / "README.md").write_text("# Other repository\n", encoding="utf-8")
    git("add", "-A", cwd=work)
    git("commit", "-qm", "Other", cwd=work)
    git("remote", "add", "origin", str(other), cwd=work)
    git("push", "-q", "origin", "main", cwd=work)

    elsewhere = dataclasses.replace(options, repository=f"file://{other}")
    await Repository(elsewhere, paths, credentials).sync()

    assert "Other repository" in (paths.repo_dir / "README.md").read_text()
    assert not (paths.repo_dir / "heating").exists()


async def test_docs_subdir_is_honoured(options, paths, docs_workdir):
    (docs_workdir / "docs").mkdir()
    (docs_workdir / "docs" / "index.md").write_text("# Nested\n", encoding="utf-8")
    git("add", "-A", cwd=docs_workdir)
    git("commit", "-qm", "Add nested docs", cwd=docs_workdir)
    git("push", "-q", "origin", "main", cwd=docs_workdir)

    nested = dataclasses.replace(options, docs_subdir="docs")
    repository = Repository(nested, paths, prepare(nested, paths))
    await repository.sync()

    assert repository.docs_dir == paths.repo_dir / "docs"


async def test_missing_docs_subdir_is_reported(options, paths):
    nested = dataclasses.replace(options, docs_subdir="nowhere")
    repository = Repository(nested, paths, prepare(nested, paths))

    with pytest.raises(GitError, match="docs_subdir"):
        await repository.sync()


async def test_missing_branch_gives_an_actionable_hint(options, paths):
    wrong = dataclasses.replace(options, branch="does-not-exist")
    repository = Repository(wrong, paths, prepare(wrong, paths))

    with pytest.raises(GitError) as err:
        await repository.sync()
    assert "does not exist on the remote" in err.value.hint


async def test_missing_repository_gives_an_actionable_hint(options, paths, tmp_path):
    missing = dataclasses.replace(options, repository=f"file://{tmp_path}/absent.git")
    repository = Repository(missing, paths, prepare(missing, paths))

    with pytest.raises(GitError) as err:
        await repository.sync()
    assert "was not found" in err.value.hint
    assert err.value.detail
