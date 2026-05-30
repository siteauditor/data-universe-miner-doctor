"""The Data Universe (SN13) profile — the default.

It references the existing engine pieces verbatim (same check classes, same
default config, same fix-order builder), so running with this profile is
identical to the original behavior.
"""

from __future__ import annotations

from du_doctor.checks import CHECK_CLASSES, build_suggested_fix_order
from du_doctor.config import default_config_dict
from du_doctor.profiles.base import SubnetProfile

DATA_UNIVERSE = SubnetProfile(
    key="data-universe",
    name="Data Universe",
    netuid=13,
    repo_url="https://github.com/macrocosm-os/data-universe",
    build_default_config=default_config_dict,
    check_classes=list(CHECK_CLASSES),
    fix_order_builder=build_suggested_fix_order,
)
