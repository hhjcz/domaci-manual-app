"""Guard rails on the add-on manifest.

These are cheap checks for things that silently break the app in Home
Assistant but look fine in a diff.
"""

from __future__ import annotations

import dataclasses

import yaml

import domaci_manual
from conftest import REPO_ROOT
from domaci_manual.config import Options

ADDON_DIR = REPO_ROOT / "domaci_manual"


def load(name: str) -> dict:
    return yaml.safe_load((ADDON_DIR / name).read_text(encoding="utf-8"))


def test_manifest_version_matches_the_package():
    assert load("config.yaml")["version"] == domaci_manual.__version__


def test_changelog_documents_the_current_version():
    changelog = (ADDON_DIR / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## {domaci_manual.__version__}" in changelog


def test_every_option_has_a_schema_entry():
    config = load("config.yaml")
    assert sorted(config["options"]) == sorted(config["schema"])


def test_every_option_is_described_for_the_user():
    config = load("config.yaml")
    translations = load("translations/en.yaml")["configuration"]
    assert sorted(translations) == sorted(config["options"])
    for name, entry in translations.items():
        assert entry["name"], name
        assert entry["description"], name


def test_manifest_defaults_match_the_code_defaults():
    """Otherwise the UI and the app disagree about what "default" means."""
    manifest = load("config.yaml")["options"]
    parsed = Options.from_mapping(manifest)
    defaults = Options()

    for field in ("branch", "sync_interval", "site_name", "language", "log_level"):
        assert getattr(parsed, field) == getattr(defaults, field), field
    assert parsed.strict_host_key_checking is defaults.strict_host_key_checking


def test_default_options_only_fail_on_the_missing_repository():
    options = Options.from_mapping(load("config.yaml")["options"])
    assert options.repository == ""
    # Everything else must already be valid out of the box.
    dataclasses.replace(options, repository="git@github.com:you/repo.git").validate()


def test_ingress_only_and_minimally_privileged():
    config = load("config.yaml")

    assert config["ingress"] is True
    assert config["ingress_port"] == 8099
    # A published port would bypass Home Assistant authentication entirely.
    assert "ports" not in config
    # The household, not just administrators, needs to read the manual.
    assert config["panel_admin"] is False
    # s6-overlay from the base image is the init system.
    assert config["init"] is False

    for privilege in (
        "hassio_api",
        "homeassistant_api",
        "auth_api",
        "docker_api",
        "host_network",
        "host_pid",
        "host_dbus",
        "privileged",
        "full_access",
        "devices",
    ):
        assert privilege not in config, privilege


def test_only_the_addon_config_directory_is_mapped_and_read_only():
    mappings = load("config.yaml")["map"]
    assert mappings == [{"type": "addon_config", "read_only": True}]


def test_build_targets_the_documented_architectures():
    config = load("config.yaml")
    build = load("build.yaml")
    assert sorted(config["arch"]) == ["aarch64", "amd64"]
    assert sorted(build["build_from"]) == sorted(config["arch"])
    for image in build["build_from"].values():
        assert image.startswith("ghcr.io/home-assistant/")
        # Pinned, not :latest.
        assert ":" in image.rsplit("/", 1)[-1]
        assert not image.endswith(":latest")
