"""Snapshot persistence used to detect drops over time.

Snapshots are stored locally in ``~/.du-doctor/snapshots.json`` as a small
rolling history. Nothing is ever uploaded. A snapshot captures the metrics and
local-data fingerprints needed to answer "did anything get worse since last
time?".
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from du_doctor.config import get_snapshots_path

# Keep history bounded so the file never grows without limit.
MAX_HISTORY = 50


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_history(path: Optional[Path] = None) -> list[dict[str, Any]]:
    """Load all stored snapshots (oldest first). Returns ``[]`` on any error."""
    path = path or get_snapshots_path()
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:  # noqa: BLE001 - corrupt file -> behave as if empty
        return []
    if isinstance(data, dict) and "snapshots" in data:
        data = data["snapshots"]
    if not isinstance(data, list):
        return []
    return [s for s in data if isinstance(s, dict)]


def latest_snapshot(
    hotkey: Optional[str] = None,
    path: Optional[Path] = None,
) -> Optional[dict[str, Any]]:
    """Return the most recent snapshot, optionally filtered by hotkey.

    When a ``hotkey`` is given we prefer the most recent snapshot for THAT
    hotkey so a config change doesn't produce misleading drop comparisons.
    """
    history = load_history(path)
    if not history:
        return None
    if hotkey:
        for snap in reversed(history):
            if snap.get("hotkey") == hotkey:
                return snap
    return history[-1]


def save_snapshot(snapshot: dict[str, Any], path: Optional[Path] = None) -> Path:
    """Append a snapshot to the rolling history and write it atomically."""
    path = path or get_snapshots_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    snapshot = dict(snapshot)
    snapshot.setdefault("timestamp", _now_iso())

    history = load_history(path)
    history.append(snapshot)
    history = history[-MAX_HISTORY:]

    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(history, fh, indent=2, default=str)
    tmp.replace(path)
    return path


def build_snapshot(ctx_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Normalise the accumulated context snapshot into the stored shape.

    All fields are optional; whatever checks managed to populate is persisted.
    """
    snap: dict[str, Any] = {
        "timestamp": _now_iso(),
        "netuid": ctx_snapshot.get("netuid"),
        "hotkey": ctx_snapshot.get("hotkey"),
        "uid": ctx_snapshot.get("uid"),
        "rank": ctx_snapshot.get("rank"),
        "trust": ctx_snapshot.get("trust"),
        "consensus": ctx_snapshot.get("consensus"),
        "incentive": ctx_snapshot.get("incentive"),
        "emission": ctx_snapshot.get("emission"),
        "active": ctx_snapshot.get("active"),
        "stake": ctx_snapshot.get("stake"),
        "dividends": ctx_snapshot.get("dividends"),
        "validator_trust": ctx_snapshot.get("validator_trust"),
        "registered": ctx_snapshot.get("registered"),
        "data_file_sizes": ctx_snapshot.get("data_file_sizes", {}),
        "data_file_mtimes": ctx_snapshot.get("data_file_mtimes", {}),
        "pm2_restart_count": ctx_snapshot.get("pm2_restart_count"),
    }
    return snap


def percent_drop(previous: Optional[float], current: Optional[float]) -> Optional[float]:
    """Return the percentage drop from ``previous`` to ``current``.

    A positive number means a decrease (a drop). Returns ``None`` if it cannot
    be computed (missing values or non-positive baseline).
    """
    if previous is None or current is None:
        return None
    try:
        previous = float(previous)
        current = float(current)
    except (TypeError, ValueError):
        return None
    if previous <= 0:
        return None
    return (previous - current) / previous * 100.0
