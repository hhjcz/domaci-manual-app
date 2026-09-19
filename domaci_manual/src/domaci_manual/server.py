"""HTTP serving behind the Home Assistant ingress.

The ingress prefix is dynamic (``/api/hassio_ingress/<token>/``) and the
Supervisor strips it before proxying, passing it in ``X-Ingress-Path``. MkDocs
emits relative URLs, so pages and assets need no rewriting; the one place the
prefix matters is a redirect, which must be an absolute path.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from pathlib import Path

from aiohttp import web

from . import api, pages
from .state import Status

_LOGGER = logging.getLogger(__name__)

# The Supervisor is the only client allowed to reach an ingress add-on.
INGRESS_SOURCE_IP = "172.30.32.2"
LOOPBACK_IPS = frozenset({"127.0.0.1", "::1", "::ffff:127.0.0.1"})

# Material's asset filenames carry a content hash, so they can be cached hard.
IMMUTABLE_PREFIXES = ("assets/",)

SyncTrigger = Callable[[], Awaitable[None]]


def ingress_prefix(request: web.Request) -> str:
    return request.headers.get("X-Ingress-Path", "").rstrip("/")


def create_app(status: Status, request_sync: SyncTrigger) -> web.Application:
    app = web.Application(middlewares=[_access_control])
    app["status"] = status
    app["request_sync"] = request_sync

    app.router.add_get("/_app/health", _health)
    app.router.add_get("/_app/status", _status)
    app.router.add_post("/_app/sync", _sync)

    # Reserved for the future documentation chat backend; see api/__init__.py.
    api.setup_routes(app)

    app.router.add_route("*", "/{tail:.*}", _documentation)
    return app


@web.middleware
async def _access_control(request: web.Request, handler):
    """Under the Supervisor, only the ingress proxy may talk to us."""
    if request.path == "/_app/health" or not _under_supervisor():
        return await handler(request)
    remote = request.remote or ""
    if remote != INGRESS_SOURCE_IP and remote not in LOOPBACK_IPS:
        _LOGGER.warning("Rejected request from %s", remote)
        raise web.HTTPForbidden(text="Only reachable through Home Assistant ingress.")
    return await handler(request)


def _under_supervisor() -> bool:
    return bool(os.environ.get("SUPERVISOR_TOKEN"))


async def _health(request: web.Request) -> web.Response:
    return web.Response(text="ok")


async def _status(request: web.Request) -> web.Response:
    return web.json_response(request.app["status"].to_json())


async def _sync(request: web.Request) -> web.Response:
    await request.app["request_sync"]()
    return web.json_response({"triggered": True})


async def _documentation(request: web.Request) -> web.StreamResponse:
    if request.method not in ("GET", "HEAD"):
        raise web.HTTPMethodNotAllowed(request.method, ["GET", "HEAD"])

    status: Status = request.app["status"]
    if not status.ready:
        return _status_page(request, status)

    root = status.site_dir
    relative = request.match_info["tail"]
    target = _resolve(root, relative)
    if target is None:
        raise web.HTTPForbidden(text="Invalid path.")

    if relative == "" or relative.endswith("/"):
        index = target / "index.html"
        if index.is_file():
            return _file(index, relative)
        return _not_found(root)

    if target.is_file():
        return _file(target, relative)

    # `use_directory_urls` means every page is a directory: send the browser to
    # the canonical trailing-slash URL, prefixed so it survives the ingress.
    if (target / "index.html").is_file():
        location = f"{ingress_prefix(request)}/{relative}/"
        if request.query_string:
            location = f"{location}?{request.query_string}"
        raise web.HTTPMovedPermanently(location)

    return _not_found(root)


def _status_page(request: web.Request, status: Status) -> web.Response:
    body = pages.render(status, ingress_prefix(request))
    # 503 is honest about the site not being servable yet, and browsers still
    # render the body.
    return web.Response(
        text=body,
        content_type="text/html",
        status=503,
        headers={"Cache-Control": "no-store"},
    )


def _file(path: Path, relative: str) -> web.FileResponse:
    if relative.startswith(IMMUTABLE_PREFIXES):
        cache = "public, max-age=604800, immutable"
    else:
        cache = "no-cache"
    return web.FileResponse(
        path,
        headers={"Cache-Control": cache, "X-Content-Type-Options": "nosniff"},
    )


def _not_found(root: Path) -> web.StreamResponse:
    custom = root / "404.html"
    if custom.is_file():
        return web.FileResponse(
            custom, status=404, headers={"Cache-Control": "no-store"}
        )
    raise web.HTTPNotFound(text="Page not found.")


def _resolve(root: Path, relative: str) -> Path | None:
    """Join ``relative`` onto ``root``, refusing anything that escapes it."""
    try:
        root_real = root.resolve()
        candidate = (root_real / relative).resolve()
    except OSError:
        return None
    if candidate != root_real and root_real not in candidate.parents:
        return None
    return candidate
