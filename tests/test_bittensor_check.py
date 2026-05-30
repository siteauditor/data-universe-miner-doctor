"""Unit tests for the Bittensor metagraph metric extraction.

These exercise ``BittensorCheck`` directly with a tiny fake metagraph (plain
Python lists), so they need neither the bittensor SDK nor a live chain. They
lock in that every spec metric — including the newer ``stake`` / ``dividends`` /
``validator_trust`` — is collected, that missing SDK fields degrade to ``None``
instead of crashing, and that the values reach both the result details and the
saved snapshot.
"""

from __future__ import annotations

from du_doctor.checks.base import RunContext
from du_doctor.checks.bittensor_check import BittensorCheck
from du_doctor.models import CheckStatus, DoctorConfig
from du_doctor.storage.snapshots import build_snapshot


class FakeAxon:
    def __init__(self, ip, port, ip_type=4):
        self.ip = ip
        self.port = port
        self.ip_type = ip_type


class FakeMetagraph:
    """A 3-neuron metagraph exposing the full-name attribute API the check uses."""

    def __init__(self):
        self.hotkeys = ["5AAA", "5BBB", "5CCC"]
        self.ranks = [0.1, 0.2, 0.3]
        self.trust = [0.4, 0.5, 0.6]
        self.consensus = [0.7, 0.8, 0.9]
        self.incentive = [0.01, 0.02, 0.03]
        self.emission = [0.001, 0.002, 0.003]
        self.stake = [100.0, 200.0, 300.0]
        self.dividends = [0.11, 0.22, 0.33]
        self.validator_trust = [0.0, 0.9, 0.0]
        self.active = [1, 1, 0]
        self.last_update = [10, 20, 30]
        self.axons = [
            FakeAxon("1.2.3.4", 8091),
            FakeAxon("5.6.7.8", 9000),
            FakeAxon("0.0.0.0", 0),
        ]


def _check() -> BittensorCheck:
    return BittensorCheck(DoctorConfig(), RunContext())


def test_extract_metrics_includes_all_fields():
    metrics = _check()._extract_metrics(FakeMetagraph(), uid=1)
    assert metrics["rank"] == 0.2
    assert metrics["trust"] == 0.5
    assert metrics["consensus"] == 0.8
    assert metrics["incentive"] == 0.02
    assert metrics["emission"] == 0.002
    # The newly added metrics (spec §12 "collect if available").
    assert metrics["stake"] == 200.0
    assert metrics["dividends"] == 0.22
    assert metrics["validator_trust"] == 0.9
    assert metrics["active"] is True
    assert metrics["last_update"] == 20


def test_extract_metrics_tolerates_missing_sdk_fields():
    """A metagraph that lacks newer attributes must degrade to None, not crash."""

    class Sparse:
        hotkeys = ["5AAA"]
        incentive = [0.5]

    metrics = _check()._extract_metrics(Sparse(), uid=0)
    assert metrics["incentive"] == 0.5
    assert metrics["stake"] is None
    assert metrics["dividends"] is None
    assert metrics["validator_trust"] is None
    assert metrics["active"] is None
    assert "last_update" not in metrics  # only included when present


def test_check_metagraph_publishes_new_metrics_to_details_and_snapshot():
    config = DoctorConfig(hotkey_ss58="5BBB")
    ctx = RunContext()
    check = BittensorCheck(config, ctx)
    fake_mg = FakeMetagraph()

    class FakeSubtensor:
        def metagraph(self, netuid):  # noqa: ARG002 - signature must match
            return fake_mg

    results = check._check_metagraph(bt=object(), subtensor=FakeSubtensor(), hotkey="5BBB")
    registration = next(r for r in results if r.id == "bt_metagraph")

    assert registration.status == CheckStatus.OK
    assert registration.details["uid"] == 1
    assert registration.details["stake"] == 200.0
    assert registration.details["dividends"] == 0.22
    assert registration.details["validator_trust"] == 0.9

    # The snapshot the runner persists must carry the new metrics too.
    assert ctx.snapshot["stake"] == 200.0
    assert ctx.snapshot["dividends"] == 0.22
    assert ctx.snapshot["validator_trust"] == 0.9
    # Axon for the resolved uid is published for the network check.
    assert ctx.axon == {"ip": "5.6.7.8", "port": 9000, "ip_type": 4}


def test_build_snapshot_persists_new_metrics():
    snap = build_snapshot(
        {
            "hotkey": "5BBB",
            "stake": 200.0,
            "dividends": 0.22,
            "validator_trust": 0.9,
        }
    )
    assert snap["stake"] == 200.0
    assert snap["dividends"] == 0.22
    assert snap["validator_trust"] == 0.9
