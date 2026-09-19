"""Drives the sync-and-build cycle.

One loop, one place where failures are turned into status the UI can show.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time

from .config import ConfigError, Options, Paths
from .gitsync import GitError, Repository
from .site import BuildError, build
from .ssh import prepare as prepare_ssh
from .state import Phase, Status

_LOGGER = logging.getLogger(__name__)

# After a failure, retry quickly at first so a user fixing the deploy key does
# not have to wait out a whole sync interval.
RETRY_BACKOFF_SECONDS = (30, 60, 120, 300, 600)


class Coordinator:
    def __init__(self, paths: Paths, status: Status) -> None:
        self._paths = paths
        self._status = status
        self._wakeup = asyncio.Event()
        self._failures = 0

    async def trigger(self) -> None:
        """Ask for a sync as soon as the loop is free."""
        self._wakeup.set()

    async def run(self) -> None:
        while True:
            delay = await self._cycle()
            self._status.next_attempt_at = time.time() + delay
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wakeup.wait(), timeout=delay)
            self._wakeup.clear()

    async def _cycle(self) -> float:
        """Run one sync/build attempt and return the seconds until the next."""
        options = None
        try:
            options = Options.load(self._paths.options_file)
            options.validate()
            _apply_log_level(options)
            await self._sync_and_build(options)
        except ConfigError as err:
            self._fail("Configuration problem", str(err))
        except GitError as err:
            self._fail(err.message, err.detail)
        except BuildError as err:
            self._fail(err.message, err.detail)
        except Exception:  # the loop must never die
            _LOGGER.exception("Unexpected error during synchronisation")
            self._fail(
                "Unexpected error during synchronisation",
                "See the add-on log for the full traceback.",
            )
        else:
            self._failures = 0
            return float(options.sync_interval_seconds)

        self._failures += 1
        index = min(self._failures, len(RETRY_BACKOFF_SECONDS)) - 1
        interval = RETRY_BACKOFF_SECONDS[index]
        if options is not None:
            interval = min(interval, options.sync_interval_seconds)
        return float(interval)

    async def _sync_and_build(self, options: Options) -> None:
        self._status.repository = options.repository
        self._status.branch = options.branch
        self._status.last_attempt_at = time.time()

        credentials = prepare_ssh(options, self._paths)
        self._status.public_key = credentials.public_key
        self._status.deploy_key_source = credentials.source

        repository = Repository(options, self._paths, credentials)
        self._status.working(Phase.SYNCING, "Checking for documentation updates")
        result = await repository.sync()
        self._status.commit = result.commit
        self._status.commit_subject = result.subject
        self._status.syncs += 1

        if result.changed or self._status.site_dir is None:
            self._status.working(Phase.BUILDING, "Building the documentation")
            self._status.site_dir = await build(
                options, self._paths, repository.docs_dir
            )
            self._status.builds += 1
        else:
            _LOGGER.debug("No changes; keeping the current site")

        self._status.phase = Phase.READY
        self._status.message = f"Up to date at {result.commit[:8]}"
        self._status.detail = ""
        self._status.last_success_at = time.time()

    def _fail(self, message: str, detail: str) -> None:
        self._status.failed(message, detail)
        if detail:
            _LOGGER.error("%s\n%s", message, detail)
        else:
            _LOGGER.error("%s", message)
        if self._status.site_dir is not None:
            _LOGGER.warning(
                "Continuing to serve the previously built documentation."
            )


def _apply_log_level(options: Options) -> None:
    level = getattr(logging, options.log_level.upper(), logging.INFO)
    logging.getLogger("domaci_manual").setLevel(level)
