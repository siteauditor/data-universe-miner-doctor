"""Pydantic data models and the core status-aggregation logic.

Everything that flows through the tool — config, individual check results, and
the final report — is modelled here so that JSON output, markdown output, and
the terminal UI all share one schema.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    """Timezone-aware UTC timestamp (used as a Pydantic ``default_factory``)."""
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class CheckStatus(str, Enum):
    """Outcome of a single check.

    ``SKIPPED`` means the check could not run (e.g. SDK missing, path not
    configured). It deliberately does NOT count towards the overall status.
    """

    OK = "OK"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    SKIPPED = "SKIPPED"


class CheckCategory(str, Enum):
    """High-level grouping used for the report sections."""

    SYSTEM = "SYSTEM"
    BITTENSOR = "BITTENSOR"
    REPO = "REPO"
    PROCESS = "PROCESS"
    NETWORK = "NETWORK"
    LOGS = "LOGS"
    DATA_UNIVERSE_CONFIG = "DATA_UNIVERSE_CONFIG"
    DATA_UNIVERSE_DATA = "DATA_UNIVERSE_DATA"
    DATA_UNIVERSE_SCORING = "DATA_UNIVERSE_SCORING"


# --------------------------------------------------------------------------- #
# Config sub-models
# --------------------------------------------------------------------------- #
class Thresholds(BaseModel):
    """Tunable thresholds that decide WARNING vs CRITICAL for several checks."""

    incentive_drop_percent: float = 25
    emission_drop_percent: float = 25
    rank_drop_percent: float = 25
    disk_usage_warning_percent: float = 85
    ram_usage_warning_percent: float = 85
    cpu_usage_warning_percent: float = 90
    stale_data_warning_hours: float = 24
    stale_data_critical_hours: float = 72
    pm2_restart_warning_count: int = 5
    repo_behind_warning_commits: int = 3
    repo_behind_critical_commits: int = 15


class ScraperCredentialRule(BaseModel):
    """How to detect that a scraper is enabled and what env vars it needs."""

    enabled_if_config_contains: list[str] = Field(default_factory=list)
    required_env_names: list[str] = Field(default_factory=list)


class KnownErrorPatterns(BaseModel):
    """Substring patterns searched for in log files (case-insensitive)."""

    critical: list[str] = Field(default_factory=list)
    warning: list[str] = Field(default_factory=list)


class DataUniverseSettings(BaseModel):
    """Data Universe / SN13 specific knowledge baked into the config."""

    requires_gpu: bool = False
    required_python_version: str = ">=3.10"
    expected_files: list[str] = Field(
        default_factory=lambda: ["neurons/miner.py", "requirements.txt", "README.md"]
    )
    expected_optional_files: list[str] = Field(
        default_factory=lambda: ["scraping_config.json", ".env"]
    )
    scraper_credentials: dict[str, ScraperCredentialRule] = Field(default_factory=dict)
    known_error_patterns: KnownErrorPatterns = Field(default_factory=KnownErrorPatterns)


# --------------------------------------------------------------------------- #
# Top-level config
# --------------------------------------------------------------------------- #
class DoctorConfig(BaseModel):
    """Full configuration for a diagnostic run.

    Loaded from ``~/.du-doctor/config.yaml`` and optionally overridden by CLI
    flags. All fields have safe defaults so a run can proceed even with an
    empty/partial config.
    """

    netuid: int = 13
    network: str = "finney"
    subnet_name: str = "Data Universe"
    subnet_repo_url: str = "https://github.com/macrocosm-os/data-universe"

    hotkey_ss58: str = ""
    wallet_name: str = ""
    wallet_hotkey_name: str = ""

    subnet_repo_path: str = ""
    miner_process_name: str = "miner.py"
    pm2_process_name: str = ""
    miner_port: Optional[int] = None

    log_paths: list[str] = Field(default_factory=lambda: ["./logs", "./pm2.log", "~/.pm2/logs"])
    data_paths: list[str] = Field(
        default_factory=lambda: ["./data", "./database", "./storage", "./local_storage"]
    )

    scraping_config_path: str = "./scraping_config.json"
    env_path: str = "./.env"

    check_interval_seconds: int = 300

    thresholds: Thresholds = Field(default_factory=Thresholds)
    data_universe: DataUniverseSettings = Field(default_factory=DataUniverseSettings)


# --------------------------------------------------------------------------- #
# Result models
# --------------------------------------------------------------------------- #
class CheckResult(BaseModel):
    """The single unit every check returns.

    A check NEVER raises to the caller; on failure it returns a ``CheckResult``
    with ``status=CRITICAL`` (or ``SKIPPED``) explaining what went wrong.
    """

    id: str
    title: str
    category: CheckCategory
    status: CheckStatus
    summary: str
    details: dict = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)
    suggested_fixes: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=_utcnow)


class DoctorReport(BaseModel):
    """The complete diagnostic report produced by a single run."""

    overall_status: CheckStatus
    subnet_name: str
    netuid: int
    network: str
    hotkey_masked: Optional[str] = None
    checks: list[CheckResult] = Field(default_factory=list)
    suggested_fix_order: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)


# --------------------------------------------------------------------------- #
# Status aggregation
# --------------------------------------------------------------------------- #
_STATUS_RANK: dict[CheckStatus, int] = {
    CheckStatus.SKIPPED: 0,
    CheckStatus.OK: 1,
    CheckStatus.WARNING: 2,
    CheckStatus.CRITICAL: 3,
}


def aggregate_status(statuses: list[CheckStatus]) -> CheckStatus:
    """Roll many check statuses up into one overall status.

    Rules (per spec):
      * CRITICAL beats WARNING beats OK.
      * SKIPPED never raises the overall status (it is ignored).
      * If every check was SKIPPED (or there are none), the overall is OK.
    """
    relevant = [s for s in statuses if s != CheckStatus.SKIPPED]
    if not relevant:
        return CheckStatus.OK
    return max(relevant, key=lambda s: _STATUS_RANK[s])


def overall_status_for(checks: list[CheckResult]) -> CheckStatus:
    """Convenience wrapper that aggregates the status of a list of results."""
    return aggregate_status([c.status for c in checks])
