"""Filesystem layout and user-facing options.

Options come from ``/data/options.json``, which the Home Assistant Supervisor
writes from the add-on configuration. The same file is used in local
development, so there is only one code path.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_DATA_DIR = "/data"
DEFAULT_ADDON_CONFIG_DIR = "/config"

# Public keys of hosts we may talk to, baked into the image.
BUNDLED_KNOWN_HOSTS = Path("/usr/share/domaci-manual/known_hosts")

LOG_LEVELS = ("debug", "info", "warning", "error")

# git@host:path, ssh://…, https://… — anything else is almost certainly a typo.
_SCP_LIKE_URL = re.compile(r"^[A-Za-z0-9_.+-]+@[A-Za-z0-9_.-]+:[^/].*$")
_SUPPORTED_SCHEMES = ("ssh://", "https://", "http://", "git://", "file://", "/")


class ConfigError(Exception):
    """A user-correctable problem with the add-on configuration."""


@dataclass(frozen=True)
class Paths:
    """Everywhere the app is allowed to write."""

    data: Path
    addon_config: Path

    @classmethod
    def from_env(cls) -> Paths:
        return cls(
            data=Path(os.environ.get("DOMACI_MANUAL_DATA", DEFAULT_DATA_DIR)),
            addon_config=Path(
                os.environ.get("DOMACI_MANUAL_ADDON_CONFIG", DEFAULT_ADDON_CONFIG_DIR)
            ),
        )

    @property
    def options_file(self) -> Path:
        override = os.environ.get("DOMACI_MANUAL_OPTIONS")
        return Path(override) if override else self.data / "options.json"

    @property
    def ssh_dir(self) -> Path:
        return self.data / "ssh"

    @property
    def repo_dir(self) -> Path:
        return self.data / "repo"

    @property
    def repo_state_file(self) -> Path:
        return self.data / "repo-state.json"

    @property
    def site_root(self) -> Path:
        return self.data / "site"

    @property
    def mkdocs_config(self) -> Path:
        return self.data / "mkdocs.yml"

    def ensure(self) -> None:
        self.data.mkdir(parents=True, exist_ok=True)
        self.site_root.mkdir(parents=True, exist_ok=True)
        self.ssh_dir.mkdir(parents=True, exist_ok=True)
        self.ssh_dir.chmod(0o700)


@dataclass(frozen=True)
class Options:
    repository: str = ""
    branch: str = "main"
    docs_subdir: str = ""
    sync_interval: int = 15  # minutes
    site_name: str = "Domácí manuál"
    language: str = "en"
    strict_host_key_checking: bool = True
    extra_known_hosts: tuple[str, ...] = field(default_factory=tuple)
    deploy_key: str = ""
    log_level: str = "info"

    @property
    def sync_interval_seconds(self) -> int:
        return self.sync_interval * 60

    @property
    def uses_ssh(self) -> bool:
        return self.repository.startswith("ssh://") or bool(
            _SCP_LIKE_URL.match(self.repository)
        )

    def validate(self) -> None:
        """Raise ConfigError for anything the user has to fix themselves."""
        if not self.repository:
            raise ConfigError(
                "No repository configured. Set the 'repository' option to the "
                "SSH URL of your documentation repository, for example "
                "git@github.com:you/domaci-manual.git"
            )
        if not (
            _SCP_LIKE_URL.match(self.repository)
            or self.repository.startswith(_SUPPORTED_SCHEMES)
        ):
            raise ConfigError(
                f"'{self.repository}' is not a usable Git URL. Use an SSH URL "
                "such as git@github.com:you/domaci-manual.git, or an HTTPS URL "
                "for a public repository."
            )
        if not self.branch:
            raise ConfigError("No branch configured. Set the 'branch' option.")
        if self.docs_subdir:
            subdir = Path(self.docs_subdir)
            if subdir.is_absolute() or ".." in subdir.parts:
                raise ConfigError(
                    "'docs_subdir' must be a relative path inside the "
                    f"repository, got '{self.docs_subdir}'."
                )
        if self.sync_interval < 1:
            raise ConfigError("'sync_interval' must be at least 1 minute.")
        if self.log_level not in LOG_LEVELS:
            raise ConfigError(
                f"'log_level' must be one of {', '.join(LOG_LEVELS)}."
            )

    @classmethod
    def from_mapping(cls, raw: dict) -> Options:
        defaults = cls()
        extra_hosts = raw.get("extra_known_hosts") or []
        if isinstance(extra_hosts, str):
            extra_hosts = [extra_hosts]
        return cls(
            repository=str(raw.get("repository") or "").strip(),
            branch=str(raw.get("branch") or defaults.branch).strip(),
            docs_subdir=str(raw.get("docs_subdir") or "").strip().strip("/"),
            sync_interval=int(raw.get("sync_interval") or defaults.sync_interval),
            site_name=str(raw.get("site_name") or defaults.site_name).strip(),
            language=str(raw.get("language") or defaults.language).strip(),
            strict_host_key_checking=bool(
                raw.get("strict_host_key_checking", defaults.strict_host_key_checking)
            ),
            extra_known_hosts=tuple(
                line.strip() for line in extra_hosts if str(line).strip()
            ),
            deploy_key=str(raw.get("deploy_key") or ""),
            log_level=str(raw.get("log_level") or defaults.log_level).strip().lower(),
        )

    @classmethod
    def load(cls, path: Path) -> Options:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ConfigError(f"Options file {path} does not exist.") from None
        except json.JSONDecodeError as err:
            raise ConfigError(f"Options file {path} is not valid JSON: {err}") from None
        if not isinstance(raw, dict):
            raise ConfigError(f"Options file {path} must contain a JSON object.")
        return cls.from_mapping(raw)
