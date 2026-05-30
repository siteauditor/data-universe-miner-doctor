"""Check registry + the runner that produces a :class:`DoctorReport`.

Checks run in a deliberate order so that information flows through the shared
``RunContext`` (e.g. the bittensor check publishes axon info before the network
check reads it; the log/config/data checks publish flags before the scoring
heuristic synthesises them).
"""

from __future__ import annotations

from typing import Optional

from du_doctor.checks.base import BaseCheck, RunContext
from du_doctor.checks.bittensor_check import BittensorCheck, resolve_hotkey_ss58
from du_doctor.checks.data_universe_config_check import DataUniverseConfigCheck
from du_doctor.checks.data_universe_data_check import DataUniverseDataCheck
from du_doctor.checks.data_universe_scoring_check import DataUniverseScoringCheck
from du_doctor.checks.log_check import LogCheck
from du_doctor.checks.network_check import NetworkCheck
from du_doctor.checks.process_check import ProcessCheck
from du_doctor.checks.repo_check import RepoCheck
from du_doctor.checks.system_check import SystemCheck
from du_doctor.models import (
    CheckResult,
    CheckStatus,
    DoctorConfig,
    DoctorReport,
    overall_status_for,
)
from du_doctor.storage.snapshots import build_snapshot, latest_snapshot, save_snapshot
from du_doctor.utils.redact import mask_hotkey

# Order matters — see module docstring.
CHECK_CLASSES: list[type[BaseCheck]] = [
    SystemCheck,
    BittensorCheck,
    RepoCheck,
    ProcessCheck,
    NetworkCheck,
    LogCheck,
    DataUniverseConfigCheck,
    DataUniverseDataCheck,
    DataUniverseScoringCheck,  # must run last: it reads everyone else's findings
]


def run_checks(
    config: DoctorConfig,
    save_snapshot_enabled: bool = True,
    show_full_hotkey: bool = False,
    profile=None,
) -> DoctorReport:
    """Run every check once and assemble the report.

    ``profile`` (a ``du_doctor.profiles.SubnetProfile``) selects which check
    classes and fix-order builder to use. ``None`` uses the built-in Data
    Universe set — identical to the original behavior.
    """
    check_classes = profile.check_classes if profile is not None else CHECK_CLASSES
    fix_builder = profile.fix_order_builder if profile is not None else build_suggested_fix_order

    hotkey, _ = resolve_hotkey_ss58(config)
    previous = latest_snapshot(hotkey=hotkey)

    ctx = RunContext(previous_snapshot=previous)

    results: list[CheckResult] = []
    for cls in check_classes:
        check = cls(config, ctx)
        results.extend(check.safe_run())

    overall = overall_status_for(results)
    resolved_hotkey = ctx.snapshot.get("hotkey") or hotkey
    report = DoctorReport(
        overall_status=overall,
        subnet_name=config.subnet_name,
        netuid=config.netuid,
        network=config.network,
        hotkey_masked=mask_hotkey(resolved_hotkey, show_full=show_full_hotkey),
        checks=results,
        suggested_fix_order=fix_builder(results, config, ctx),
    )

    if save_snapshot_enabled and (
        ctx.snapshot.get("hotkey") or ctx.snapshot.get("data_file_sizes")
    ):
        try:
            save_snapshot(build_snapshot(ctx.snapshot))
        except Exception:  # noqa: BLE001 - never let snapshot saving break a run
            pass

    return report


def build_suggested_fix_order(
    results: list[CheckResult],
    config: DoctorConfig,
    ctx: Optional[RunContext] = None,
) -> list[str]:
    """Produce the ordered, deduplicated list of headline fixes.

    Order follows the Data Universe fix-priority list (most impactful first).
    Only conditions that actually triggered are included.
    """
    by_id = {r.id: r for r in results}

    def is_status(check_id: str, status: CheckStatus) -> bool:
        r = by_id.get(check_id)
        return r is not None and r.status == status

    def any_cred_critical() -> bool:
        return any(
            r.id.startswith("du_cred_") and r.status == CheckStatus.CRITICAL for r in results
        )

    repo_path = config.subnet_repo_path or "<repo-path>"
    start_cmd = (
        "pm2 start python -- ./neurons/miner.py "
        "--wallet.name <wallet-name> --wallet.hotkey <hotkey-name>"
    )

    ordered: list[str] = []

    # 1. Hotkey not registered.
    if is_status("bt_metagraph", CheckStatus.CRITICAL):
        ordered.append(
            "Register your hotkey on subnet 13 — it is not registered (the miner earns nothing until then)."
        )
    # 2. Cannot connect to Subtensor.
    if is_status("bt_subtensor", CheckStatus.CRITICAL):
        ordered.append(
            f"Restore the subtensor connection to '{config.network}' so the miner can sync the chain."
        )
    # 3. Miner process not running.
    if is_status("pm2_process", CheckStatus.CRITICAL) or is_status(
        "process_search", CheckStatus.CRITICAL
    ):
        ordered.append(f"Start the miner process:\n   {start_cmd}")
    # 4. PM2 restart loop.
    if is_status("score_restart_loop", CheckStatus.CRITICAL) or is_status(
        "pm2_process", CheckStatus.WARNING
    ):
        ordered.append(
            "Stabilise the miner (frequent restarts) — inspect `pm2 logs` for the crash cause."
        )
    # 5. Missing scraping credentials.
    if any_cred_critical() or is_status("score_credentials", CheckStatus.CRITICAL):
        ordered.append(
            "Add the missing scraper credentials to your .env (e.g. APIFY_API_TOKEN / REDDIT_*)."
        )
    # 6. Invalid scraping_config.json.
    if is_status("du_config_json", CheckStatus.CRITICAL):
        ordered.append("Fix scraping_config.json — it is not valid JSON (python -m json.tool ...).")
    # 7. No local data / stale data.
    if (
        is_status("du_data_files", CheckStatus.WARNING)
        or is_status("du_data_freshness", CheckStatus.CRITICAL)
        or is_status("score_stale", CheckStatus.CRITICAL)
        or is_status("score_no_activity", CheckStatus.CRITICAL)
    ):
        ordered.append(
            "Investigate local data — ensure the scraper is producing fresh, growing data."
        )
    # 8. Repo very outdated.
    if is_status("repo_behind", CheckStatus.CRITICAL) or is_status(
        "repo_behind", CheckStatus.WARNING
    ):
        ordered.append(
            f"Update the Data Universe repo:\n   cd {repo_path} && git pull   (then restart the miner)"
        )
    # 9. Axon/port problem.
    if is_status("axon_port", CheckStatus.CRITICAL) or is_status(
        "axon_advertised", CheckStatus.WARNING
    ):
        ordered.append("Fix the axon/port so validators can reach your miner.")
    # 10. Rate limits / scraper errors.
    if is_status("logs_warning", CheckStatus.WARNING) or (
        ctx is not None and ctx.get("rate_limited")
    ):
        ordered.append("Address scraper warnings in the logs (rate limits, upload/storage errors).")
    # 11. Generic labels / low config quality.
    if is_status("du_config_labels", CheckStatus.WARNING) or is_status(
        "score_labels", CheckStatus.WARNING
    ):
        ordered.append(
            "Improve label/config quality — generic labels may be less competitive (check subnet docs)."
        )

    # Deduplicate while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for item in ordered:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


__all__ = [
    "CHECK_CLASSES",
    "run_checks",
    "build_suggested_fix_order",
    "RunContext",
    "BaseCheck",
]
