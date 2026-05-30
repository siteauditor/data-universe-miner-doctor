"""JSON reporter: valid JSON + stable schema."""

from __future__ import annotations

import json

from du_doctor.models import CheckCategory, CheckResult, CheckStatus, DoctorReport
from du_doctor.reporters.json_reporter import render_json, report_to_dict


def _sample_report() -> DoctorReport:
    return DoctorReport(
        overall_status=CheckStatus.CRITICAL,
        subnet_name="Data Universe",
        netuid=13,
        network="finney",
        hotkey_masked="5F3abc...XyZ921",
        checks=[
            CheckResult(
                id="pm2_process",
                title="PM2 miner process",
                category=CheckCategory.PROCESS,
                status=CheckStatus.CRITICAL,
                summary="Miner process is not running",
            )
        ],
        suggested_fix_order=["Start the miner process"],
    )


def test_render_json_is_valid_and_parseable():
    text = render_json(_sample_report())
    data = json.loads(text)
    assert data["overall_status"] == "CRITICAL"
    assert data["subnet_name"] == "Data Universe"
    assert data["netuid"] == 13
    assert data["network"] == "finney"
    assert data["hotkey_masked"] == "5F3abc...XyZ921"
    assert isinstance(data["checks"], list)


def test_json_check_schema_matches_spec():
    data = report_to_dict(_sample_report())
    check = data["checks"][0]
    for key in (
        "id",
        "title",
        "category",
        "status",
        "summary",
        "details",
        "evidence",
        "suggested_fixes",
        "timestamp",
    ):
        assert key in check
    assert check["category"] == "PROCESS"
    assert check["status"] == "CRITICAL"
    assert isinstance(check["details"], dict)
    assert isinstance(check["evidence"], list)


def test_created_at_serialised_as_string():
    data = report_to_dict(_sample_report())
    assert isinstance(data["created_at"], str)


def _report_with_full_hotkey() -> DoctorReport:
    report = _sample_report()
    # A realistic full ss58 (matches the ss58 redaction regex).
    report.hotkey_masked = "5F3sa2TJAZ1jZsd8Z3kn1xpcyd2pHnY1Gh8M2KjQ9F3abcde"
    return report


def test_full_hotkey_is_remasked_by_default():
    # Without opting in, the public ss58 is masked by the blanket redaction.
    data = report_to_dict(_report_with_full_hotkey())
    assert data["hotkey_masked"] == "5F3sa2...3abcde"


def test_show_full_hotkey_preserves_headline_field():
    # Explicit opt-in (mirrors the terminal reporter / --unsafe-show-full-hotkey).
    full = "5F3sa2TJAZ1jZsd8Z3kn1xpcyd2pHnY1Gh8M2KjQ9F3abcde"
    data = report_to_dict(_report_with_full_hotkey(), show_full_hotkey=True)
    assert data["hotkey_masked"] == full
    # And it round-trips through render_json.
    assert full in render_json(_report_with_full_hotkey(), show_full_hotkey=True)
