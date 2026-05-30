"""Local data-health checks for Data Universe.

We don't assume the exact internal schema. Instead we locate the local
SQLite/data files, judge their freshness and growth, and (best-effort, fully
read-only) peek at table names / row counts to confirm data is actually landing.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from du_doctor.checks.base import BaseCheck
from du_doctor.models import CheckCategory, CheckResult, CheckStatus
from du_doctor.utils.files import expand_path, expand_paths, find_files
from du_doctor.utils.formatting import human_age_from_mtime, human_bytes

_DB_PATTERNS = ["*.db", "*.sqlite", "*.sqlite3"]
_REPO_DATA_SUBDIRS = ["data", "database", "storage", "local_storage", "SqliteMinerStorage"]
_TIMESTAMP_COLUMNS = [
    "created_at",
    "datetime",
    "timestamp",
    "scraped_at",
    "updated_at",
    "datetime_inserted",
]
# Below this gap between snapshots we don't judge growth (the DB can't grow in seconds).
_MIN_GROWTH_INTERVAL_SECONDS = 120


def _count_rows(
    conn: sqlite3.Connection, cur: sqlite3.Cursor, table: str
) -> tuple[Optional[int], bool]:
    """Count rows in ``table``, bounding the work so a huge table can't stall.

    Returns ``(count, exact)``. A SQLite progress handler aborts a runaway
    ``COUNT(*)``; on abort we fall back to a fast ``MAX(rowid)`` estimate
    (``exact=False``). Returns ``(None, True)`` if counting isn't possible.
    """
    budget = {"calls": 0}
    # ~4e8 VM ops before aborting (counts well over 100M rows; ~sub-second).
    limit = 200_000

    def _guard() -> int:
        budget["calls"] += 1
        return 1 if budget["calls"] > limit else 0

    conn.set_progress_handler(_guard, 2000)
    try:
        cur.execute(f'SELECT COUNT(*) FROM "{table}"')
        value = int(cur.fetchone()[0])
        conn.set_progress_handler(None, 0)
        return value, True
    except sqlite3.OperationalError:
        # Interrupted (table too large) — clear handler and try a fast estimate.
        conn.set_progress_handler(None, 0)
    except Exception:  # noqa: BLE001
        conn.set_progress_handler(None, 0)
        return None, True

    try:
        cur.execute(f'SELECT MAX(_rowid_) FROM "{table}"')
        val = cur.fetchone()[0]
        if val is not None:
            return int(val), False
    except Exception:  # noqa: BLE001
        pass
    return None, True


def _snapshot_age_seconds(prev: dict) -> Optional[float]:
    """Seconds since a previous snapshot was taken, or None if unknown."""
    ts = prev.get("timestamp")
    if not ts:
        return None
    try:
        when = datetime.fromisoformat(str(ts))
    except (ValueError, TypeError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max((datetime.now(timezone.utc) - when).total_seconds(), 0.0)


class DataUniverseDataCheck(BaseCheck):
    category = CheckCategory.DATA_UNIVERSE_DATA
    name = "data_universe_data"

    def run(self) -> list[CheckResult]:
        roots = self._data_roots()
        db_files = find_files(roots, _DB_PATTERNS, max_files=50)

        if not db_files:
            self.ctx.note("no_local_data", True)
            return [
                self.result(
                    "du_data_files",
                    "Local data files",
                    CheckStatus.WARNING,
                    "No local database files (*.db / *.sqlite) found in the configured data paths.",
                    details={"searched": [str(r) for r in roots]},
                    suggested_fixes=[
                        "Check whether your scraper is producing local data.",
                        "Confirm data_paths point at where the miner writes its DB.",
                    ],
                )
            ]

        self.ctx.note("no_local_data", False)
        # Record fingerprints for the snapshot / growth comparison. Keyed by
        # absolute path so comparisons are stable regardless of the cwd a later
        # run is launched from.
        sizes: dict[str, int] = {}
        mtimes: dict[str, float] = {}
        for f in db_files:
            try:
                st = f.stat()
                key = os.path.abspath(str(f))
                sizes[key] = st.st_size
                mtimes[key] = st.st_mtime
            except Exception:  # noqa: BLE001
                continue
        self.ctx.snapshot["data_file_sizes"] = sizes
        self.ctx.snapshot["data_file_mtimes"] = mtimes

        results: list[CheckResult] = []
        results.append(self._summary_result(db_files, sizes))
        results.append(self._freshness_result(db_files, mtimes))
        results.append(self._growth_result(sizes, mtimes))
        table_result = self._sqlite_table_result(db_files, sizes)
        if table_result is not None:
            results.append(table_result)
        return results

    # ------------------------------------------------------------------ #
    def _data_roots(self) -> list[Path]:
        roots = expand_paths(self.config.data_paths)
        repo = expand_path(self.config.subnet_repo_path)
        if repo is not None and repo.exists():
            roots.append(repo)  # repo root (DU often writes the DB at the repo root)
            for sub in _REPO_DATA_SUBDIRS:
                roots.append(repo / sub)
        # Deduplicate, keep only existing.
        seen: set[str] = set()
        out: list[Path] = []
        for r in roots:
            key = str(r)
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
        return out

    def _summary_result(self, db_files: list[Path], sizes: dict[str, int]) -> CheckResult:
        total = sum(sizes.values())
        listing = [
            f"{Path(p).name}: {human_bytes(s)}"
            for p, s in sorted(sizes.items(), key=lambda kv: kv[1], reverse=True)
        ][:10]
        return self.result(
            "du_data_files",
            "Local data files",
            CheckStatus.OK,
            f"Found {len(db_files)} data file(s), total {human_bytes(total)}.",
            details={"count": len(db_files), "total_bytes": total, "files": listing},
            evidence=listing,
        )

    def _freshness_result(self, db_files: list[Path], mtimes: dict[str, float]) -> CheckResult:
        if not mtimes:
            return self.result(
                "du_data_freshness",
                "Data freshness",
                CheckStatus.SKIPPED,
                "Could not stat any data files for freshness.",
            )
        newest_path, newest_mtime = max(mtimes.items(), key=lambda kv: kv[1])
        age_hours = max((datetime.now(timezone.utc).timestamp() - newest_mtime) / 3600.0, 0.0)
        warn = self.config.thresholds.stale_data_warning_hours
        crit = self.config.thresholds.stale_data_critical_hours
        details = {
            "newest_file": Path(newest_path).name,
            "age_hours": round(age_hours, 1),
            "last_modified": human_age_from_mtime(newest_mtime),
        }

        if age_hours >= crit:
            self.ctx.note("stale_data", "critical")
            return self.result(
                "du_data_freshness",
                "Data freshness",
                CheckStatus.CRITICAL,
                f"Most recent data file was modified {human_age_from_mtime(newest_mtime)} "
                f"(> {crit}h). The scraper appears stalled.",
                details=details,
                suggested_fixes=[
                    "Check that the scraper is running and not erroring (see logs).",
                    "Verify scraper credentials and connectivity.",
                ],
            )
        if age_hours >= warn:
            self.ctx.note("stale_data", "warning")
            return self.result(
                "du_data_freshness",
                "Data freshness",
                CheckStatus.WARNING,
                f"Most recent data file was modified {human_age_from_mtime(newest_mtime)} "
                f"(> {warn}h). Data may be getting stale.",
                details=details,
                suggested_fixes=["Confirm the scraper is actively writing new data."],
            )
        self.ctx.note("stale_data", False)
        return self.result(
            "du_data_freshness",
            "Data freshness",
            CheckStatus.OK,
            f"Most recent data file updated {human_age_from_mtime(newest_mtime)}.",
            details=details,
        )

    def _growth_result(self, sizes: dict[str, int], mtimes: dict[str, float]) -> CheckResult:
        prev = self.ctx.previous_snapshot
        if not prev or not prev.get("data_file_sizes"):
            return self.result(
                "du_data_growth",
                "Data growth",
                CheckStatus.SKIPPED,
                "No previous snapshot available yet. Run again later to detect data growth.",
            )
        # Don't conclude "idle" until enough time has passed that the scraper
        # *should* have written. The window is the larger of a small floor and
        # ~2x the slowest configured scraper cadence (published by the config
        # check). This prevents false "idle" on rapid re-runs and when the watch
        # interval is shorter than the scraper cadence.
        elapsed = _snapshot_age_seconds(prev)
        min_window = float(_MIN_GROWTH_INTERVAL_SECONDS)
        cadence = self.ctx.get("max_cadence_seconds")
        if isinstance(cadence, (int, float)) and not isinstance(cadence, bool) and cadence > 0:
            min_window = max(min_window, float(cadence) * 2.0)
        if elapsed is not None and elapsed < min_window:
            return self.result(
                "du_data_growth",
                "Data growth",
                CheckStatus.SKIPPED,
                f"Last snapshot was {int(elapsed)}s ago — below the ~{int(min_window)}s window "
                "needed to assess growth for this scraper cadence.",
            )
        prev_sizes: dict[str, Any] = prev.get("data_file_sizes", {})
        prev_mtimes: dict[str, Any] = prev.get("data_file_mtimes", {})
        # Compare files present in both snapshots.
        common = [p for p in sizes if p in prev_sizes]
        if not common:
            return self.result(
                "du_data_growth",
                "Data growth",
                CheckStatus.SKIPPED,
                "Data files changed since last snapshot; cannot compare growth this run.",
            )

        # Activity = the file changed size OR was written more recently. Using
        # mtime as well avoids false "idle" warnings for SQLite DBs whose file
        # size stays stable (page reuse / WAL) while data is still being added.
        def _changed(p: str) -> bool:
            size_changed = sizes[p] != prev_sizes.get(p)
            mtime_advanced = float(mtimes.get(p, 0)) > float(prev_mtimes.get(p, 0) or 0)
            return size_changed or mtime_advanced

        if any(_changed(p) for p in common):
            return self.result(
                "du_data_growth",
                "Data growth",
                CheckStatus.OK,
                "Local data changed (size or modified time) since the last check.",
            )
        self.ctx.note("data_idle", True)
        return self.result(
            "du_data_growth",
            "Data growth",
            CheckStatus.WARNING,
            "Local data size has not changed since last check. Scraper may be idle or blocked.",
            details={"files_compared": len(common)},
            suggested_fixes=[
                "Check the scraper logs for rate limits, auth failures, or empty responses.",
            ],
        )

    def _sqlite_table_result(
        self, db_files: list[Path], sizes: dict[str, int]
    ) -> Optional[CheckResult]:
        # Inspect the largest DB (most likely the real data store).
        if not sizes:
            return None
        target = Path(max(sizes.items(), key=lambda kv: kv[1])[0])
        try:
            uri = f"file:{target.as_posix()}?mode=ro&immutable=1"
            conn = sqlite3.connect(uri, uri=True, timeout=2.0)
        except Exception as exc:  # noqa: BLE001
            return self.result(
                "du_data_tables",
                "Data tables",
                CheckStatus.SKIPPED,
                f"Could not open {target.name} read-only: {exc}",
            )
        try:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = [row[0] for row in cur.fetchall() if not str(row[0]).startswith("sqlite_")]
            if not tables:
                return self.result(
                    "du_data_tables",
                    "Data tables",
                    CheckStatus.SKIPPED,
                    f"{target.name} has no user tables (schema unknown / empty).",
                    details={"db": target.name},
                )
            table_info = self._inspect_tables(conn, cur, tables)
            total_rows = sum(t.get("rows", 0) or 0 for t in table_info)
            latest = self._latest_timestamp(table_info)
            evidence = [
                f"{t['name']}: "
                + (
                    f"{t['rows']}{'' if t.get('rows_exact', True) else '+ (est.)'} rows"
                    if t.get("rows") is not None
                    else "row count unavailable"
                )
                for t in table_info
            ][:10]
            details = {"db": target.name, "tables": table_info, "latest_timestamp": latest}

            if total_rows == 0:
                return self.result(
                    "du_data_tables",
                    "Data tables",
                    CheckStatus.WARNING,
                    f"{target.name} has tables but 0 rows — no data has been stored yet.",
                    details=details,
                    evidence=evidence,
                    suggested_fixes=["Confirm the scraper is collecting and storing data."],
                )
            summary = f"{len(tables)} table(s), ~{total_rows} total rows in {target.name}."
            if latest:
                summary += f" Latest record: {latest}."
            return self.result(
                "du_data_tables",
                "Data tables",
                CheckStatus.OK,
                summary,
                details=details,
                evidence=evidence,
            )
        except Exception as exc:  # noqa: BLE001
            return self.result(
                "du_data_tables",
                "Data tables",
                CheckStatus.SKIPPED,
                f"Could not inspect tables in {target.name}: {exc}",
            )
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    def _inspect_tables(
        self, conn: sqlite3.Connection, cur: sqlite3.Cursor, tables: list[str]
    ) -> list[dict[str, Any]]:
        info: list[dict[str, Any]] = []
        for name in tables[:12]:
            entry: dict[str, Any] = {"name": name}
            rows, exact = _count_rows(conn, cur, name)
            entry["rows"] = rows
            entry["rows_exact"] = exact if rows is not None else True
            try:
                cur.execute(f'PRAGMA table_info("{name}")')
                cols = [str(r[1]) for r in cur.fetchall()]
                entry["columns"] = cols
                ts_col = next((c for c in cols if c.lower() in _TIMESTAMP_COLUMNS), None)
                if ts_col:
                    cur.execute(f'SELECT MAX("{ts_col}") FROM "{name}"')
                    val = cur.fetchone()[0]
                    if val is not None:
                        entry["latest_timestamp_column"] = ts_col
                        entry["latest_timestamp_value"] = str(val)
            except Exception:  # noqa: BLE001
                pass
            info.append(entry)
        return info

    def _latest_timestamp(self, table_info: list[dict[str, Any]]) -> Optional[str]:
        values = [
            t.get("latest_timestamp_value") for t in table_info if t.get("latest_timestamp_value")
        ]
        if not values:
            return None
        return max(values)
