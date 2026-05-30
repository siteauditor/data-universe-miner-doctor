"""Terminal reporter: it must render every status mix without crashing,
and must still redact secrets that slipped into evidence."""

from __future__ import annotations

from rich.console import Console

from du_doctor.models import CheckCategory, CheckResult, CheckStatus, DoctorReport
from du_doctor.reporters.terminal_reporter import render_terminal


def _report(statuses) -> DoctorReport:
    checks = []
    for i, status in enumerate(statuses):
        checks.append(
            CheckResult(
                id=f"c{i}",
                title=f"Check {i}",
                category=list(CheckCategory)[i % len(CheckCategory)],
                status=status,
                summary=f"summary {i}",
                evidence=["rate limit APIFY_API_TOKEN=apify_api_supersecret123"],
                suggested_fixes=["do the thing"],
            )
        )
    return DoctorReport(
        overall_status=CheckStatus.CRITICAL,
        subnet_name="Data Universe",
        netuid=13,
        network="finney",
        hotkey_masked="5F3abc...XyZ921",
        checks=checks,
        suggested_fix_order=["Start the miner process", "Add Apify token"],
    )


def _render_to_text(report: DoctorReport, verbose: bool = False) -> str:
    # record=True lets us capture the rendered output as plain text.
    console = Console(record=True, width=100, legacy_windows=False, no_color=True)
    render_terminal(report, console=console, verbose=verbose)
    return console.export_text()


def test_terminal_reporter_does_not_crash_on_all_statuses():
    report = _report(
        [CheckStatus.OK, CheckStatus.WARNING, CheckStatus.CRITICAL, CheckStatus.SKIPPED]
    )
    out = _render_to_text(report)
    assert "Data Universe Miner Doctor" in out
    assert "Overall status" in out
    assert "Suggested fixes" in out


def test_terminal_reporter_verbose_does_not_crash():
    report = _report([CheckStatus.SKIPPED, CheckStatus.OK])
    out = _render_to_text(report, verbose=True)
    assert "Data Universe Miner Doctor" in out


def test_terminal_reporter_redacts_secrets_in_output():
    out = _render_to_text(_report([CheckStatus.WARNING]))
    assert "apify_api_supersecret123" not in out
    assert "REDACTED" in out


def test_terminal_reporter_handles_empty_report():
    report = DoctorReport(
        overall_status=CheckStatus.OK,
        subnet_name="Data Universe",
        netuid=13,
        network="finney",
        hotkey_masked=None,
        checks=[],
        suggested_fix_order=[],
    )
    out = _render_to_text(report)
    assert "Overall status" in out
