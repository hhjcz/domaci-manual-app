"""Runtime status shared between the sync task and the HTTP server.

Both live in the same event loop, so a plain mutable object is enough.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path


class Phase(StrEnum):
    STARTING = "starting"
    SYNCING = "syncing"
    BUILDING = "building"
    READY = "ready"
    ERROR = "error"


@dataclass
class Status:
    phase: Phase = Phase.STARTING
    message: str = "Starting up"
    # Operator-facing detail: command output, hints, stack-trace-free text.
    detail: str = ""
    repository: str = ""
    branch: str = ""
    commit: str = ""
    commit_subject: str = ""
    public_key: str = ""
    deploy_key_source: str = ""
    last_success_at: float | None = None
    last_attempt_at: float | None = None
    next_attempt_at: float | None = None
    syncs: int = 0
    builds: int = 0
    site_dir: Path | None = field(default=None, repr=False)

    @property
    def ready(self) -> bool:
        """True once a built site exists.

        Deliberately independent of :attr:`phase`: once documentation has been
        built successfully, a later failed sync keeps serving the last good
        site rather than replacing it with an error page. The failure is
        reported in the add-on log and on ``/_app/status``.
        """
        return self.site_dir is not None

    def working(self, phase: Phase, message: str) -> None:
        self.phase = phase
        self.message = message
        self.detail = ""

    def failed(self, message: str, detail: str = "") -> None:
        self.phase = Phase.ERROR
        self.message = message
        self.detail = detail

    def to_json(self) -> dict:
        data = asdict(self)
        data["phase"] = self.phase.value
        data["site_dir"] = str(self.site_dir) if self.site_dir else None
        data["ready"] = self.ready
        data["now"] = time.time()
        return data
