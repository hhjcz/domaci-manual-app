"""HTTP behaviour, with the emphasis on surviving the ingress path prefix."""

from __future__ import annotations

import pytest

from domaci_manual import server
from domaci_manual.state import Phase, Status

INGRESS_HEADERS = {"X-Ingress-Path": "/api/hassio_ingress/AbC123"}


@pytest.fixture
def triggered():
    return []


@pytest.fixture
def status():
    return Status()


@pytest.fixture
async def client(aiohttp_client, status, triggered):
    async def request_sync() -> None:
        triggered.append(True)

    return await aiohttp_client(server.create_app(status, request_sync))


@pytest.fixture
async def ready_client(client, status, tmp_path):
    site = tmp_path / "site"
    (site / "heating" / "heat-pump").mkdir(parents=True)
    (site / "assets").mkdir()
    (site / "index.html").write_text("<h1>Household manual</h1>", encoding="utf-8")
    (site / "heating" / "heat-pump" / "index.html").write_text("<h1>Heat pump</h1>")
    (site / "assets" / "app.js").write_text("// asset", encoding="utf-8")
    (site / "404.html").write_text("<h1>Not found</h1>", encoding="utf-8")
    status.site_dir = site
    status.phase = Phase.READY
    return client


async def test_status_page_is_served_before_the_first_build(client, status):
    status.public_key = "ssh-ed25519 AAAAtest domaci-manual@home-assistant"
    status.deploy_key_source = "generated"

    response = await client.get("/", headers=INGRESS_HEADERS)

    assert response.status == 503
    body = await response.text()
    assert "ssh-ed25519 AAAAtest" in body
    assert "Deploy keys" in body
    # Buttons must target the ingress-prefixed path, not a bare /_app/sync.
    assert "'/api/hassio_ingress/AbC123/_app/sync'" in body


async def test_status_page_shows_configuration_errors(client, status):
    status.failed("Configuration problem", "No repository configured.")

    body = await (await client.get("/deep/link/", headers=INGRESS_HEADERS)).text()

    assert "Configuration problem" in body
    assert "No repository configured." in body
    # An error is not going to fix itself; do not spin on a refresh loop.
    assert "http-equiv=\"refresh\"" not in body


async def test_serves_the_index(ready_client):
    response = await ready_client.get("/", headers=INGRESS_HEADERS)
    assert response.status == 200
    assert "Household manual" in await response.text()


async def test_serves_a_directory_url_page(ready_client):
    response = await ready_client.get("/heating/heat-pump/", headers=INGRESS_HEADERS)
    assert response.status == 200
    assert "Heat pump" in await response.text()


async def test_redirect_keeps_the_ingress_prefix(ready_client):
    response = await ready_client.get(
        "/heating/heat-pump", headers=INGRESS_HEADERS, allow_redirects=False
    )
    assert response.status == 301
    assert response.headers["Location"] == (
        "/api/hassio_ingress/AbC123/heating/heat-pump/"
    )


async def test_redirect_preserves_the_query_string(ready_client):
    response = await ready_client.get(
        "/heating/heat-pump?h=filter", headers=INGRESS_HEADERS, allow_redirects=False
    )
    assert response.headers["Location"].endswith("/heating/heat-pump/?h=filter")


async def test_redirect_without_ingress_still_works(ready_client):
    response = await ready_client.get("/heating/heat-pump", allow_redirects=False)
    assert response.headers["Location"] == "/heating/heat-pump/"


async def test_unknown_page_serves_the_mkdocs_404(ready_client):
    response = await ready_client.get("/nope/", headers=INGRESS_HEADERS)
    assert response.status == 404
    assert "Not found" in await response.text()


@pytest.mark.parametrize(
    "path",
    [
        "/../secret",
        "/heating/../../secret",
        "/%2e%2e/%2e%2e/etc/passwd",
        "/heating/%2e%2e/%2e%2e/%2e%2e/etc/passwd",
    ],
)
async def test_path_traversal_is_refused(ready_client, path):
    response = await ready_client.get(path, headers=INGRESS_HEADERS)
    assert response.status in (403, 404)


@pytest.mark.parametrize(
    "relative", ["../secret", "../../etc/passwd", "a/../../b", "/etc/passwd"]
)
def test_resolve_refuses_to_leave_the_site_directory(tmp_path, relative):
    root = tmp_path / "site"
    root.mkdir()
    (tmp_path / "secret").write_text("nope", encoding="utf-8")
    assert server._resolve(root, relative) is None


def test_resolve_accepts_paths_inside_the_site_directory(tmp_path):
    root = tmp_path / "site"
    (root / "heating").mkdir(parents=True)
    assert server._resolve(root, "heating") == (root / "heating").resolve()
    assert server._resolve(root, "") == root.resolve()


async def test_assets_are_cached_but_pages_are_not(ready_client):
    asset = await ready_client.get("/assets/app.js", headers=INGRESS_HEADERS)
    page = await ready_client.get("/", headers=INGRESS_HEADERS)

    assert "immutable" in asset.headers["Cache-Control"]
    assert page.headers["Cache-Control"] == "no-cache"


async def test_status_endpoint_reports_the_runtime_state(ready_client, status):
    status.commit = "abc123"
    payload = await (await ready_client.get("/_app/status")).json()

    assert payload["ready"] is True
    assert payload["commit"] == "abc123"
    assert payload["phase"] == "ready"


async def test_sync_endpoint_triggers_a_sync(client, triggered):
    response = await client.post("/_app/sync")
    assert response.status == 200
    assert triggered == [True]


async def test_writes_are_not_accepted_on_documentation_paths(ready_client):
    assert (await ready_client.post("/heating/heat-pump/")).status == 405


async def test_supervisor_rejects_non_ingress_clients(
    ready_client, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "token")
    monkeypatch.setattr(server, "LOOPBACK_IPS", frozenset())

    assert (await ready_client.get("/", headers=INGRESS_HEADERS)).status == 403
    # The container health check must keep working.
    assert (await ready_client.get("/_app/health")).status == 200


async def test_outside_supervisor_everything_is_reachable(
    ready_client, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    monkeypatch.setattr(server, "LOOPBACK_IPS", frozenset())

    assert (await ready_client.get("/")).status == 200
