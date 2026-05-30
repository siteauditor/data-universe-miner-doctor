"""Local data checks: discovery, freshness, and growth (incl. mtime logic)."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone

from du_doctor.checks.base import RunContext
from du_doctor.checks.data_universe_data_check import DataUniverseDataCheck, _count_rows
from du_doctor.config import load_config
from du_doctor.models import CheckStatus


def _make_db(path, rows: int = 10):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE DataEntity (uri TEXT, datetime TEXT)")
    con.executemany(
        "INSERT INTO DataEntity VALUES (?, ?)",
        [(f"u{i}", "2026-05-30T10:00:00Z") for i in range(rows)],
    )
    con.commit()
    con.close()


def _run(tmp_path, previous_snapshot=None):
    cfg = load_config()
    cfg.data_paths = [str(tmp_path)]
    cfg.subnet_repo_path = ""
    ctx = RunContext(previous_snapshot=previous_snapshot)
    results = DataUniverseDataCheck(cfg, ctx).run()
    return {r.id: r for r in results}, ctx


def test_no_db_files_warns(tmp_path):
    by_id, ctx = _run(tmp_path)
    assert by_id["du_data_files"].status == CheckStatus.WARNING
    assert ctx.get("no_local_data") is True


def test_finds_db_and_inspects_tables(tmp_path):
    db = tmp_path / "SqliteMinerStorage.sqlite"
    _make_db(db, rows=42)
    by_id, _ = _run(tmp_path)
    assert by_id["du_data_files"].status == CheckStatus.OK
    assert by_id["du_data_tables"].status == CheckStatus.OK
    assert "42" in by_id["du_data_tables"].summary


def test_growth_idle_when_size_and_mtime_unchanged(tmp_path):
    db = tmp_path / "data.sqlite"
    _make_db(db)
    key = os.path.abspath(str(db))
    st = db.stat()
    prev = {
        "data_file_sizes": {key: st.st_size},
        "data_file_mtimes": {key: st.st_mtime},
    }
    by_id, ctx = _run(tmp_path, previous_snapshot=prev)
    assert by_id["du_data_growth"].status == CheckStatus.WARNING
    assert ctx.get("data_idle") is True


def test_growth_skipped_when_previous_snapshot_too_recent(tmp_path):
    db = tmp_path / "data.sqlite"
    _make_db(db)
    key = os.path.abspath(str(db))
    st = db.stat()
    prev = {
        "timestamp": datetime.now(timezone.utc).isoformat(),  # just now
        "data_file_sizes": {key: st.st_size},
        "data_file_mtimes": {key: st.st_mtime},
    }
    by_id, ctx = _run(tmp_path, previous_snapshot=prev)
    # Too soon to judge growth — must not falsely warn "idle".
    assert by_id["du_data_growth"].status == CheckStatus.SKIPPED
    assert ctx.get("data_idle") is not True


def test_growth_ok_when_mtime_advanced_even_if_size_same(tmp_path):
    db = tmp_path / "data.sqlite"
    _make_db(db)
    key = os.path.abspath(str(db))
    st = db.stat()
    # Pretend the previous snapshot saw the same size but an OLDER mtime.
    prev = {
        "data_file_sizes": {key: st.st_size},
        "data_file_mtimes": {key: st.st_mtime - 3600},
    }
    by_id, ctx = _run(tmp_path, previous_snapshot=prev)
    assert by_id["du_data_growth"].status == CheckStatus.OK
    assert ctx.get("data_idle") is not True


def test_growth_window_widens_with_scraper_cadence(tmp_path):
    db = tmp_path / "data.sqlite"
    _make_db(db)
    key = os.path.abspath(str(db))
    st = db.stat()
    # Previous snapshot ~200s ago with identical fingerprints.
    ts = (datetime.now(timezone.utc) - timedelta(seconds=200)).isoformat()
    prev = {
        "timestamp": ts,
        "data_file_sizes": {key: st.st_size},
        "data_file_mtimes": {key: st.st_mtime},
    }
    cfg = load_config()
    cfg.data_paths = [str(tmp_path)]
    cfg.subnet_repo_path = ""

    # With a 1h cadence, 200s elapsed is far below the ~7200s window -> SKIPPED.
    ctx = RunContext(previous_snapshot=prev)
    ctx.note("max_cadence_seconds", 3600)
    by_id = {r.id: r for r in DataUniverseDataCheck(cfg, ctx).run()}
    assert by_id["du_data_growth"].status == CheckStatus.SKIPPED

    # With no cadence info, 200s clears the 120s floor -> idle WARNING fires.
    ctx2 = RunContext(previous_snapshot=prev)
    by_id2 = {r.id: r for r in DataUniverseDataCheck(cfg, ctx2).run()}
    assert by_id2["du_data_growth"].status == CheckStatus.WARNING


def test_count_rows_exact(tmp_path):
    db = tmp_path / "x.sqlite"
    _make_db(db, rows=7)
    conn = sqlite3.connect(db)
    try:
        count, exact = _count_rows(conn, conn.cursor(), "DataEntity")
    finally:
        conn.close()
    assert count == 7
    assert exact is True
