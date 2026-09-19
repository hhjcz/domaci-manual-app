import stat

import pytest

from domaci_manual.config import ConfigError, Options
from domaci_manual.ssh import (
    SOURCE_CONFIG_FILE,
    SOURCE_GENERATED,
    SOURCE_OPTION,
    prepare,
)


def test_generates_its_own_key_when_none_supplied(paths):
    credentials = prepare(Options(repository="git@github.com:you/repo.git"), paths)

    assert credentials.source == SOURCE_GENERATED
    assert credentials.public_key.startswith("ssh-ed25519 ")
    assert credentials.key_path.exists()
    assert stat.S_IMODE(credentials.key_path.stat().st_mode) == 0o600


def test_generated_key_is_stable_across_restarts(paths):
    options = Options(repository="git@github.com:you/repo.git")
    first = prepare(options, paths)
    second = prepare(options, paths)
    assert first.public_key == second.public_key


def test_supplied_key_file_wins(paths):
    generated = prepare(Options(repository="git@github.com:you/repo.git"), paths)
    supplied = generated.key_path.read_text(encoding="utf-8")
    (paths.addon_config / "deploy_key").write_text(supplied, encoding="utf-8")

    credentials = prepare(Options(repository="git@github.com:you/repo.git"), paths)
    assert credentials.source == SOURCE_CONFIG_FILE
    assert credentials.public_key == generated.public_key


def test_inline_key_option_wins_over_file(paths):
    generated = prepare(Options(repository="git@github.com:you/repo.git"), paths)
    material = generated.key_path.read_text(encoding="utf-8")

    credentials = prepare(
        # Without the trailing newline, to prove it is restored.
        Options(repository="git@github.com:you/repo.git", deploy_key=material.strip()),
        paths,
    )
    assert credentials.source == SOURCE_OPTION
    assert credentials.public_key == generated.public_key
    assert credentials.key_path.read_text(encoding="utf-8").endswith("\n")


def test_unreadable_key_gives_an_actionable_error(paths):
    with pytest.raises(ConfigError, match="unencrypted OpenSSH private key"):
        prepare(
            Options(repository="git@github.com:you/repo.git", deploy_key="not a key"),
            paths,
        )


def test_known_hosts_contains_github_and_extras(paths):
    credentials = prepare(
        Options(
            repository="git@github.com:you/repo.git",
            extra_known_hosts=("git.example.com ssh-ed25519 AAAAtest",),
        ),
        paths,
    )
    content = credentials.known_hosts_path.read_text(encoding="utf-8")
    assert "github.com ssh-ed25519 " in content
    assert "git.example.com ssh-ed25519 AAAAtest" in content


def test_git_ssh_command_is_locked_down(paths):
    credentials = prepare(Options(repository="git@github.com:you/repo.git"), paths)
    command = credentials.git_ssh_command
    assert "IdentitiesOnly=yes" in command
    assert "BatchMode=yes" in command
    assert "StrictHostKeyChecking=yes" in command
    assert str(credentials.known_hosts_path) in command


def test_strict_host_key_checking_off_accepts_new_hosts(paths):
    credentials = prepare(
        Options(
            repository="git@github.com:you/repo.git", strict_host_key_checking=False
        ),
        paths,
    )
    assert "StrictHostKeyChecking=accept-new" in credentials.git_ssh_command
