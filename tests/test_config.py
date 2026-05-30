"""Config loading, defaults, file round-trip, and CLI override behaviour."""

from __future__ import annotations

import yaml

from du_doctor.config import (
    apply_cli_overrides,
    default_config_dict,
    get_config_path,
    init_config,
    load_config,
)


def test_default_config_has_data_universe_defaults():
    data = default_config_dict()
    assert data["netuid"] == 13
    assert data["network"] == "finney"
    assert data["subnet_name"] == "Data Universe"
    patterns = data["data_universe"]["known_error_patterns"]
    assert "traceback" in patterns["critical"]
    assert "rate limit" in patterns["warning"]


def test_load_config_without_file_uses_defaults():
    cfg = load_config()  # no file exists in the isolated home
    assert cfg.netuid == 13
    assert cfg.network == "finney"
    # Patterns from default_config_dict must be merged into the model.
    assert "traceback" in cfg.data_universe.known_error_patterns.critical
    assert cfg.data_universe.scraper_credentials["apify"].required_env_names


def test_load_config_reads_yaml_overrides(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"netuid": 99, "network": "test"}), encoding="utf-8")
    cfg = load_config(path)
    assert cfg.netuid == 99
    assert cfg.network == "test"
    # Unspecified fields still come from defaults.
    assert cfg.subnet_name == "Data Universe"
    assert "traceback" in cfg.data_universe.known_error_patterns.critical


def test_cli_overrides_win_over_file(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"netuid": 13, "hotkey_ss58": "fromfile"}), encoding="utf-8")
    cfg = load_config(path, cli_overrides={"hotkey": "fromcli", "netuid": 7})
    assert cfg.hotkey_ss58 == "fromcli"
    assert cfg.netuid == 7


def test_apply_cli_overrides_ignores_none():
    base = {"netuid": 13, "hotkey_ss58": "keep"}
    merged = apply_cli_overrides(base, {"hotkey": None, "netuid": 21})
    assert merged["hotkey_ss58"] == "keep"
    assert merged["netuid"] == 21


def test_init_config_creates_then_respects_existing():
    path, created = init_config()
    assert created is True
    assert path == get_config_path()
    assert path.exists()

    # Second call without --force should not overwrite.
    _, created_again = init_config()
    assert created_again is False

    # With force it rewrites.
    _, forced = init_config(force=True)
    assert forced is True


def test_init_config_applies_overrides():
    path, _ = init_config(overrides={"hotkey": "5ABC", "repo_path": "/opt/data-universe"})
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["hotkey_ss58"] == "5ABC"
    assert data["subnet_repo_path"] == "/opt/data-universe"
