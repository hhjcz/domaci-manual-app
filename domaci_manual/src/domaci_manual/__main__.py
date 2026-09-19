"""Entry point: start the HTTP server, then keep the documentation in sync."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import sys

from aiohttp import web

from . import __version__
from .config import Paths
from .coordinator import Coordinator
from .server import create_app
from .state import Status

_LOGGER = logging.getLogger("domaci_manual")

# Reachable only through the Supervisor ingress proxy; see server.py.
BIND_HOST = "0.0.0.0"
BIND_PORT = 8099


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    # aiohttp logs every asset request; the add-on log is not the place for it.
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)


async def run() -> None:
    paths = Paths.from_env()
    paths.ensure()

    status = Status()
    coordinator = Coordinator(paths, status)

    app = create_app(status, coordinator.trigger)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, BIND_HOST, BIND_PORT)
    await site.start()
    _LOGGER.info("Domácí manuál %s listening on %s:%s", __version__, BIND_HOST, BIND_PORT)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    sync_task = asyncio.create_task(coordinator.run(), name="sync")
    try:
        await stop.wait()
    finally:
        _LOGGER.info("Shutting down")
        sync_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sync_task
        await runner.cleanup()


def main() -> int:
    configure_logging()
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
