"""Multi-subnet profiles: registry, default parity, custom profile, config base."""

from __future__ import annotations

from du_doctor.checks import run_checks
from du_doctor.checks.system_check import SystemCheck
from du_doctor.config import load_config
from du_doctor.models import CheckCategory
from du_doctor.profiles import default_profile, get_profile, list_profiles
from du_doctor.profiles.base import SubnetProfile
from du_doctor.profiles.data_universe import DATA_UNIVERSE


def test_registry_default_and_lookup():
    assert get_profile() is DATA_UNIVERSE
    assert get_profile("data-universe") is DATA_UNIVERSE
    assert default_profile() is DATA_UNIVERSE
    assert "data-universe" in list_profiles()


def test_unknown_profile_raises():
    import pytest

    with pytest.raises(KeyError):
        get_profile("no-such-subnet")


def test_default_profile_reproduces_check_set():
    cfg = load_config()
    default = run_checks(cfg, save_snapshot_enabled=False)
    profiled = run_checks(cfg, save_snapshot_enabled=False, profile=DATA_UNIVERSE)
    # The default code path and the Data Universe profile must be indistinguishable:
    # same checks in the same order (id/category/status) AND the same prioritized
    # fix list (which comes from the profile's fix_order_builder).
    assert [(c.id, c.category, c.status) for c in default.checks] == [
        (c.id, c.category, c.status) for c in profiled.checks
    ]
    assert default.suggested_fix_order == profiled.suggested_fix_order


def _mini_profile() -> SubnetProfile:
    return SubnetProfile(
        key="mini",
        name="Mini",
        netuid=1,
        repo_url="",
        build_default_config=lambda: {"netuid": 1, "subnet_name": "Mini", "network": "finney"},
        check_classes=[SystemCheck],
        fix_order_builder=lambda results, config, ctx: [],
    )


def test_custom_profile_runs_only_its_checks():
    cfg = load_config()
    report = run_checks(cfg, save_snapshot_enabled=False, profile=_mini_profile())
    # Only the SystemCheck ran -> every result is in the SYSTEM category.
    assert {c.category for c in report.checks} == {CheckCategory.SYSTEM}
    assert all(not c.id.startswith(("bt_", "du_")) for c in report.checks)
    assert report.suggested_fix_order == []


def test_custom_profile_supplies_config_base():
    cfg = load_config(profile=_mini_profile())  # no config file in the isolated home
    assert cfg.netuid == 1
    assert cfg.subnet_name == "Mini"
