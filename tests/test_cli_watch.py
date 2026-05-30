"""`watch` graceful-shutdown signal wiring."""

from __future__ import annotations

import signal

import pytest

from du_doctor.cli import _install_stop_signal_handlers


def test_install_stop_signal_handlers_routes_to_keyboardinterrupt():
    """SIGTERM / SIGBREAK should be translated into KeyboardInterrupt so the
    single ``except KeyboardInterrupt`` path in ``watch`` runs for all stops."""
    names = [n for n in ("SIGTERM", "SIGBREAK") if getattr(signal, n, None) is not None]
    originals = {getattr(signal, n): signal.getsignal(getattr(signal, n)) for n in names}
    try:
        _install_stop_signal_handlers()
        for n in names:
            sig = getattr(signal, n)
            handler = signal.getsignal(sig)
            assert callable(handler)
            with pytest.raises(KeyboardInterrupt):
                handler(sig, None)
    finally:
        for sig, original in originals.items():
            try:
                signal.signal(sig, original)
            except (TypeError, ValueError, OSError):
                pass
