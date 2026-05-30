"""Lightweight version parsing — just enough for ``>=3.10`` style checks.

We deliberately avoid pulling in ``packaging`` to keep the dependency surface
small; these helpers only need to compare dotted numeric versions.
"""

from __future__ import annotations

import re

_NUM_RE = re.compile(r"\d+")


def parse_version(text: str) -> tuple[int, ...]:
    """Extract a numeric version tuple from an arbitrary string.

    >>> parse_version("Python 3.10.12")
    (3, 10, 12)
    >>> parse_version("git version 2.43.0")
    (2, 43, 0)
    """
    if not text:
        return ()
    nums = _NUM_RE.findall(text)
    return tuple(int(n) for n in nums[:4])


def version_ge(version: str, minimum: str) -> bool:
    """True if ``version >= minimum`` by tuple comparison."""
    v = parse_version(version)
    m = parse_version(minimum)
    if not v or not m:
        return False
    # Pad to equal length for fair comparison.
    length = max(len(v), len(m))
    v = v + (0,) * (length - len(v))
    m = m + (0,) * (length - len(m))
    return v >= m


def satisfies_min(version: str, spec: str) -> bool:
    """Check a version against a ``>=X.Y`` style spec string.

    Only the minimum-version semantics needed for Data Universe are supported.
    A spec without a comparator is treated as a minimum.
    """
    minimum = ".".join(str(n) for n in parse_version(spec))
    if not minimum:
        return True  # nothing to compare against
    return version_ge(version, minimum)
