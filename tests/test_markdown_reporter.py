"""Markdown reporter: structure + secret redaction + file writing."""

from __future__ import annotations

from du_doctor.models import CheckCategory, CheckResult, CheckStatus, DoctorReport
from du_doctor.reporters.markdown_reporter import render_markdown, write_markdown


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
                suggested_fixes=["pm2 start python -- ./neurons/miner.py ..."],
            ),
            CheckResult(
                id="logs_warning",
                title="Logs (warning patterns)",
                category=CheckCategory.LOGS,
                status=CheckStatus.WARNING,
                summary="rate limit found",
                evidence=["miner.log: rate limit APIFY_API_TOKEN=apify_api_supersecret"],
            ),
        ],
        suggested_fix_order=["Start the miner process"],
    )


def test_render_markdown_contains_sections():
    md = render_markdown(_sample_report())
    assert "# Data Universe Miner Doctor Report" in md
    assert "NETUID 13" in md
    assert "5F3abc...XyZ921" in md
    assert "## Summary" in md
    assert "## Detailed checks" in md
    assert "## Suggested fixes (in priority order)" in md
    assert "PM2 miner process" in md


def test_render_markdown_redacts_secrets():
    md = render_markdown(_sample_report())
    assert "apify_api_supersecret" not in md
    assert "REDACTED" in md


def test_write_markdown_creates_file(tmp_path):
    out = write_markdown(_sample_report(), tmp_path / "report.md")
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert content.startswith("# Data Universe Miner Doctor Report")
