"""Overall status aggregation rules."""

from __future__ import annotations

from du_doctor.models import (
    CheckCategory,
    CheckResult,
    CheckStatus,
    aggregate_status,
    overall_status_for,
)


def _r(status: CheckStatus) -> CheckResult:
    return CheckResult(id="x", title="x", category=CheckCategory.SYSTEM, status=status, summary="x")


def test_critical_wins_over_warning():
    assert aggregate_status([CheckStatus.WARNING, CheckStatus.CRITICAL]) == CheckStatus.CRITICAL
    assert aggregate_status([CheckStatus.CRITICAL, CheckStatus.OK]) == CheckStatus.CRITICAL


def test_warning_wins_over_ok():
    assert aggregate_status([CheckStatus.OK, CheckStatus.WARNING]) == CheckStatus.WARNING


def test_skipped_does_not_make_overall_warning():
    assert aggregate_status([CheckStatus.OK, CheckStatus.SKIPPED]) == CheckStatus.OK
    # Skipped alongside warning is ignored (warning still wins, not escalated).
    assert aggregate_status([CheckStatus.SKIPPED, CheckStatus.WARNING]) == CheckStatus.WARNING


def test_all_skipped_or_empty_is_ok():
    assert aggregate_status([CheckStatus.SKIPPED, CheckStatus.SKIPPED]) == CheckStatus.OK
    assert aggregate_status([]) == CheckStatus.OK


def test_overall_status_for_results():
    results = [_r(CheckStatus.OK), _r(CheckStatus.SKIPPED), _r(CheckStatus.WARNING)]
    assert overall_status_for(results) == CheckStatus.WARNING
