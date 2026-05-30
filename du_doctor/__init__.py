"""Data Universe Miner Doctor.

A read-only, subnet-specific diagnostic CLI for Bittensor *Data Universe*
(NETUID 13) miners. It answers a single focused question:

    "Why is my Data Universe miner not earning well?"

This package is intentionally read-only. It never asks for seed phrases,
mnemonics, private keys, or wallet passwords, never moves TAO, never registers
hotkeys, and never uploads anything off the machine. See ``README.md``.
"""

__version__ = "0.1.0"

SUBNET_NAME = "Data Universe"
NETUID = 13
SUBNET_REPO_URL = "https://github.com/macrocosm-os/data-universe"

__all__ = ["__version__", "SUBNET_NAME", "NETUID", "SUBNET_REPO_URL"]
