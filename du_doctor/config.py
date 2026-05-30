"""Configuration: defaults, file location, ``init`` writing, and loading.

The on-disk config lives at ``~/.du-doctor/config.yaml``. CLI flags can override
any of the commonly-tweaked fields at run time without rewriting the file.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml

from du_doctor.models import DoctorConfig

CONFIG_DIR_ENV = "DU_DOCTOR_HOME"


def get_config_dir() -> Path:
    """Directory holding config + snapshots (``~/.du-doctor`` by default).

    Overridable via the ``DU_DOCTOR_HOME`` env var (handy for tests / CI).
    """
    override = os.environ.get(CONFIG_DIR_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".du-doctor"


def get_config_path() -> Path:
    return get_config_dir() / "config.yaml"


def get_snapshots_path() -> Path:
    return get_config_dir() / "snapshots.json"


def default_config_dict() -> dict[str, Any]:
    """The default config as a plain dict (also what ``init`` writes to disk)."""
    return {
        "netuid": 13,
        "network": "finney",
        "subnet_name": "Data Universe",
        "subnet_repo_url": "https://github.com/macrocosm-os/data-universe",
        "hotkey_ss58": "",
        "wallet_name": "",
        "wallet_hotkey_name": "",
        "subnet_repo_path": "",
        "miner_process_name": "miner.py",
        "pm2_process_name": "",
        "miner_port": None,
        "log_paths": ["./logs", "./pm2.log", "~/.pm2/logs"],
        "data_paths": ["./data", "./database", "./storage", "./local_storage"],
        "scraping_config_path": "./scraping_config.json",
        "env_path": "./.env",
        "check_interval_seconds": 300,
        "thresholds": {
            "incentive_drop_percent": 25,
            "emission_drop_percent": 25,
            "rank_drop_percent": 25,
            "disk_usage_warning_percent": 85,
            "ram_usage_warning_percent": 85,
            "cpu_usage_warning_percent": 90,
            "stale_data_warning_hours": 24,
            "stale_data_critical_hours": 72,
            "pm2_restart_warning_count": 5,
            "repo_behind_warning_commits": 3,
            "repo_behind_critical_commits": 15,
        },
        "data_universe": {
            "requires_gpu": False,
            "required_python_version": ">=3.10",
            "expected_files": [
                "neurons/miner.py",
                "requirements.txt",
                "README.md",
            ],
            "expected_optional_files": [
                "scraping_config.json",
                ".env",
            ],
            "scraper_credentials": {
                "apify": {
                    "enabled_if_config_contains": ["apify", "Apify"],
                    "required_env_names": ["APIFY_API_TOKEN", "APIFY_TOKEN"],
                },
                "reddit": {
                    "enabled_if_config_contains": ["reddit", "Reddit"],
                    "required_env_names": [
                        "REDDIT_CLIENT_ID",
                        "REDDIT_CLIENT_SECRET",
                        "REDDIT_USERNAME",
                        "REDDIT_PASSWORD",
                    ],
                },
            },
            "known_error_patterns": {
                "critical": [
                    "hotkey not registered",
                    "not registered",
                    "cannot connect to subtensor",
                    "failed to serve axon",
                    "address already in use",
                    "permission denied",
                    "no module named",
                    "traceback",
                    "database is locked",
                    "sqlite database is locked",
                    "invalid signature",
                    "authentication failed",
                    "invalid apify token",
                    "reddit authentication failed",
                    "out of disk",
                    "no space left on device",
                ],
                "warning": [
                    "timeout",
                    "retrying",
                    "rate limit",
                    "too many requests",
                    "deprecated",
                    "no data scraped",
                    "empty response",
                    "validator rejected",
                    "stale",
                    "upload failed",
                    "miner index",
                    "storage upload",
                    "s3 upload",
                ],
            },
        },
    }


# Mapping of CLI override keyword -> config field name.
_CLI_FIELD_MAP = {
    "netuid": "netuid",
    "network": "network",
    "hotkey": "hotkey_ss58",
    "wallet_name": "wallet_name",
    "wallet_hotkey": "wallet_hotkey_name",
    "repo_path": "subnet_repo_path",
    "scraping_config": "scraping_config_path",
    "env_path": "env_path",
    "pm2_process_name": "pm2_process_name",
    "miner_process_name": "miner_process_name",
    "miner_port": "miner_port",
}


def apply_cli_overrides(data: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``data`` with non-None CLI overrides applied."""
    merged = dict(data)
    for key, value in (overrides or {}).items():
        if value is None:
            continue
        field = _CLI_FIELD_MAP.get(key, key)
        merged[field] = value
    return merged


def init_config(
    path: Optional[Path] = None,
    force: bool = False,
    overrides: Optional[dict[str, Any]] = None,
) -> tuple[Path, bool]:
    """Create the default config file.

    Returns ``(path, created)`` where ``created`` is False if the file already
    existed and ``force`` was not set (the file is left untouched in that case).
    """
    path = path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists() and not force:
        return path, False

    data = apply_cli_overrides(default_config_dict(), overrides or {})
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, default_flow_style=False, allow_unicode=True)
    return path, True


def load_config(
    path: Optional[Path] = None,
    cli_overrides: Optional[dict[str, Any]] = None,
    profile=None,
) -> DoctorConfig:
    """Load config from disk (or defaults if absent) and apply CLI overrides.

    ``profile`` (a ``SubnetProfile``) supplies the default config base; ``None``
    uses the built-in Data Universe defaults. Never raises on a missing file.
    """
    path = path or get_config_path()

    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}
        except Exception:  # noqa: BLE001 - corrupt YAML -> fall back to defaults
            raw = {}
    else:
        raw = {}

    base = profile.build_default_config() if profile is not None else default_config_dict()
    merged = _deep_merge(base, raw)
    merged = apply_cli_overrides(merged, cli_overrides or {})
    try:
        return DoctorConfig.model_validate(merged)
    except Exception:  # noqa: BLE001 - malformed value(s) in the file
        # Never crash on a bad config: fall back to defaults plus the (typed)
        # CLI overrides so the run can still proceed.
        safe = apply_cli_overrides(dict(base), cli_overrides or {})
        return DoctorConfig.model_validate(safe)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` onto ``base`` (override wins).

    A ``None`` override value is ignored (keeps the base default). This makes an
    empty YAML key like ``thresholds:`` harmless instead of a validation error.
    """
    result = dict(base)
    for key, value in (override or {}).items():
        if value is None:
            continue
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
