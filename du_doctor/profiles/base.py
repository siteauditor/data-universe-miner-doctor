"""Subnet profile abstraction.

A ``SubnetProfile`` bundles everything subnet-specific: the default config, the
ordered list of check classes to run, and the prioritized-fix builder. The core
engine (`run_checks`, `load_config`) is profile-agnostic — pass a profile to
target a different subnet. The default profile (Data Universe / SN13) reproduces
the original behavior exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

# A fix-order builder takes (results, config, run_context) -> list[str], matching
# du_doctor.checks.build_suggested_fix_order.
FixOrderBuilder = Callable[..., list]


@dataclass(frozen=True)
class SubnetProfile:
    key: str  # CLI/registry id, e.g. "data-universe"
    name: str  # human name
    netuid: int
    repo_url: str
    build_default_config: Callable[[], dict[str, Any]]
    check_classes: list  # ordered list of BaseCheck subclasses
    fix_order_builder: FixOrderBuilder
