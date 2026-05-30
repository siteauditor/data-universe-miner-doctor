"""Shared pytest fixtures.

The autouse fixture points ``DU_DOCTOR_HOME`` at a throwaway temp directory so
tests never read or write the real ``~/.du-doctor`` config or snapshots.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / ".du-doctor"
    monkeypatch.setenv("DU_DOCTOR_HOME", str(home))
    yield home
