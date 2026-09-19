"""The full pipeline — clone, build, serve, detect a push, rebuild.

This is the local-fixture twin of the GitHub end-to-end flow in
tests/test_github_e2e.py, and it needs no network.
"""

from __future__ import annotations

import pytest

from conftest import push_change, write_options
from domaci_manual import server
from domaci_manual.config import Options
from domaci_manual.coordinator import Coordinator
from domaci_manual.state import Phase, Status


@pytest.fixture
async def running(aiohttp_client, paths, options):
    write_options(paths, options)
    status = Status()
    coordinator = Coordinator(paths, status)
    client = await aiohttp_client(server.create_app(status, coordinator.trigger))
    return coordinator, status, client


async def test_first_cycle_clones_builds_and_serves(running):
    coordinator, status, client = running

    interval = await coordinator._cycle()

    assert status.phase is Phase.READY
    assert status.ready
    assert interval == 60  # sync_interval of 1 minute
    body = await (await client.get("/")).text()
    assert "Household manual" in body
    assert "Heat pump" in body  # navigation built from the directory tree


async def test_a_pushed_change_reaches_the_rendered_site(running, docs_workdir):
    coordinator, status, client = running
    await coordinator._cycle()
    builds_before = status.builds

    push_change(
        docs_workdir,
        "water/main-shutoff.md",
        "# Main water shut-off\n\nMoved to the cellar in 2026.\n",
    )
    await coordinator._cycle()

    assert status.builds == builds_before + 1
    page = await (await client.get("/water/main-shutoff/")).text()
    assert "Moved to the cellar in 2026." in page


async def test_a_new_page_appears_in_the_navigation(running, docs_workdir):
    coordinator, _status, client = running
    await coordinator._cycle()

    push_change(docs_workdir, "garden/irrigation.md", "# Irrigation\n\nZone 1.\n")
    await coordinator._cycle()

    assert (await client.get("/garden/irrigation/")).status == 200
    assert "Garden" in await (await client.get("/")).text()


async def test_an_unchanged_repository_is_not_rebuilt(running):
    coordinator, status, _ = running
    await coordinator._cycle()
    builds = status.builds

    await coordinator._cycle()

    assert status.syncs == 2
    assert status.builds == builds


async def test_a_broken_configuration_surfaces_on_the_status_page(paths, aiohttp_client):
    write_options(paths, Options(repository=""))
    status = Status()
    coordinator = Coordinator(paths, status)
    client = await aiohttp_client(server.create_app(status, coordinator.trigger))

    await coordinator._cycle()

    assert status.phase is Phase.ERROR
    body = await (await client.get("/")).text()
    assert "No repository configured" in body


async def test_a_later_failure_keeps_serving_the_last_good_site(
    running, paths, options
):
    coordinator, status, client = running
    await coordinator._cycle()

    write_options(paths, options, repository="file:///nonexistent/repo.git")
    await coordinator._cycle()

    assert status.phase is Phase.ERROR
    assert status.ready
    assert "Household manual" in await (await client.get("/")).text()


async def test_failures_back_off_before_retrying(running, paths, options):
    coordinator, status, _ = running
    write_options(paths, options, repository="file:///nonexistent/repo.git")

    first = await coordinator._cycle()
    second = await coordinator._cycle()

    assert status.phase is Phase.ERROR
    # Capped by the configured sync interval of 60 seconds.
    assert first == 30
    assert second == 60


async def test_the_deploy_key_is_generated_on_the_first_cycle(running, paths):
    coordinator, status, _ = running
    await coordinator._cycle()

    assert status.public_key.startswith("ssh-ed25519 ")
    assert status.deploy_key_source == "generated"
    assert (paths.ssh_dir / "id_ed25519").is_file()


async def test_changing_an_option_rebuilds_without_a_new_commit(
    running, paths, options
):
    """Editing `exclude` must take effect on the next sync, not the next push."""
    coordinator, status, client = running
    await coordinator._cycle()
    assert (await client.get("/water/main-shutoff/")).status == 200
    builds = status.builds

    write_options(paths, options, exclude=["water/"])
    await coordinator._cycle()

    assert status.builds == builds + 1
    assert (await client.get("/water/main-shutoff/")).status == 404
    assert (await client.get("/heating/heat-pump/")).status == 200


async def test_an_unchanged_option_set_does_not_rebuild(running, paths, options):
    coordinator, status, _ = running
    await coordinator._cycle()
    builds = status.builds

    write_options(paths, options)
    await coordinator._cycle()

    assert status.builds == builds


async def test_excluding_the_landing_page_keeps_the_last_good_site(
    running, paths, options
):
    coordinator, status, client = running
    await coordinator._cycle()

    write_options(paths, options, exclude=["README.md"])
    await coordinator._cycle()

    assert status.phase is Phase.ERROR
    assert "landing page" in status.message
    # The previously built site is still served rather than a 404.
    assert (await client.get("/")).status == 200
