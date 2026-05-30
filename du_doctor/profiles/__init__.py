"""Subnet profile registry + discovery.

Built-in profiles plus any registered via the ``du_doctor.profiles`` entry-point
group (third-party subnets). ``get_profile(None)`` returns the default
(Data Universe).
"""

from __future__ import annotations

import logging
from typing import Optional

from du_doctor.profiles.base import SubnetProfile
from du_doctor.profiles.data_universe import DATA_UNIVERSE

log = logging.getLogger("du_doctor.profiles")

_BUILTIN: dict[str, SubnetProfile] = {DATA_UNIVERSE.key: DATA_UNIVERSE}
DEFAULT_PROFILE_KEY = DATA_UNIVERSE.key


def _discover() -> dict[str, SubnetProfile]:
    profiles = dict(_BUILTIN)
    try:
        from importlib.metadata import entry_points

        eps = entry_points()
        group = (
            eps.select(group="du_doctor.profiles")
            if hasattr(eps, "select")
            else eps.get("du_doctor.profiles", [])  # type: ignore[attr-defined]
        )
        for ep in group:
            try:
                obj = ep.load()
                if isinstance(obj, SubnetProfile):
                    profiles[obj.key] = obj
            except Exception:  # noqa: BLE001 - a bad plugin must not break discovery
                log.warning("Failed to load subnet profile plugin %r", getattr(ep, "name", "?"))
    except Exception:  # noqa: BLE001
        pass
    return profiles


def list_profiles() -> dict[str, SubnetProfile]:
    return _discover()


def default_profile() -> SubnetProfile:
    return DATA_UNIVERSE


def get_profile(key: Optional[str] = None) -> SubnetProfile:
    """Return the profile for ``key`` (default: Data Universe). Raises KeyError if unknown."""
    if not key:
        return DATA_UNIVERSE
    profiles = _discover()
    if key not in profiles:
        raise KeyError(key)
    return profiles[key]


__all__ = [
    "SubnetProfile",
    "get_profile",
    "list_profiles",
    "default_profile",
    "DEFAULT_PROFILE_KEY",
]
