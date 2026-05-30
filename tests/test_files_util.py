"""Filesystem helpers: find_files pattern handling + log tailing."""

from __future__ import annotations

from du_doctor.utils.files import find_files, read_last_lines


def test_find_files_matches_patterns_in_dir(tmp_path):
    (tmp_path / "a.db").write_text("x", encoding="utf-8")
    (tmp_path / "b.sqlite").write_text("x", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    found = {p.name for p in find_files([tmp_path], ["*.db", "*.sqlite"])}
    assert found == {"a.db", "b.sqlite"}


def test_find_files_direct_file_must_match_pattern(tmp_path):
    db = tmp_path / "real.db"
    db.write_text("x", encoding="utf-8")
    txt = tmp_path / "notes.txt"
    txt.write_text("x", encoding="utf-8")
    # A direct (non-dir) file root is only included if it matches a pattern.
    assert find_files([db], ["*.db"]) == [db]
    assert find_files([txt], ["*.db"]) == []


def test_read_last_lines_tails_file(tmp_path):
    f = tmp_path / "x.log"
    f.write_text("\n".join(f"line {i}" for i in range(1000)), encoding="utf-8")
    last = read_last_lines(f, n=5)
    assert last == [f"line {i}" for i in range(995, 1000)]


def test_read_last_lines_missing_file_returns_empty(tmp_path):
    assert read_last_lines(tmp_path / "nope.log") == []
