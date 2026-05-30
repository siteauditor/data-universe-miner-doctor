"""HTML reporter + support bundle: structure, redaction, file/zip writing."""

from __future__ import annotations

import json
import zipfile

from du_doctor.models import CheckCategory, CheckResult, CheckStatus, DoctorReport
from du_doctor.reporters.bundle import write_bundle
from du_doctor.reporters.html_reporter import render_html, write_html

SECRET = "apify_api_supersecret"


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
                summary=f"rate limit APIFY_API_TOKEN={SECRET}",
                evidence=[f"miner.log: <script> rate limit APIFY_API_TOKEN={SECRET}"],
            ),
        ],
        suggested_fix_order=["Start the miner process"],
    )


def test_render_html_structure():
    out = render_html(_sample_report())
    assert out.startswith("<!doctype html>")
    assert "Data Universe Miner Doctor Report" in out
    assert "NETUID 13" in out
    assert "5F3abc...XyZ921" in out
    assert "PM2 miner process" in out
    assert "Suggested fixes" in out


def test_render_html_redacts_and_escapes():
    out = render_html(_sample_report())
    assert SECRET not in out  # secret redacted
    assert "REDACTED" in out
    assert "<script>" not in out  # HTML-escaped
    assert "&lt;script&gt;" in out


def test_write_html_creates_file(tmp_path):
    out = write_html(_sample_report(), tmp_path / "r.html")
    assert out.exists()
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_bundle_contains_all_formats_and_is_redacted(tmp_path):
    zpath = write_bundle(
        _sample_report(),
        tmp_path / "bundle.zip",
        extra_files={"config-env-names.txt": "APIFY_API_TOKEN\nREDDIT_CLIENT_ID"},
    )
    assert zpath.exists()
    with zipfile.ZipFile(zpath) as zf:
        names = set(zf.namelist())
        assert {
            "du-doctor-report.json",
            "du-doctor-report.md",
            "du-doctor-report.html",
            "config-env-names.txt",
        } <= names
        blob = "".join(zf.read(n).decode("utf-8") for n in names)
        assert SECRET not in blob  # no secret in any bundled artifact
        # The JSON is a valid serialized report.
        d = json.loads(zf.read("du-doctor-report.json"))
        assert d["netuid"] == 13
        # env-names file holds NAMES only (no values).
        env_txt = zf.read("config-env-names.txt").decode("utf-8")
        assert "APIFY_API_TOKEN" in env_txt
