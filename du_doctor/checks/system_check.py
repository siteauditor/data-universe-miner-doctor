"""System / environment checks: OS, Python, disk, RAM, CPU, internet, GPU."""

from __future__ import annotations

import os
import platform
import socket
import sys
from pathlib import Path

import psutil

from du_doctor.checks.base import BaseCheck
from du_doctor.models import CheckCategory, CheckResult, CheckStatus
from du_doctor.utils.formatting import human_bytes
from du_doctor.utils.shell import command_exists, run_command
from du_doctor.utils.versioning import satisfies_min

# A few independent, well-known TCP endpoints so connectivity isn't judged by
# one fragile host. We only open a socket — no payload, no HTTP, no DNS-only.
_CONNECTIVITY_TARGETS = [
    ("1.1.1.1", 443),
    ("8.8.8.8", 443),
    ("9.9.9.9", 443),
]


class SystemCheck(BaseCheck):
    category = CheckCategory.SYSTEM
    name = "system"

    def run(self) -> list[CheckResult]:
        return [
            self._check_os(),
            self._check_python(),
            self._check_disk(),
            self._check_ram(),
            self._check_cpu(),
            self._check_internet(),
            self._check_gpu(),
        ]

    # ------------------------------------------------------------------ #
    def _check_os(self) -> CheckResult:
        system = platform.system()
        distro = _linux_distro() if system == "Linux" else ""
        details = {"system": system, "release": platform.release(), "distro": distro}

        if system == "Linux":
            label = distro or "Linux"
            return self.result(
                "os",
                "Operating system",
                CheckStatus.OK,
                f"{label} detected",
                details=details,
            )
        if system == "Darwin":
            return self.result(
                "os",
                "Operating system",
                CheckStatus.WARNING,
                "macOS detected — fine for testing, but Data Universe miners are "
                "expected to run on Ubuntu/Linux servers.",
                details=details,
                suggested_fixes=["Run the miner on an Ubuntu/Linux server for production."],
            )
        # Windows or unknown.
        return self.result(
            "os",
            "Operating system",
            CheckStatus.CRITICAL,
            f"{system or 'Unknown OS'} detected — Data Universe miners run on Ubuntu/Linux. "
            "PM2/process/log checks will be unreliable here.",
            details=details,
            suggested_fixes=["Run du-doctor on the same Ubuntu/Linux server as your miner."],
        )

    def _check_python(self) -> CheckResult:
        version = platform.python_version()
        required = self.config.data_universe.required_python_version
        details = {"python_version": version, "required": required, "executable": sys.executable}
        if satisfies_min(version, required):
            return self.result(
                "python_version",
                "Python version",
                CheckStatus.OK,
                f"Python {version} (requires {required})",
                details=details,
            )
        return self.result(
            "python_version",
            "Python version",
            CheckStatus.WARNING,
            f"Python {version} is below the recommended {required}.",
            details=details,
            suggested_fixes=["Use Python 3.10+ for the miner virtual environment."],
        )

    def _check_disk(self) -> CheckResult:
        target = _disk_target(self.config.subnet_repo_path)
        try:
            usage = psutil.disk_usage(str(target))
        except Exception as exc:  # noqa: BLE001
            return self.result(
                "disk",
                "Disk usage",
                CheckStatus.SKIPPED,
                f"Could not read disk usage for {target}: {exc}",
            )
        pct = usage.percent
        details = {
            "path": str(target),
            "percent_used": pct,
            "total": human_bytes(usage.total),
            "used": human_bytes(usage.used),
            "free": human_bytes(usage.free),
        }
        warn = self.config.thresholds.disk_usage_warning_percent
        summary = f"{pct:.0f}% used on {target} ({human_bytes(usage.free)} free)"
        if pct >= 95:
            return self.result(
                "disk",
                "Disk usage",
                CheckStatus.CRITICAL,
                f"Disk almost full: {summary}. Scrapers and the DB can fail to write.",
                details=details,
                suggested_fixes=[
                    "Free disk space immediately (old logs, caches, unused docker images).",
                    "A full disk causes 'no space left on device' and stops data writes.",
                ],
            )
        if pct >= warn:
            return self.result(
                "disk",
                "Disk usage",
                CheckStatus.WARNING,
                f"Disk high: {summary}.",
                details=details,
                suggested_fixes=["Plan to free disk space before it fills up."],
            )
        return self.result("disk", "Disk usage", CheckStatus.OK, summary, details=details)

    def _check_ram(self) -> CheckResult:
        vm = psutil.virtual_memory()
        pct = vm.percent
        details = {
            "percent_used": pct,
            "total": human_bytes(vm.total),
            "available": human_bytes(vm.available),
        }
        warn = self.config.thresholds.ram_usage_warning_percent
        summary = f"{pct:.0f}% RAM used ({human_bytes(vm.available)} available)"
        if pct >= 95:
            return self.result(
                "ram",
                "RAM usage",
                CheckStatus.CRITICAL,
                f"Memory critically high: {summary}. The miner may be OOM-killed.",
                details=details,
                suggested_fixes=["Reduce scraper concurrency or add RAM/swap."],
            )
        if pct >= warn:
            return self.result(
                "ram",
                "RAM usage",
                CheckStatus.WARNING,
                f"Memory high: {summary}.",
                details=details,
            )
        return self.result("ram", "RAM usage", CheckStatus.OK, summary, details=details)

    def _check_cpu(self) -> CheckResult:
        cpu_count = psutil.cpu_count(logical=True) or 1
        # Short sampling window so we don't stall the run.
        cpu_pct = psutil.cpu_percent(interval=0.4)
        loadavg = _loadavg()
        details = {"cpu_percent": cpu_pct, "cpu_count": cpu_count, "loadavg": loadavg}
        warn = self.config.thresholds.cpu_usage_warning_percent

        load_per_core = (loadavg[0] / cpu_count) if loadavg else None
        summary = f"{cpu_pct:.0f}% CPU"
        if loadavg:
            summary += f", load {loadavg[0]:.2f} over {cpu_count} cores"

        sustained_high = load_per_core is not None and load_per_core > 1.5
        if cpu_pct >= warn or sustained_high:
            return self.result(
                "cpu",
                "CPU load",
                CheckStatus.WARNING,
                f"High CPU load: {summary}.",
                details=details,
                suggested_fixes=[
                    "Sustained high load can throttle scraping and miner responsiveness.",
                    "Check `top`/`htop` and reduce scraper parallelism if needed.",
                ],
            )
        return self.result("cpu", "CPU load", CheckStatus.OK, summary, details=details)

    def _check_internet(self) -> CheckResult:
        reachable = []
        for host, port in _CONNECTIVITY_TARGETS:
            if _can_connect(host, port):
                reachable.append(f"{host}:{port}")
        details = {"reachable": reachable, "tested": [f"{h}:{p}" for h, p in _CONNECTIVITY_TARGETS]}
        if reachable:
            return self.result(
                "internet",
                "Internet connectivity",
                CheckStatus.OK,
                f"Outbound connectivity OK ({len(reachable)}/{len(_CONNECTIVITY_TARGETS)} reachable)",
                details=details,
            )
        return self.result(
            "internet",
            "Internet connectivity",
            CheckStatus.CRITICAL,
            "No outbound connectivity to any test endpoint. The miner cannot reach "
            "the chain or scraper APIs.",
            details=details,
            suggested_fixes=[
                "Check network/firewall/egress rules on this server.",
                "Without internet the miner cannot sync the chain or scrape data.",
            ],
        )

    def _check_gpu(self) -> CheckResult:
        requires_gpu = self.config.data_universe.requires_gpu
        if not command_exists("nvidia-smi"):
            msg = "No GPU detected. Data Universe does not require GPU by default."
            status = CheckStatus.CRITICAL if requires_gpu else CheckStatus.OK
            return self.result(
                "gpu",
                "GPU",
                status,
                msg,
                details={"nvidia_smi": False, "requires_gpu": requires_gpu},
            )
        res = run_command(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,utilization.gpu",
                "--format=csv,noheader",
            ],
            timeout=10,
        )
        if not res.ok or not res.stdout.strip():
            return self.result(
                "gpu",
                "GPU",
                CheckStatus.OK,
                "nvidia-smi present but returned no GPU info (not required for SN13).",
                details={"nvidia_smi": True, "error": res.stderr.strip()[:200]},
            )
        gpus = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        return self.result(
            "gpu",
            "GPU",
            CheckStatus.OK,
            f"{len(gpus)} GPU(s) detected (not required for SN13).",
            details={"nvidia_smi": True, "gpus": gpus},
            evidence=gpus,
        )


# --------------------------------------------------------------------------- #
# Module-level helpers
# --------------------------------------------------------------------------- #
def _linux_distro() -> str:
    """Best-effort pretty distro name from /etc/os-release."""
    try:
        with open("/etc/os-release", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except Exception:  # noqa: BLE001
        pass
    return ""


def _disk_target(repo_path: str) -> Path:
    """Pick a meaningful filesystem to measure (repo dir, else home, else root)."""
    if repo_path:
        p = Path(os.path.expanduser(repo_path))
        if p.exists():
            return p
    home = Path.home()
    if home.exists():
        return home
    return Path(os.path.abspath(os.sep))


def _loadavg() -> tuple[float, float, float] | None:
    try:
        return os.getloadavg()  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        try:
            return psutil.getloadavg()  # available on some platforms
        except Exception:  # noqa: BLE001
            return None


def _can_connect(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:  # noqa: BLE001
        return False
