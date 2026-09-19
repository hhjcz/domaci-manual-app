import json

import pytest

from domaci_manual.config import ConfigError, Options


def test_defaults_are_a_usable_shape():
    options = Options()
    assert options.branch == "main"
    assert options.sync_interval_seconds == 900


@pytest.mark.parametrize(
    "url",
    [
        "git@github.com:you/domaci-manual.git",
        "ssh://git@github.com/you/domaci-manual.git",
        "https://github.com/you/domaci-manual.git",
        "file:///srv/docs.git",
    ],
)
def test_accepts_supported_urls(url):
    Options(repository=url).validate()


@pytest.mark.parametrize("url", ["", "github.com/you/repo", "you/repo"])
def test_rejects_unusable_urls(url):
    with pytest.raises(ConfigError):
        Options(repository=url).validate()


def test_detects_ssh_urls():
    assert Options(repository="git@github.com:you/repo.git").uses_ssh
    assert Options(repository="ssh://git@github.com/you/repo.git").uses_ssh
    assert not Options(repository="https://github.com/you/repo.git").uses_ssh


@pytest.mark.parametrize("subdir", ["/etc", "../outside", "docs/../../etc"])
def test_rejects_escaping_docs_subdir(subdir):
    with pytest.raises(ConfigError, match="docs_subdir"):
        Options(repository="git@github.com:you/repo.git", docs_subdir=subdir).validate()


def test_rejects_unknown_log_level():
    with pytest.raises(ConfigError, match="log_level"):
        Options(repository="git@github.com:you/repo.git", log_level="loud").validate()


def test_from_mapping_normalises_input():
    options = Options.from_mapping(
        {
            "repository": "  git@github.com:you/repo.git  ",
            "docs_subdir": "/docs/",
            "sync_interval": "30",
            "extra_known_hosts": ["  example.com ssh-ed25519 AAAA  ", ""],
            "log_level": "DEBUG",
        }
    )
    assert options.repository == "git@github.com:you/repo.git"
    assert options.docs_subdir == "docs"
    assert options.sync_interval == 30
    assert options.extra_known_hosts == ("example.com ssh-ed25519 AAAA",)
    assert options.log_level == "debug"


def test_missing_options_file_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError, match="does not exist"):
        Options.load(tmp_path / "nope.json")


def test_malformed_options_file_is_a_config_error(tmp_path):
    bad = tmp_path / "options.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError, match="valid JSON"):
        Options.load(bad)


def test_load_round_trip(tmp_path):
    path = tmp_path / "options.json"
    path.write_text(json.dumps({"repository": "git@github.com:you/repo.git"}))
    assert Options.load(path).repository == "git@github.com:you/repo.git"


def test_exclude_patterns_are_normalised():
    options = Options.from_mapping(
        {
            "repository": "git@github.com:you/repo.git",
            "exclude": ["  drafts/ ", "", "*.tmp"],
        }
    )
    assert options.exclude == ("drafts/", "*.tmp")


def test_exclude_accepts_a_bare_string():
    assert Options.from_mapping({"exclude": "drafts/"}).exclude == ("drafts/",)


def test_exclude_defaults_to_nothing():
    assert Options().exclude == ()
