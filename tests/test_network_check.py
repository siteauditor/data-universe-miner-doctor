"""Network / axon port checks (uses real loopback sockets, no mocking)."""

from __future__ import annotations

import socket

import pytest

from du_doctor.checks.base import RunContext
from du_doctor.checks.network_check import NetworkCheck
from du_doctor.config import load_config
from du_doctor.models import CheckStatus


def _check(port):
    cfg = load_config()
    cfg.miner_port = port
    return {r.id: r for r in NetworkCheck(cfg, RunContext()).run()}


@pytest.fixture
def listening_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]
    yield port
    sock.close()


def _free_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def test_no_port_configured_is_skipped():
    cfg = load_config()
    cfg.miner_port = None
    by_id = {r.id: r for r in NetworkCheck(cfg, RunContext()).run()}
    assert by_id["axon_port"].status == CheckStatus.SKIPPED


def test_listening_port_is_ok(listening_port):
    by_id = _check(listening_port)
    assert by_id["axon_port"].status == CheckStatus.OK


def test_closed_port_is_not_ok():
    # Nothing is listening. On a normal OS the connect is refused -> CRITICAL;
    # on hosts that DROP loopback SYNs to closed ports it times out -> WARNING.
    # Either way it must not report OK (and must not be SKIPPED here, since we
    # can enumerate our own sockets).
    by_id = _check(_free_port())
    assert by_id["axon_port"].status in (CheckStatus.CRITICAL, CheckStatus.WARNING)


def test_probe_loopback_open_then_closed(listening_port):
    nc = NetworkCheck(load_config(), RunContext())
    assert nc._probe_loopback(listening_port) == "open"
    # A closed port is either actively refused or (on drop-filtering hosts) times
    # out — never reported as open.
    assert nc._probe_loopback(_free_port()) in ("refused", "timeout")
