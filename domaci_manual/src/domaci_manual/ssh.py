"""SSH credentials for read-only access to the documentation repository.

By default the app generates its own ed25519 key pair in ``/data/ssh`` and
prints the public half. The user registers that public key as a *read-only*
deploy key on GitHub; the private half never leaves the add-on's data volume
and is never part of the Docker image.

A user-supplied key is still accepted, either as a file in the add-on's config
directory or inline in the options, for people who manage keys elsewhere.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import BUNDLED_KNOWN_HOSTS, ConfigError, Options, Paths

_LOGGER = logging.getLogger(__name__)

# Names accepted for a user-supplied private key in the add-on config dir.
USER_KEY_FILENAMES = ("deploy_key", "id_ed25519", "id_rsa")

SOURCE_GENERATED = "generated"
SOURCE_OPTION = "option"
SOURCE_CONFIG_FILE = "config-file"


@dataclass(frozen=True)
class SshCredentials:
    key_path: Path
    public_key: str
    source: str
    known_hosts_path: Path
    strict: bool

    @property
    def git_ssh_command(self) -> str:
        host_key_policy = "yes" if self.strict else "accept-new"
        return " ".join(
            [
                "ssh",
                "-i", str(self.key_path),
                # Do not let ssh fall back to an agent or other keys: a wrong
                # key would produce a confusing "too many authentication
                # failures" instead of a clear rejection.
                "-o", "IdentitiesOnly=yes",
                "-o", "IdentityAgent=none",
                "-o", "BatchMode=yes",
                "-o", f"StrictHostKeyChecking={host_key_policy}",
                "-o", f"UserKnownHostsFile={self.known_hosts_path}",
                "-o", "ConnectTimeout=20",
            ]
        )


def prepare(options: Options, paths: Paths) -> SshCredentials:
    """Materialise the key and known_hosts files, then describe them."""
    paths.ensure()
    key_path, source = _resolve_private_key(options, paths)
    public_key = _public_key_for(key_path)
    known_hosts = _write_known_hosts(options, paths)
    return SshCredentials(
        key_path=key_path,
        public_key=public_key,
        source=source,
        known_hosts_path=known_hosts,
        strict=options.strict_host_key_checking,
    )


def _resolve_private_key(options: Options, paths: Paths) -> tuple[Path, str]:
    user_key = paths.ssh_dir / "user_key"
    managed_key = paths.ssh_dir / "id_ed25519"

    if options.deploy_key.strip():
        _write_private_key(user_key, options.deploy_key)
        return user_key, SOURCE_OPTION

    supplied = _find_supplied_key_file(paths)
    if supplied is not None:
        _write_private_key(user_key, supplied.read_text(encoding="utf-8"))
        return user_key, SOURCE_CONFIG_FILE

    # Nothing supplied: fall back to the key we manage ourselves.
    user_key.unlink(missing_ok=True)
    if not managed_key.exists():
        _generate_key(managed_key)
    managed_key.chmod(0o600)
    return managed_key, SOURCE_GENERATED


def _find_supplied_key_file(paths: Paths) -> Path | None:
    for name in USER_KEY_FILENAMES:
        candidate = paths.addon_config / name
        if candidate.is_file():
            _LOGGER.info("Using SSH private key supplied at %s", candidate)
            return candidate
    return None


def _write_private_key(path: Path, material: str) -> None:
    # OpenSSH rejects a key file without a trailing newline.
    path.write_text(material.rstrip("\n") + "\n", encoding="utf-8")
    path.chmod(0o600)


def _generate_key(path: Path) -> None:
    _LOGGER.info("Generating a new read-only deploy key at %s", path)
    path.unlink(missing_ok=True)
    Path(f"{path}.pub").unlink(missing_ok=True)
    _run(
        [
            "ssh-keygen",
            "-t", "ed25519",
            "-N", "",
            "-C", "domaci-manual@home-assistant",
            "-f", str(path),
        ],
        "Could not generate an SSH key",
    )


def _public_key_for(key_path: Path) -> str:
    """Derive the public key, so it is correct even for a supplied key."""
    result = _run(
        ["ssh-keygen", "-y", "-f", str(key_path)],
        "Could not read the SSH private key",
        check=False,
    )
    if result.returncode != 0:
        raise ConfigError(
            "The configured SSH private key could not be read. It must be an "
            "unencrypted OpenSSH private key (no passphrase). OpenSSH said: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout.strip()


def _write_known_hosts(options: Options, paths: Paths) -> Path:
    bundled = Path(os.environ.get("DOMACI_MANUAL_KNOWN_HOSTS", BUNDLED_KNOWN_HOSTS))
    lines: list[str] = []
    if bundled.is_file():
        lines.append(bundled.read_text(encoding="utf-8").rstrip("\n"))
    else:
        _LOGGER.warning("Bundled known_hosts file %s is missing", bundled)
    if options.extra_known_hosts:
        lines.append("# extra_known_hosts from the add-on configuration")
        lines.extend(options.extra_known_hosts)

    target = paths.ssh_dir / "known_hosts"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    target.chmod(0o600)
    return target


def _run(
    args: list[str], failure: str, check: bool = True
) -> subprocess.CompletedProcess:
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        raise ConfigError(f"{failure}: {result.stderr.strip() or result.stdout.strip()}")
    return result
