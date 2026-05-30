"""Heuristic "why might earnings be low?" checker.

IMPORTANT: these are *heuristics*, not the exact Data Universe scoring formula.
Wording is deliberately careful ("possible reason", "may reduce value",
"check subnet docs"). This check reads flags published into the run context by
the earlier checks (logs, data, config, process) and turns them into
actionable, clearly-hedged hypotheses.
"""

from __future__ import annotations

from du_doctor.checks.base import BaseCheck
from du_doctor.models import CheckCategory, CheckResult, CheckStatus


class DataUniverseScoringCheck(BaseCheck):
    category = CheckCategory.DATA_UNIVERSE_SCORING
    name = "data_universe_scoring"

    def run(self) -> list[CheckResult]:
        results: list[CheckResult] = []
        ctx = self.ctx

        # 6. PM2 restart loop (most severe → list first).
        restarts = ctx.get("pm2_restart_count")
        warn_count = self.config.thresholds.pm2_restart_warning_count
        if isinstance(restarts, int) and restarts >= warn_count:
            results.append(
                self.result(
                    "score_restart_loop",
                    "Uptime / stability",
                    CheckStatus.CRITICAL,
                    f"Miner has restarted {restarts} times — it may be unstable and losing uptime, "
                    "which reduces earnings.",
                    suggested_fixes=[
                        "Find the crash cause in the logs and stabilise before tuning data."
                    ],
                )
            )

        # 3. Credential failure.
        if ctx.get("credentials_missing"):
            results.append(
                self.result(
                    "score_credentials",
                    "Scraper credentials",
                    CheckStatus.CRITICAL,
                    "An enabled scraper cannot run without credentials, so it likely collects no "
                    "data — a direct, fixable cause of low value.",
                    suggested_fixes=[
                        "Add the missing scraper credentials (see config checks above)."
                    ],
                )
            )

        # 2. Low scrape activity (no new data and/or logs say nothing scraped).
        no_local_data = ctx.get("no_local_data")
        data_idle = ctx.get("data_idle")
        no_data_scraped = ctx.get("no_data_scraped")
        if no_data_scraped:
            # Logs explicitly report nothing scraped — a strong, direct signal.
            results.append(
                self.result(
                    "score_no_activity",
                    "Scrape activity",
                    CheckStatus.CRITICAL,
                    "Logs indicate little or no data is being scraped. A miner that stores no fresh "
                    "data has little to be rewarded for.",
                    suggested_fixes=[
                        "Verify the scraper runs, has credentials, and is not rate-limited.",
                        "Confirm the local DB is actually growing.",
                    ],
                )
            )
        elif no_local_data:
            # We couldn't find any local DB — could be no scraping OR a path
            # misconfiguration, so this stays a hedged WARNING rather than CRITICAL.
            results.append(
                self.result(
                    "score_no_activity",
                    "Scrape activity",
                    CheckStatus.WARNING,
                    "No local data was found. Either the scraper isn't producing data, or data_paths "
                    "doesn't point at the miner's database — confirm which before drawing conclusions.",
                    suggested_fixes=[
                        "Check that data_paths point at where the miner writes its DB.",
                        "Then verify the scraper is actually collecting and storing data.",
                    ],
                )
            )
        elif data_idle:
            results.append(
                self.result(
                    "score_idle",
                    "Scrape activity",
                    CheckStatus.WARNING,
                    "Heuristic warning: local data did not grow since last check. The scraper may be "
                    "idle or blocked, which may reduce value.",
                    suggested_fixes=["Check scraper logs for stalls, auth errors, or rate limits."],
                )
            )

        # 1. Stale data.
        stale = ctx.get("stale_data")
        if stale == "critical":
            results.append(
                self.result(
                    "score_stale",
                    "Data freshness",
                    CheckStatus.CRITICAL,
                    "Data appears very stale. Freshness may strongly affect miner value — "
                    "check subnet docs for how recency is rewarded.",
                    suggested_fixes=[
                        "Get the scraper producing fresh data again (see data checks)."
                    ],
                )
            )
        elif stale == "warning":
            results.append(
                self.result(
                    "score_stale",
                    "Data freshness",
                    CheckStatus.WARNING,
                    "Data appears stale. Freshness may affect miner value — check subnet docs.",
                    suggested_fixes=["Confirm the scraper is writing new data frequently."],
                )
            )

        # 4. Rate limit.
        if ctx.get("rate_limited"):
            results.append(
                self.result(
                    "score_rate_limit",
                    "Rate limiting",
                    CheckStatus.WARNING,
                    "Scraper may be throttled (rate-limit messages in logs). Throttling can reduce "
                    "how much data you collect.",
                    suggested_fixes=[
                        "Slow the cadence, rotate/upgrade API credentials, or reduce concurrency.",
                    ],
                )
            )

        # 5. Generic labels.
        if ctx.get("generic_labels"):
            results.append(
                self.result(
                    "score_labels",
                    "Label strategy",
                    CheckStatus.WARNING,
                    "Generic labels may be less competitive. Review your label strategy — "
                    "this may reduce relative value. Check subnet docs.",
                    suggested_fixes=[
                        "Target less-saturated, higher-value labels where appropriate."
                    ],
                )
            )

        # validator rejection signal.
        if ctx.get("validator_rejected"):
            results.append(
                self.result(
                    "score_validator_reject",
                    "Validator acceptance",
                    CheckStatus.WARNING,
                    "Logs mention data being rejected by a validator. This may reduce rewarded data — "
                    "check data quality/freshness against subnet docs.",
                    suggested_fixes=["Investigate which data is rejected and why."],
                )
            )

        if not results:
            return [
                self.result(
                    "score_summary",
                    "Earning heuristics",
                    CheckStatus.OK,
                    "No obvious heuristic reasons for low earnings detected. "
                    "(Scoring also depends on chain-side factors not measurable locally.)",
                )
            ]
        return results
