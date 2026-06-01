"""Data Universe Miner Doctor.

A read-only, subnet-specific diagnostic CLI for Bittensor *Data Universe*
(NETUID 13) miners. It answers a single focused question:

    "Why is my Data Universe miner not earning well?"

This package is intentionally read-only. It never asks for seed phrases,
mnemonics, private keys, or wallet passwords, never moves TAO, never registers
hotkeys, and never uploads anything off the machine. See ``README.md``.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    # Single source of truth is pyproject.toml; read it back from the installed
    # package metadata so the code version can never drift from the release.
    __version__ = _pkg_version("data-universe-miner-doctor")
except PackageNotFoundError:  # running from a source tree without an install
    __version__ = "0.0.0+local"

SUBNET_NAME = "Data Universe"
NETUID = 13
SUBNET_REPO_URL = "https://github.com/macrocosm-os/data-universe"

__all__ = ["__version__", "SUBNET_NAME", "NETUID", "SUBNET_REPO_URL"]
