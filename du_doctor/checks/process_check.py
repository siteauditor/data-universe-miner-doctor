"""Process checks: PM2 status + a generic psutil fallback search.

The canonical Data Universe miner command is:

    pm2 start python -- ./neurons/miner.py --wallet.name <name> --wallet.hotkey <hk>

so PM2 is the primary target, with a psutil scan as a backstop for non-PM2
setups (systemd, tmux, nohup, ...).
"""

from __future__ import annotations

import json
from typing import Any, Optional

import psutil

from du_doctor.checks.base import BaseCheck
from du_doctor.models import CheckCategory, CheckResult, CheckStatus
from du_doctor.utils.shell import command_exists, run_command

_START_HINT = (
    "pm2 start python -- ./neurons/miner.py "
    "--wallet.name <wallet-name> --wallet.hotkey <hotkey-name>"
)


class ProcessCheck(BaseCheck):
    category = CheckCategory.PROCESS
    name = "process"

    def run(self) -> list[CheckResult]:
        results: list[CheckResult] = []
        pm2_installed = command_exists("pm2")

        # 1. PM2 installed?
        if pm2_installed:
            ver = run_command(["pm2", "--version"], timeout=10)
            results.append(
                self.result(
                    "pm2_installed",
                    "PM2 installed",
                    CheckStatus.OK,
                    f"PM2 {ver.stdout.strip() or 'present'}.",
                    details={"version": ver.stdout.strip()},
                )
            )
        else:
            results.append(
                self.result(
                    "pm2_installed",
                    "PM2 installed",
                    CheckStatus.WARNING,
                    "PM2 not found. The common Data Universe setup runs the miner under PM2.",
                    suggested_fixes=[
                        "Install PM2: `npm install -g pm2` (or run under another process manager).",
                    ],
                )
            )

        # Always do a generic process scan; it's useful in every path.
        psutil_matches = self._psutil_search()

        if pm2_installed:
            results.append(self._check_pm2_process(psutil_matches))
        else:
            results.append(self._check_without_pm2(psutil_matches))

        return results

    # ------------------------------------------------------------------ #
    def _psutil_search(self) -> list[dict[str, Any]]:
        """Return matching processes by scanning command lines."""
        needles = {self.config.miner_process_name.lower(), "neurons/miner.py", "miner.py"}
        needles = {n for n in needles if n}
        matches: list[dict[str, Any]] = []
        for proc in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
            try:
                cmdline = proc.info.get("cmdline") or []
                joined = " ".join(cmdline).lower()
                if any(n in joined for n in needles):
                    matches.append(
                        {
                            "pid": proc.info.get("pid"),
                            "name": proc.info.get("name"),
                            "cmdline": " ".join(cmdline)[:300],
                        }
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            except Exception:  # noqa: BLE001
                continue
        return matches

    def _pm2_jlist(self) -> Optional[list[dict[str, Any]]]:
        res = run_command(["pm2", "jlist"], timeout=15)
        if not res.ok:
            return None
        # pm2 sometimes prints a banner before the JSON; grab from first '['.
        text = res.stdout
        start = text.find("[")
        if start == -1:
            return None
        try:
            data = json.loads(text[start:])
        except Exception:  # noqa: BLE001
            return None
        return data if isinstance(data, list) else None

    def _match_pm2_proc(self, jlist: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
        configured = (self.config.pm2_process_name or "").strip().lower()
        for proc in jlist:
            name = str(proc.get("name", "")).lower()
            env = proc.get("pm2_env", {}) or {}
            exec_path = str(env.get("pm_exec_path", "")).lower()
            args = env.get("args", [])
            if isinstance(args, list):
                args_str = " ".join(str(a) for a in args).lower()
            else:
                args_str = str(args).lower()
            haystack = f"{name} {exec_path} {args_str}"

            if configured and name == configured:
                return proc
            if "neurons/miner.py" in haystack or "miner.py" in haystack:
                return proc
        return None

    def _check_pm2_process(self, psutil_matches: list[dict[str, Any]]) -> CheckResult:
        jlist = self._pm2_jlist()
        if jlist is None:
            # PM2 is installed but jlist failed; fall back to psutil verdict.
            if psutil_matches:
                self.ctx.note("miner_running", True)
                return self.result(
                    "pm2_process",
                    "PM2 miner process",
                    CheckStatus.WARNING,
                    "Could not read `pm2 jlist`, but a miner process is running (via psutil).",
                    details={"psutil_matches": psutil_matches},
                )
            self.ctx.note("miner_running", False)
            return self.result(
                "pm2_process",
                "PM2 miner process",
                CheckStatus.CRITICAL,
                "Could not read `pm2 jlist` and no miner process found.",
                suggested_fixes=["Check PM2: `pm2 list`", f"Start the miner: {_START_HINT}"],
            )

        proc = self._match_pm2_proc(jlist)
        if proc is None:
            self.ctx.note("miner_running", bool(psutil_matches))
            extra = ""
            if psutil_matches:
                extra = " A matching process IS running but is not managed by PM2."
            return self.result(
                "pm2_process",
                "PM2 miner process",
                CheckStatus.CRITICAL,
                "No Data Universe miner process found in PM2." + extra,
                details={"pm2_process_count": len(jlist), "psutil_matches": psutil_matches},
                evidence=[str(p.get("name")) for p in jlist][:15],
                suggested_fixes=[
                    "List PM2 processes: pm2 list",
                    f"Start the miner: {_START_HINT}",
                ],
            )

        env = proc.get("pm2_env", {}) or {}
        status = str(env.get("status", "unknown"))
        restarts = _int_or_zero(env.get("restart_time", proc.get("restart", 0)))
        name = proc.get("name", "?")
        details = {
            "name": name,
            "status": status,
            "restart_time": restarts,
            "pm_id": proc.get("pm_id"),
            "pid": proc.get("pid"),
        }
        # Publish for the snapshot + scoring heuristic.
        self.ctx.snapshot["pm2_restart_count"] = restarts
        self.ctx.note("pm2_restart_count", restarts)
        self.ctx.note("miner_running", status == "online")

        warn_count = self.config.thresholds.pm2_restart_warning_count

        if status != "online":
            return self.result(
                "pm2_process",
                "PM2 miner process",
                CheckStatus.CRITICAL if status in {"errored", "stopped"} else CheckStatus.WARNING,
                f"PM2 process '{name}' is '{status}' (not online).",
                details=details,
                suggested_fixes=[
                    f"pm2 logs {name}",
                    f"pm2 restart {name}",
                    f"Or (re)start fresh: {_START_HINT}",
                ],
            )

        if restarts >= warn_count:
            return self.result(
                "pm2_process",
                "PM2 miner process",
                CheckStatus.WARNING,
                f"PM2 process '{name}' is online but has restarted {restarts} times "
                f"(>= {warn_count}). It may be unstable.",
                details=details,
                suggested_fixes=[
                    f"Inspect why it restarts: pm2 logs {name}",
                    "Frequent restarts cost uptime and can hurt miner value.",
                ],
            )

        return self.result(
            "pm2_process",
            "PM2 miner process",
            CheckStatus.OK,
            f"PM2 process '{name}' is online ({restarts} restarts).",
            details=details,
        )

    def _check_without_pm2(self, psutil_matches: list[dict[str, Any]]) -> CheckResult:
        if psutil_matches:
            self.ctx.note("miner_running", True)
            return self.result(
                "process_search",
                "Miner process",
                CheckStatus.WARNING,
                "Miner process found, but PM2 not detected.",
                details={"matches": psutil_matches},
                evidence=[m["cmdline"] for m in psutil_matches][:5],
                suggested_fixes=[
                    "Running without PM2 is fine, but PM2 makes restarts/logs easier.",
                ],
            )
        self.ctx.note("miner_running", False)
        return self.result(
            "process_search",
            "Miner process",
            CheckStatus.CRITICAL,
            "No Data Universe miner process is running.",
            suggested_fixes=[f"Start the miner: {_START_HINT}"],
        )


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
