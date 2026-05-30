"""Data model construction + serialisation."""

from __future__ import annotations

from datetime import datetime

from du_doctor.models import (
    CheckCategory,
    CheckResult,
    CheckStatus,
    DoctorConfig,
    DoctorReport,
)


def test_check_result_defaults():
    r = CheckResult(
        id="pm2_process",
        title="PM2 miner process",
        category=CheckCategory.PROCESS,
        status=CheckStatus.CRITICAL,
        summary="Miner process is not running",
    )
    assert r.details == {}
    assert r.evidence == []
    assert r.suggested_fixes == []
    assert isinstance(r.timestamp, datetime)


def test_enums_are_string_valued():
    assert CheckStatus.CRITICAL.value == "CRITICAL"
    assert CheckCategory.DATA_UNIVERSE_CONFIG.value == "DATA_UNIVERSE_CONFIG"


def test_doctor_config_defaults():
    cfg = DoctorConfig()
    assert cfg.netuid == 13
    assert cfg.network == "finney"
    assert cfg.miner_process_name == "miner.py"
    assert cfg.miner_port is None
    assert "./logs" in cfg.log_paths
    assert cfg.thresholds.incentive_drop_percent == 25


def test_report_round_trips_via_json_mode():
    report = DoctorReport(
        overall_status=CheckStatus.WARNING,
        subnet_name="Data Universe",
        netuid=13,
        network="finney",
        hotkey_masked="5F3abc...XyZ921",
        checks=[
            CheckResult(
                id="disk",
                title="Disk usage",
                category=CheckCategory.SYSTEM,
                status=CheckStatus.OK,
                summary="40% used",
            )
        ],
        suggested_fix_order=["do the thing"],
    )
    dumped = report.model_dump(mode="json")
    assert dumped["overall_status"] == "WARNING"
    assert dumped["checks"][0]["status"] == "OK"
    assert isinstance(dumped["created_at"], str)

    # Re-validate from the dumped dict.
    restored = DoctorReport.model_validate(dumped)
    assert restored.netuid == 13
    assert restored.checks[0].id == "disk"
