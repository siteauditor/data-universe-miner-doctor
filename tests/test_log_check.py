"""Log scanning: pattern detection + secret redaction in excerpts."""

from __future__ import annotations

from du_doctor.checks.base import RunContext
from du_doctor.checks.log_check import LogCheck
from du_doctor.config import load_config
from du_doctor.models import CheckStatus


def _run_log_check(tmp_path, log_text: str):
    log_file = tmp_path / "miner.log"
    log_file.write_text(log_text, encoding="utf-8")
    cfg = load_config()  # full default patterns
    cfg.log_paths = [str(tmp_path)]
    ctx = RunContext()
    return LogCheck(cfg, ctx).run(), ctx


def test_detects_critical_pattern(tmp_path):
    results, _ = _run_log_check(
        tmp_path,
        "INFO starting miner\nTraceback (most recent call last):\n  File ...\n",
    )
    crit = [r for r in results if r.status == CheckStatus.CRITICAL]
    assert crit, "expected a CRITICAL log result"
    assert any("traceback" in r.details.get("patterns", []) for r in crit)


def test_detects_warning_pattern_and_sets_context(tmp_path):
    results, ctx = _run_log_check(
        tmp_path,
        "WARN reddit rate limit exceeded, retrying\n",
    )
    warn = [r for r in results if r.status == CheckStatus.WARNING]
    assert warn, "expected a WARNING log result"
    patterns = warn[0].details.get("patterns", [])
    assert "rate limit" in patterns
    assert ctx.get("rate_limited") is True


def test_secrets_are_redacted_in_excerpts(tmp_path):
    results, _ = _run_log_check(
        tmp_path,
        "ERROR rate limit hit while using APIFY_API_TOKEN=apify_api_supersecret123\n",
    )
    warn = [r for r in results if r.status == CheckStatus.WARNING]
    assert warn
    joined = "\n".join(warn[0].evidence)
    assert "apify_api_supersecret123" not in joined
    assert "REDACTED" in joined


def test_no_logs_is_skipped(tmp_path):
    cfg = load_config()
    cfg.log_paths = [str(tmp_path / "does_not_exist")]
    results = LogCheck(cfg, RunContext()).run()
    assert len(results) == 1
    assert results[0].status == CheckStatus.SKIPPED
