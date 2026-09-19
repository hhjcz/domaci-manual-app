"""Read-only Git synchronisation of the documentation repository.

The app never writes to the remote. Locally it is deliberately destructive:
the working tree is reset to the remote branch on every change, so a partially
applied or manually edited checkout can never drift.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from .config import Options, Paths
from .ssh import SshCredentials

_LOGGER = logging.getLogger(__name__)

CLONE_DEPTH = 1


class GitError(Exception):
    """A Git operation failed. Carries an actionable hint where we have one."""

    def __init__(self, message: str, hint: str = "", output: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.output = output

    @property
    def detail(self) -> str:
        parts = [part for part in (self.hint, self.output.strip()) if part]
        return "\n\n".join(parts)


@dataclass(frozen=True)
class SyncResult:
    changed: bool
    commit: str
    subject: str


class Repository:
    """The local checkout of the documentation repository."""

    def __init__(
        self, options: Options, paths: Paths, credentials: SshCredentials
    ) -> None:
        self._options = options
        self._paths = paths
        self._credentials = credentials

    @property
    def docs_dir(self) -> Path:
        if self._options.docs_subdir:
            return self._paths.repo_dir / self._options.docs_subdir
        return self._paths.repo_dir

    async def sync(self) -> SyncResult:
        """Clone or update the checkout and report whether anything changed."""
        if self._needs_fresh_clone():
            await self._clone()
            changed = True
        else:
            changed = await self._pull()

        self._write_state()
        commit, subject = await self._head()
        self._check_docs_dir()
        return SyncResult(changed=changed, commit=commit, subject=subject)

    async def local_state(self) -> SyncResult | None:
        """Describe the existing checkout without touching the network.

        Returns None when there is nothing usable to fall back on: no checkout
        yet, or one belonging to a repository or branch the user has since
        moved away from. Content from a repository that is no longer configured
        must never be served.
        """
        if self._needs_fresh_clone() or not self.docs_dir.is_dir():
            return None
        try:
            commit, subject = await self._head()
        except GitError:
            return None
        return SyncResult(changed=False, commit=commit, subject=subject)

    # -- clone / pull ----------------------------------------------------

    def _needs_fresh_clone(self) -> bool:
        if not (self._paths.repo_dir / ".git").is_dir():
            return True
        previous = self._read_state()
        return (
            previous.get("repository") != self._options.repository
            or previous.get("branch") != self._options.branch
        )

    async def _clone(self) -> None:
        target = self._paths.repo_dir
        if target.exists():
            _LOGGER.info("Repository or branch changed, re-cloning from scratch")
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)

        _LOGGER.info(
            "Cloning %s (branch %s)", self._options.repository, self._options.branch
        )
        await self._git(
            [
                "clone",
                "--depth", str(CLONE_DEPTH),
                "--single-branch",
                "--no-tags",
                "--branch", self._options.branch,
                self._options.repository,
                str(target),
            ],
            cwd=target.parent,
        )

    async def _pull(self) -> bool:
        before = (await self._git(["rev-parse", "HEAD"])).strip()
        await self._git(
            [
                "fetch",
                "--depth", str(CLONE_DEPTH),
                "--no-tags",
                "--prune",
                "origin",
                self._options.branch,
            ]
        )
        after = (await self._git(["rev-parse", "FETCH_HEAD"])).strip()
        if before == after:
            _LOGGER.debug("Already up to date at %s", before[:8])
            return False

        _LOGGER.info("Updating %s -> %s", before[:8], after[:8])
        await self._git(["reset", "--hard", "FETCH_HEAD"])
        await self._git(["clean", "-ffdx"])
        return True

    async def _head(self) -> tuple[str, str]:
        commit = (await self._git(["rev-parse", "HEAD"])).strip()
        subject = (await self._git(["log", "-1", "--format=%s"])).strip()
        return commit, subject

    def _check_docs_dir(self) -> None:
        if self.docs_dir.is_dir():
            return
        raise GitError(
            f"The configured docs_subdir '{self._options.docs_subdir}' does not "
            "exist in the repository.",
            hint="Clear the 'docs_subdir' option to use the repository root.",
        )

    # -- persisted marker ------------------------------------------------

    def _read_state(self) -> dict:
        try:
            return json.loads(self._paths.repo_state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_state(self) -> None:
        self._paths.repo_state_file.write_text(
            json.dumps(
                {
                    "repository": self._options.repository,
                    "branch": self._options.branch,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    # -- process plumbing ------------------------------------------------

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        env.update(
            {
                "GIT_SSH_COMMAND": self._credentials.git_ssh_command,
                # Never block on a credential or host-key prompt.
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_ASKPASS": "",
                "SSH_ASKPASS": "",
                # Keep the user's machine-wide git config out of the picture and
                # give git a HOME it is allowed to write to.
                "GIT_CONFIG_NOSYSTEM": "1",
                "HOME": str(self._paths.data),
                "LC_ALL": "C",
            }
        )
        return env

    async def _git(self, args: list[str], cwd: Path | None = None) -> str:
        cwd = cwd or self._paths.repo_dir
        _LOGGER.debug("git %s", " ".join(args))
        process = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=str(cwd),
            env=self._env(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        out = stdout.decode("utf-8", "replace")
        err = stderr.decode("utf-8", "replace")
        if process.returncode != 0:
            raise self._explain(args, err or out)
        return out

    def _explain(self, args: list[str], output: str) -> GitError:
        """Turn raw git/ssh output into something a household user can act on."""
        command = f"git {args[0]}"
        hint = ""
        lowered = output.lower()

        if "permission denied (publickey" in lowered:
            hint = (
                "The remote rejected our SSH key. Open the Domácí manuál panel, "
                "copy the public key it shows, and add it to the documentation "
                "repository under Settings -> Deploy keys (read-only is enough). "
                "Deploy keys are per-repository: a key added to a different "
                "repository will not work."
            )
        elif (
            "host key verification failed" in lowered
            or "no matching host key" in lowered
        ):
            hint = (
                "The SSH host key of the server is not trusted. For a host other "
                "than github.com, add its host key to the 'extra_known_hosts' "
                "option (output of `ssh-keyscan <host>`), or set "
                "'strict_host_key_checking' to false to trust it on first use."
            )
        elif (
            "repository not found" in lowered
            or "does not appear to be a git repository" in lowered
        ):
            hint = (
                f"'{self._options.repository}' was not found. Check the URL, and "
                "make sure the deploy key belongs to that exact repository."
            )
        elif "could not resolve hostname" in lowered or "connection timed out" in lowered:
            hint = "The Git host could not be reached. Check network and DNS."
        elif "remote branch" in lowered and "not found" in lowered:
            hint = (
                f"Branch '{self._options.branch}' does not exist on the remote. "
                "Set the 'branch' option to an existing branch."
            )
        elif "terminal prompts disabled" in lowered or "authentication failed" in lowered:
            hint = (
                "The remote asked for a username and password. Use an SSH URL "
                "(git@github.com:you/repo.git) with a deploy key instead."
            )

        return GitError(f"{command} failed", hint=hint, output=output)
