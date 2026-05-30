"""Log scanning for known Data Universe failure signatures.

Reads only the tail of each log (default 500 lines), never prints whole files,
and redacts secrets from every excerpt before it is shown or stored.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from du_doctor.checks.base import BaseCheck
from du_doctor.models import CheckCategory, CheckResult, CheckStatus
from du_doctor.utils.files import expand_paths, read_last_lines, recent_log_files
from du_doctor.utils.redact import redact_secrets

# Pattern-specific remediation hints (substring -> advice).
_FIX_HINTS: dict[str, str] = {
    "not registered": "Register the hotkey on subnet 13 (btcli) before mining.",
    "hotkey not registered": "Register the hotkey on subnet 13 (btcli) before mining.",
    "cannot connect to subtensor": "Check network/subtensor endpoint; the miner can't reach the chain.",
    "failed to serve axon": "Free the axon port / fix firewall so the axon can bind.",
    "address already in use": "Another process holds the axon port; stop it or change the port.",
    "permission denied": "Fix file/directory permissions for the miner user.",
    "no module named": "A Python dependency is missing — `pip install -r requirements.txt`.",
    "database is locked": "Ensure only one miner instance writes the DB; avoid concurrent runs.",
    "sqlite database is locked": "Ensure only one miner instance writes the DB; avoid concurrent runs.",
    "invalid apify token": "Set a valid APIFY_API_TOKEN in your .env.",
    "reddit authentication failed": "Re-check REDDIT_CLIENT_ID/SECRET/USERNAME/PASSWORD in .env.",
    "authentication failed": "A credential is wrong/expired — re-check your .env tokens.",
    "no space left on device": "Free disk space immediately; the miner cannot write data.",
    "out of disk": "Free disk space immediately; the miner cannot write data.",
    "rate limit": "Scraper is being throttled; reduce request cadence or rotate credentials.",
    "too many requests": "Scraper is being throttled; reduce request cadence or rotate credentials.",
    "no data scraped": "Scraper produced no data — check credentials, labels, and connectivity.",
    "empty response": "Scraper got empty responses — check credentials/labels/connectivity.",
    "validator rejected": "Data was rejected by a validator — review data quality/freshness.",
    "upload failed": "Data upload failed — check connectivity and storage credentials.",
    "s3 upload": "Review S3/storage upload configuration and credentials.",
    "storage upload": "Review storage upload configuration and credentials.",
    "timeout": "Transient timeouts; if frequent, check network/API health.",
}

# Patterns that influence the scoring heuristic, mapped to a context flag.
_CTX_FLAGS: dict[str, str] = {
    "rate limit": "rate_limited",
    "too many requests": "rate_limited",
    "no data scraped": "no_data_scraped",
    "empty response": "no_data_scraped",
    "no space left on device": "disk_full_logs",
    "out of disk": "disk_full_logs",
    "validator rejected": "validator_rejected",
}

MAX_EVIDENCE = 25


@dataclass
class _Match:
    file: str
    severity: str  # "critical" | "warning"
    pattern: str
    excerpt: str


class LogCheck(BaseCheck):
    category = CheckCategory.LOGS
    name = "logs"

    def run(self) -> list[CheckResult]:
        files = self._collect_files()
        if not files:
            return [
                self.result(
                    "logs",
                    "Logs",
                    CheckStatus.SKIPPED,
                    "No log files found at the configured log_paths.",
                    details={"searched": [str(p) for p in expand_paths(self.config.log_paths)]},
                    suggested_fixes=[
                        "Point log_paths at your PM2/miner logs (e.g. ~/.pm2/logs).",
                    ],
                )
            ]

        critical = self.config.data_universe.known_error_patterns.critical
        warning = self.config.data_universe.known_error_patterns.warning
        matches = self._scan(files, critical, warning)

        crit_matches = [m for m in matches if m.severity == "critical"]
        warn_matches = [m for m in matches if m.severity == "warning"]

        self._publish_findings(matches)

        results: list[CheckResult] = []
        results.append(self._build_result("critical", crit_matches, len(files)))
        results.append(self._build_result("warning", warn_matches, len(files)))
        # Drop the empty placeholder if there were no matches at that severity.
        return [r for r in results if r is not None]

    # ------------------------------------------------------------------ #
    def _collect_files(self) -> list[Path]:
        files: list[Path] = []
        for p in expand_paths(self.config.log_paths):
            try:
                if p.is_file():
                    files.append(p)
                elif p.is_dir():
                    files.extend(recent_log_files([p]))
            except Exception:  # noqa: BLE001
                continue
        # Deduplicate, keep order.
        seen: set[Path] = set()
        unique = []
        for f in files:
            if f not in seen:
                seen.add(f)
                unique.append(f)
        return unique[:25]

    def _scan(self, files: list[Path], critical: list[str], warning: list[str]) -> list[_Match]:
        # Severity is intrinsic to the pattern. A single line can match several
        # patterns (e.g. "rate limit ... retrying") — record each so context
        # flags and the patterns list are complete.
        all_patterns = [(p, p.lower(), "critical") for p in critical]
        all_patterns += [(p, p.lower(), "warning") for p in warning]
        matches: list[_Match] = []
        # Avoid flooding: at most a few excerpts per (file, pattern).
        seen_counts: dict[tuple[str, str], int] = {}

        for f in files:
            for line in read_last_lines(f, n=500):
                low = line.lower()
                excerpt = redact_secrets(line.strip())[:240]
                for pat, patl, severity in all_patterns:
                    if patl not in low:
                        continue
                    key = (str(f), pat)
                    seen_counts[key] = seen_counts.get(key, 0) + 1
                    if seen_counts[key] > 3:
                        continue
                    matches.append(
                        _Match(file=str(f), severity=severity, pattern=pat, excerpt=excerpt)
                    )
        return matches

    def _publish_findings(self, matches: list[_Match]) -> None:
        for m in matches:
            flag = _CTX_FLAGS.get(m.pattern)
            if flag:
                self.ctx.note(flag, True)

    def _build_result(
        self, severity: str, matches: list[_Match], file_count: int
    ) -> CheckResult | None:
        patterns = sorted({m.pattern for m in matches})
        if not matches:
            if severity == "critical":
                # Emit a single OK only for the critical sweep to avoid duplicate OKs.
                return self.result(
                    "logs_critical",
                    "Logs (critical patterns)",
                    CheckStatus.OK,
                    f"No critical error patterns in the last lines of {file_count} log file(s).",
                    details={"files_scanned": file_count},
                )
            return None

        evidence = [f"{Path(m.file).name}: {m.excerpt}" for m in matches][:MAX_EVIDENCE]
        fixes = []
        for pat in patterns:
            hint = _FIX_HINTS.get(pat)
            if hint and hint not in fixes:
                fixes.append(hint)

        if severity == "critical":
            return self.result(
                "logs_critical",
                "Logs (critical patterns)",
                CheckStatus.CRITICAL,
                f"Found {len(matches)} critical log line(s) matching: {', '.join(patterns)}.",
                details={
                    "patterns": patterns,
                    "match_count": len(matches),
                    "files_scanned": file_count,
                },
                evidence=evidence,
                suggested_fixes=fixes
                or ["Inspect the affected logs and address the errors above."],
            )
        return self.result(
            "logs_warning",
            "Logs (warning patterns)",
            CheckStatus.WARNING,
            f"Found {len(matches)} warning log line(s) matching: {', '.join(patterns)}.",
            details={
                "patterns": patterns,
                "match_count": len(matches),
                "files_scanned": file_count,
            },
            evidence=evidence,
            suggested_fixes=fixes or ["Review the warnings above; they may reduce miner value."],
        )
