"""Base class shared by every check.

Design goals:
  * A check NEVER crashes the run. ``safe_run`` wraps ``run`` and converts any
    unexpected exception into a single CRITICAL ``CheckResult``.
  * Checks can share information through a mutable ``RunContext`` (e.g. the
    bittensor check publishes axon info that the network check consumes, and
    several checks contribute to the snapshot the runner saves at the end).
"""

from __future__ import annotations

from typing import Any, Optional

from du_doctor.models import (
    CheckCategory,
    CheckResult,
    CheckStatus,
    DoctorConfig,
)


class RunContext:
    """Mutable scratch space passed to every check during a single run.

    Notable keys populated by checks:
      * ``previous_snapshot`` (dict | None) — set by the runner before checks.
      * ``snapshot`` (dict) — accumulated current values to persist at the end.
      * ``axon`` (dict | None) — advertised axon info from the metagraph.
      * ``findings`` (dict) — booleans/values that the scoring heuristic reads
        (e.g. ``rate_limited``, ``no_data_scraped``, ``stale_data``,
        ``credentials_missing``, ``pm2_restart_count``).
    """

    def __init__(self, previous_snapshot: Optional[dict] = None) -> None:
        self.previous_snapshot: Optional[dict] = previous_snapshot
        self.snapshot: dict[str, Any] = {}
        self.axon: Optional[dict] = None
        self.findings: dict[str, Any] = {}

    def note(self, key: str, value: Any) -> None:
        self.findings[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.findings.get(key, default)


class BaseCheck:
    """Subclass and implement :meth:`run`."""

    #: Stable category for all results this check produces.
    category: CheckCategory = CheckCategory.SYSTEM
    #: Human-friendly name used in the failure wrapper.
    name: str = "check"

    def __init__(self, config: DoctorConfig, context: RunContext) -> None:
        self.config = config
        self.ctx = context

    # --- to be implemented by subclasses ---------------------------------- #
    def run(self) -> list[CheckResult]:  # pragma: no cover - abstract
        raise NotImplementedError

    # --- helpers ---------------------------------------------------------- #
    def result(
        self,
        id: str,
        title: str,
        status: CheckStatus,
        summary: str,
        details: Optional[dict] = None,
        evidence: Optional[list[str]] = None,
        suggested_fixes: Optional[list[str]] = None,
        category: Optional[CheckCategory] = None,
    ) -> CheckResult:
        """Construct a ``CheckResult`` with this check's category as default."""
        return CheckResult(
            id=id,
            title=title,
            category=category or self.category,
            status=status,
            summary=summary,
            details=details or {},
            evidence=evidence or [],
            suggested_fixes=suggested_fixes or [],
        )

    def safe_run(self) -> list[CheckResult]:
        """Run the check, converting any unexpected error into a result."""
        try:
            results = self.run()
            # Guard against a buggy check returning nothing.
            return results if results else []
        except Exception as exc:  # noqa: BLE001 - resilience is the whole point
            return [
                self.result(
                    id=f"{self.name}_error",
                    title=f"{self.name} (internal error)",
                    status=CheckStatus.CRITICAL,
                    summary=f"Check '{self.name}' failed unexpectedly: {exc}",
                    details={"exception": type(exc).__name__, "message": str(exc)},
                    suggested_fixes=[
                        "This is a bug in du-doctor, not necessarily your miner.",
                        "Re-run with --verbose and please report the traceback.",
                    ],
                )
            ]
