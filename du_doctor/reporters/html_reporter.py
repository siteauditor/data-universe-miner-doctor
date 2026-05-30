"""Self-contained HTML "Miner Health Report" (no JS, no external assets).

Mirrors the markdown reporter's sections but emits a styled, printable HTML
document (users can print-to-PDF in the browser). Every dynamic value is
redacted (``redact_secrets``) and HTML-escaped, so the output is safe to share.
"""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

from du_doctor.models import CheckCategory, CheckResult, CheckStatus, DoctorReport
from du_doctor.utils.redact import redact_secrets

DEFAULT_HTML_PATH = "du-doctor-report.html"

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

_STATUS_CLASS = {
    CheckStatus.OK: "ok",
    CheckStatus.WARNING: "warn",
    CheckStatus.CRITICAL: "crit",
    CheckStatus.SKIPPED: "skip",
}

_CSS = """
:root { color-scheme: light dark; }
body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
       margin: 0; padding: 0 0 48px; color: #1b1f24; background: #f6f8fa; }
header { background: #0d1117; color: #e6edf3; padding: 20px 28px; }
header h1 { margin: 0 0 6px; font-size: 20px; }
header .meta { font-size: 13px; color: #9aa6b2; line-height: 1.6; }
main { max-width: 980px; margin: 0 auto; padding: 24px 28px; }
.overall { font-size: 15px; font-weight: 700; padding: 10px 14px; border-radius: 8px; display: inline-block; }
h2 { font-size: 16px; margin: 28px 0 10px; border-bottom: 1px solid #d0d7de; padding-bottom: 6px; }
table { width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #d0d7de; border-radius: 8px; overflow: hidden; }
th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid #eaeef2; font-size: 14px; vertical-align: top; }
th { background: #f0f3f6; }
.pill { padding: 2px 9px; border-radius: 999px; font-size: 12px; font-weight: 700; white-space: nowrap; }
.ok { background: #e6f4ea; color: #1a7f37; } .warn { background: #fff4e5; color: #9a6700; }
.crit { background: #ffebe9; color: #cf222e; } .skip { background: #eaeef2; color: #57606a; }
.check { background: #fff; border: 1px solid #d0d7de; border-radius: 8px; padding: 12px 14px; margin: 10px 0; }
.check .title { font-weight: 600; }
.evidence { background: #0d1117; color: #c9d1d9; font-family: ui-monospace, monospace; font-size: 12px;
            padding: 8px 10px; border-radius: 6px; margin-top: 8px; white-space: pre-wrap; }
.fixes { margin: 8px 0 0; padding-left: 20px; }
ol.fixorder li { margin: 6px 0; }
.footer { color: #57606a; font-size: 12px; margin-top: 28px; }
code { background: #eaeef2; padding: 1px 5px; border-radius: 4px; }
""".strip()


def _esc(text: str) -> str:
    """Redact then HTML-escape — the single safe path for dynamic strings."""
    return html.escape(redact_secrets(text or ""), quote=False)


def _fmt_time(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC") if hasattr(dt, "strftime") else str(dt)


def _pill(status: CheckStatus) -> str:
    cls = _STATUS_CLASS.get(status, "skip")
    return f'<span class="pill {cls}">{status.value}</span>'


def render_html(report: DoctorReport) -> str:
    overall_cls = _STATUS_CLASS.get(report.overall_status, "skip")
    parts: list[str] = []
    parts.append("<!doctype html><html lang='en'><head><meta charset='utf-8'>")
    parts.append("<meta name='viewport' content='width=device-width, initial-scale=1'>")
    parts.append("<title>Data Universe Miner Doctor Report</title>")
    parts.append(f"<style>{_CSS}</style></head><body>")

    # Header
    parts.append("<header>")
    parts.append("<h1>Data Universe Miner Doctor Report</h1>")
    parts.append("<div class='meta'>")
    parts.append(f"Subnet: {_esc(report.subnet_name)} (NETUID {report.netuid})<br>")
    parts.append(f"Network: {_esc(report.network)}<br>")
    parts.append(f"Hotkey: {_esc(report.hotkey_masked or 'not resolved')}<br>")
    parts.append(f"Created: {_esc(_fmt_time(report.created_at))}")
    parts.append("</div></header>")

    parts.append("<main>")
    parts.append(
        f"<p><span class='overall {overall_cls}'>Overall status: "
        f"{report.overall_status.value}</span></p>"
    )

    # Summary table
    parts.append(
        "<h2>Summary</h2><table><thead><tr>"
        "<th>Status</th><th>Category</th><th>Check</th><th>Summary</th>"
        "</tr></thead><tbody>"
    )
    for c in report.checks:
        parts.append(
            f"<tr><td>{_pill(c.status)}</td><td>{_esc(c.category.value)}</td>"
            f"<td>{_esc(c.title)}</td><td>{_esc(c.summary)}</td></tr>"
        )
    parts.append("</tbody></table>")

    # Detailed sections
    parts.append("<h2>Detailed checks</h2>")
    by_cat: dict[CheckCategory, list[CheckResult]] = {}
    for c in report.checks:
        by_cat.setdefault(c.category, []).append(c)
    for category, title in _SECTION_ORDER:
        checks = by_cat.get(category)
        if not checks:
            continue
        parts.append(f"<h3>{_esc(title)}</h3>")
        for c in checks:
            parts.append("<div class='check'>")
            parts.append(f"<div class='title'>{_pill(c.status)} {_esc(c.title)}</div>")
            parts.append(f"<div>{_esc(c.summary)}</div>")
            if c.evidence:
                ev = "\n".join(_esc(line) for line in c.evidence)
                parts.append(f"<div class='evidence'>{ev}</div>")
            if c.suggested_fixes:
                parts.append("<ul class='fixes'>")
                parts.extend(f"<li>{_esc(fix)}</li>" for fix in c.suggested_fixes)
                parts.append("</ul>")
            parts.append("</div>")

    # Suggested fix order
    parts.append("<h2>Suggested fixes (priority order)</h2>")
    if report.suggested_fix_order:
        parts.append("<ol class='fixorder'>")
        parts.extend(f"<li>{_esc(fix)}</li>" for fix in report.suggested_fix_order)
        parts.append("</ol>")
    else:
        parts.append("<p><em>No prioritized fixes — nothing critical detected.</em></p>")

    parts.append(
        "<p class='footer'>Generated by Data Universe Miner Doctor (read-only). "
        "Secrets redacted; hotkey masked.</p>"
    )
    parts.append("</main></body></html>")
    return "".join(parts)


def write_html(report: DoctorReport, path: str | Path = DEFAULT_HTML_PATH) -> Path:
    out = Path(path)
    out.write_text(render_html(report), encoding="utf-8")
    return out
