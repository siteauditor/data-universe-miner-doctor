"""Rich terminal report — the default human-facing output of ``du-doctor``."""

from __future__ import annotations

from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from du_doctor.models import CheckCategory, CheckResult, CheckStatus, DoctorReport
from du_doctor.utils.formatting import STATUS_COLOR, status_label
from du_doctor.utils.redact import redact_secrets

_SECTION_ORDER: list[tuple[CheckCategory, str]] = [
    (CheckCategory.SYSTEM, "System"),
    (CheckCategory.BITTENSOR, "Bittensor registration & miner metrics"),
    (CheckCategory.REPO, "Repo / code status"),
    (CheckCategory.PROCESS, "PM2 / process status"),
    (CheckCategory.NETWORK, "Network / axon"),
    (CheckCategory.DATA_UNIVERSE_CONFIG, "Data Universe scraping config"),
    (CheckCategory.DATA_UNIVERSE_DATA, "Data freshness / local DB"),
    (CheckCategory.LOGS, "Logs"),
    (CheckCategory.DATA_UNIVERSE_SCORING, "Earning heuristics (possible reasons)"),
]


def _status_text(status: CheckStatus) -> Text:
    return Text(status_label(status), style=STATUS_COLOR.get(status, "white"))


def render_terminal(
    report: DoctorReport,
    console: Optional[Console] = None,
    verbose: bool = False,
) -> None:
    """Print the full report to the terminal. Never raises."""
    console = console or Console()

    # --- Header ---
    header = Text()
    header.append("Data Universe Miner Doctor\n", style="bold cyan")
    header.append(f"Subnet: {report.subnet_name} / NETUID {report.netuid}\n")
    header.append(f"Network: {report.network}\n")
    header.append(f"Hotkey: {report.hotkey_masked or 'not resolved'}\n")
    header.append(f"Created: {report.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    console.print(Panel(header, border_style="cyan"))

    # --- Overall status ---
    overall_color = STATUS_COLOR.get(report.overall_status, "white")
    console.print(
        Text("Overall status: ", style="bold")
        + Text(report.overall_status.value, style=f"bold {overall_color}")
    )
    console.print()

    # --- Quick scan list (matches the spec's example output) ---
    for c in report.checks:
        if not verbose and c.status == CheckStatus.SKIPPED:
            continue
        line = _status_text(c.status)
        line.append(f" {_friendly_category(c.category)}: ", style="bold")
        line.append(redact_secrets(c.summary))
        console.print(line)
    console.print()

    # --- Summary table ---
    table = Table(title="Summary", show_lines=False, expand=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Category", no_wrap=True)
    table.add_column("Check", no_wrap=True)
    table.add_column("Summary", overflow="fold")
    for c in report.checks:
        table.add_row(
            _status_text(c.status),
            c.category.value,
            c.title,
            redact_secrets(c.summary),
        )
    console.print(table)
    console.print()

    # --- Detailed sections (non-OK by default; everything in verbose) ---
    _render_details(console, report, verbose)

    # --- Suggested fixes ---
    if report.suggested_fix_order:
        fix_text = Text()
        for i, fix in enumerate(report.suggested_fix_order, start=1):
            fix_text.append(f"{i}. ", style="bold")
            fix_text.append(redact_secrets(fix) + "\n")
        console.print(
            Panel(fix_text, title="Suggested fixes (priority order)", border_style="magenta")
        )
    else:
        console.print(
            Panel(
                "No prioritized fixes — nothing critical detected.",
                title="Suggested fixes",
                border_style="green",
            )
        )


def _render_details(console: Console, report: DoctorReport, verbose: bool) -> None:
    by_cat: dict[CheckCategory, list[CheckResult]] = {}
    for c in report.checks:
        by_cat.setdefault(c.category, []).append(c)

    for category, title in _SECTION_ORDER:
        checks = by_cat.get(category)
        if not checks:
            continue
        shown = [
            c for c in checks if verbose or c.status in (CheckStatus.WARNING, CheckStatus.CRITICAL)
        ]
        if not shown:
            continue
        console.rule(f"[bold]{title}")
        for c in shown:
            line = _status_text(c.status)
            line.append(f" {c.title}: ", style="bold")
            line.append(redact_secrets(c.summary))
            console.print(line)
            for ev in c.evidence[:10]:
                console.print(Text("    " + redact_secrets(ev), style="dim"))
            for fix in c.suggested_fixes:
                console.print(Text("    -> " + redact_secrets(fix), style="cyan"))
        console.print()


def _friendly_category(category: CheckCategory) -> str:
    return {
        CheckCategory.SYSTEM: "System",
        CheckCategory.BITTENSOR: "Bittensor",
        CheckCategory.REPO: "Repo",
        CheckCategory.PROCESS: "Process",
        CheckCategory.NETWORK: "Network",
        CheckCategory.LOGS: "Logs",
        CheckCategory.DATA_UNIVERSE_CONFIG: "Config",
        CheckCategory.DATA_UNIVERSE_DATA: "Data",
        CheckCategory.DATA_UNIVERSE_SCORING: "Earnings",
    }.get(category, category.value)
