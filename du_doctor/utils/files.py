"""Filesystem helpers: path expansion, efficient log tailing, and file finding."""

from __future__ import annotations

import os
from fnmatch import fnmatch
from pathlib import Path
from typing import Iterable


def expand_path(path: str | os.PathLike | None) -> Path | None:
    """Expand ``~`` and environment variables. Returns ``None`` for empty input.

    Does NOT resolve symlinks or require existence — callers decide that.
    """
    if path is None:
        return None
    text = str(path).strip()
    if not text:
        return None
    return Path(os.path.expandvars(os.path.expanduser(text)))


def expand_paths(paths: Iterable[str]) -> list[Path]:
    """Expand a list of path strings, dropping empties."""
    out: list[Path] = []
    for p in paths:
        ep = expand_path(p)
        if ep is not None:
            out.append(ep)
    return out


def read_last_lines(path: Path, n: int = 500, max_bytes: int = 5_000_000) -> list[str]:
    """Return up to the last ``n`` lines of a text file.

    Reads at most ``max_bytes`` from the end of the file so we never load a
    multi-gigabyte log into memory. Never raises — returns ``[]`` on any error.
    """
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            if size > max_bytes:
                fh.seek(-max_bytes, os.SEEK_END)
            data = fh.read()
        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        return lines[-n:]
    except Exception:  # noqa: BLE001 - missing/locked/binary files are tolerated
        return []


def find_files(
    roots: Iterable[Path],
    patterns: Iterable[str],
    max_files: int = 200,
) -> list[Path]:
    """Recursively find files under ``roots`` matching any glob in ``patterns``.

    Deduplicates, skips unreadable trees, and caps the result to ``max_files``.
    """
    patterns = list(patterns)
    seen: set[Path] = set()
    out: list[Path] = []
    for root in roots:
        try:
            if root.is_file():
                # A direct file path is included only if it matches a pattern.
                if root not in seen and any(fnmatch(root.name, pat) for pat in patterns):
                    seen.add(root)
                    out.append(root)
                continue
            if not root.is_dir():
                continue
            for pattern in patterns:
                for match in root.rglob(pattern):
                    if not match.is_file():
                        continue
                    if match in seen:
                        continue
                    seen.add(match)
                    out.append(match)
                    if len(out) >= max_files:
                        return out
        except Exception:  # noqa: BLE001 - permission errors etc.
            continue
    return out


def recent_log_files(roots: Iterable[Path], limit: int = 20) -> list[Path]:
    """Find ``*.log`` files (plus a couple of common variants) under roots.

    Returns the most-recently-modified files first.
    """
    candidates = find_files(roots, ["*.log", "*.out", "*-error.log", "*-out.log"])

    # Also accept a direct file path that isn't named *.log (e.g. ./pm2.log
    # handled above, but a path like ./miner.txt passed explicitly).
    def _mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except Exception:  # noqa: BLE001
            return 0.0

    candidates.sort(key=_mtime, reverse=True)
    return candidates[:limit]
