"""Presentation helpers shared by the terminal, JSON, and markdown reporters."""

from __future__ import annotations

from datetime import datetime, timezone

from du_doctor.models import CheckStatus

# Plain-text labels (used in markdown and the example terminal output).
STATUS_LABEL: dict[CheckStatus, str] = {
    CheckStatus.OK: "[OK]",
    CheckStatus.WARNING: "[WARNING]",
    CheckStatus.CRITICAL: "[CRITICAL]",
    CheckStatus.SKIPPED: "[SKIPPED]",
}

# Rich colour names for the terminal reporter.
STATUS_COLOR: dict[CheckStatus, str] = {
    CheckStatus.OK: "green",
    CheckStatus.WARNING: "yellow",
    CheckStatus.CRITICAL: "red",
    CheckStatus.SKIPPED: "dim",
}

# Small emoji/symbol used in section headers.
STATUS_SYMBOL: dict[CheckStatus, str] = {
    CheckStatus.OK: "✔",
    CheckStatus.WARNING: "▲",
    CheckStatus.CRITICAL: "✖",
    CheckStatus.SKIPPED: "•",
}


def human_bytes(num: float | int | None) -> str:
    """Format a byte count as a human-readable string (e.g. ``1.4 GB``)."""
    if num is None:
        return "unknown"
    value = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(value) < 1024.0:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
        value /= 1024.0
    return f"{value:.1f} EB"


def human_duration(seconds: float | None) -> str:
    """Format a duration in seconds as a compact human string."""
    if seconds is None:
        return "unknown"
    seconds = float(seconds)
    if seconds < 60:
        return f"{int(seconds)}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.0f}m"
    hours = minutes / 60
    if hours < 48:
        return f"{hours:.1f}h"
    days = hours / 24
    return f"{days:.1f}d"


def age_hours(ts: datetime) -> float:
    """Hours elapsed since a timestamp (timezone-aware or naive treated as UTC)."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - ts
    return delta.total_seconds() / 3600.0


def human_age_from_mtime(mtime: float) -> str:
    """Human-readable age given a POSIX mtime (seconds since epoch)."""
    age_seconds = datetime.now(timezone.utc).timestamp() - mtime
    return human_duration(max(age_seconds, 0.0)) + " ago"


def status_label(status: CheckStatus) -> str:
    return STATUS_LABEL.get(status, f"[{status.value}]")
