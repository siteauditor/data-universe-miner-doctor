"""Bittensor chain / metagraph checks (read-only).

Everything here is strictly read-only:
  * The SDK is imported lazily so the rest of the tool works without it.
  * Hotkeys are resolved either from an explicit ``hotkey_ss58`` or by reading
    the PUBLIC ss58 from the hotkey file on disk — the wallet is NEVER unlocked
    and no secret material is ever read or printed.
  * Subtensor/metagraph are queried but nothing is ever submitted.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from du_doctor.checks.base import BaseCheck
from du_doctor.models import CheckCategory, CheckResult, CheckStatus
from du_doctor.storage.snapshots import percent_drop
from du_doctor.utils.redact import mask_hotkey


def _import_bittensor():
    try:
        import bittensor as bt  # type: ignore

        return bt
    except Exception:  # noqa: BLE001 - ImportError or heavy-import side effects
        return None


def resolve_hotkey_ss58(config) -> tuple[Optional[str], str]:
    """Return ``(ss58, source)`` resolving the hotkey without unlocking anything.

    Priority: explicit ``hotkey_ss58`` > public ss58 read from the hotkey file
    on disk. Returns ``(None, "")`` if it cannot be resolved safely.
    """
    if config.hotkey_ss58:
        return config.hotkey_ss58.strip(), "config/cli"

    if config.wallet_name and config.wallet_hotkey_name:
        path = (
            Path.home()
            / ".bittensor"
            / "wallets"
            / config.wallet_name
            / "hotkeys"
            / config.wallet_hotkey_name
        )
        try:
            if path.is_file():
                raw = path.read_text(encoding="utf-8", errors="replace")
                data = json.loads(raw)
                ss58 = data.get("ss58Address") or data.get("ss58_address")
                if ss58:
                    return str(ss58).strip(), "wallet hotkey file (public ss58 only)"
        except Exception:  # noqa: BLE001 - never fail; just fall through
            pass
    return None, ""


class BittensorCheck(BaseCheck):
    category = CheckCategory.BITTENSOR
    name = "bittensor"

    def run(self) -> list[CheckResult]:
        results: list[CheckResult] = []

        bt = _import_bittensor()
        if bt is None:
            results.append(
                self.result(
                    "bt_sdk",
                    "Bittensor SDK",
                    CheckStatus.CRITICAL,
                    "bittensor SDK is not importable in this environment.",
                    suggested_fixes=[
                        "Install bittensor in your miner environment: pip install bittensor",
                        "Run du-doctor from the same venv as your miner for chain checks.",
                    ],
                )
            )
            results.append(
                self._skipped("bt_subtensor", "Subtensor connection", "bittensor SDK unavailable.")
            )
            results.append(self._skipped("bt_metagraph", "Metagraph", "bittensor SDK unavailable."))
            return results

        version = getattr(bt, "__version__", "unknown")
        results.append(
            self.result(
                "bt_sdk",
                "Bittensor SDK",
                CheckStatus.OK,
                f"bittensor SDK installed (v{version}).",
                details={"version": str(version)},
            )
        )

        # --- Subtensor connection ---
        subtensor, block = self._connect(bt)
        if subtensor is None:
            results.append(
                self.result(
                    "bt_subtensor",
                    "Subtensor connection",
                    CheckStatus.CRITICAL,
                    f"Could not connect to subtensor network '{self.config.network}'.",
                    suggested_fixes=[
                        "Check connectivity and that the network name is correct (e.g. finney).",
                        "The miner cannot sync the chain without a subtensor connection.",
                    ],
                )
            )
            results.append(self._skipped("bt_metagraph", "Metagraph", "No subtensor connection."))
            return results
        results.append(
            self.result(
                "bt_subtensor",
                "Subtensor connection",
                CheckStatus.OK,
                f"Connected to '{self.config.network}'"
                + (f" (block {block})." if block is not None else "."),
                details={"network": self.config.network, "block": block},
            )
        )

        # --- Hotkey resolution ---
        hotkey, source = resolve_hotkey_ss58(self.config)
        if not hotkey:
            results.append(
                self.result(
                    "bt_hotkey",
                    "Hotkey resolution",
                    CheckStatus.WARNING,
                    "Could not resolve a hotkey ss58 safely.",
                    suggested_fixes=[
                        "Pass --hotkey <ss58> or set hotkey_ss58 in config.",
                        "(Wallet-name lookup only reads the public ss58; it never unlocks keys.)",
                    ],
                )
            )
            results.append(self._skipped("bt_metagraph", "Metagraph", "No hotkey to look up."))
            return results
        results.append(
            self.result(
                "bt_hotkey",
                "Hotkey resolution",
                CheckStatus.OK,
                f"Resolved hotkey {mask_hotkey(hotkey)} (from {source}).",
                details={"hotkey_masked": mask_hotkey(hotkey), "source": source},
            )
        )
        self.ctx.snapshot["hotkey"] = hotkey
        self.ctx.snapshot["netuid"] = self.config.netuid

        # --- Metagraph + metrics ---
        results.extend(self._check_metagraph(bt, subtensor, hotkey))
        return results

    # ------------------------------------------------------------------ #
    def _connect(self, bt) -> tuple[Optional[Any], Optional[int]]:
        try:
            subtensor = bt.subtensor(network=self.config.network)
        except Exception:  # noqa: BLE001
            try:
                subtensor = bt.subtensor()
            except Exception:  # noqa: BLE001
                return None, None
        block = None
        try:
            block = int(subtensor.get_current_block())
        except Exception:  # noqa: BLE001
            block = None
        return subtensor, block

    def _load_metagraph(self, bt, subtensor):
        # Different SDK versions expose this differently; try the common paths.
        try:
            return subtensor.metagraph(self.config.netuid)
        except Exception:  # noqa: BLE001
            pass
        try:
            return bt.metagraph(netuid=self.config.netuid, network=self.config.network, sync=True)
        except Exception:  # noqa: BLE001
            return None

    def _check_metagraph(self, bt, subtensor, hotkey: str) -> list[CheckResult]:
        metagraph = self._load_metagraph(bt, subtensor)
        if metagraph is None:
            return [
                self._skipped(
                    "bt_metagraph",
                    "Metagraph",
                    f"Could not load metagraph for netuid {self.config.netuid}.",
                )
            ]

        hotkeys = list(getattr(metagraph, "hotkeys", []) or [])
        prev = self.ctx.previous_snapshot
        was_registered = bool(prev and prev.get("uid") is not None) if prev else False

        if hotkey not in hotkeys:
            self.ctx.snapshot["registered"] = False
            self.ctx.note("registered", False)
            extra = ""
            if was_registered:
                extra = " It was registered in a previous snapshot — possibly deregistered."
            return [
                self.result(
                    "bt_metagraph",
                    "Subnet registration",
                    CheckStatus.CRITICAL,
                    f"Hotkey {mask_hotkey(hotkey)} is NOT registered on subnet "
                    f"{self.config.netuid}." + extra,
                    details={"netuid": self.config.netuid, "neurons": len(hotkeys)},
                    suggested_fixes=[
                        "Register the hotkey on subnet 13 before mining (btcli subnet register).",
                        "Until registered, the miner earns nothing.",
                    ],
                )
            ]

        uid = hotkeys.index(hotkey)
        metrics = self._extract_metrics(metagraph, uid)
        axon = self._extract_axon(metagraph, uid)
        if axon:
            self.ctx.axon = axon

        # Persist into the snapshot.
        self.ctx.snapshot.update(
            {
                "uid": uid,
                "registered": True,
                "rank": metrics.get("rank"),
                "trust": metrics.get("trust"),
                "consensus": metrics.get("consensus"),
                "incentive": metrics.get("incentive"),
                "emission": metrics.get("emission"),
                "active": metrics.get("active"),
                "stake": metrics.get("stake"),
                "dividends": metrics.get("dividends"),
                "validator_trust": metrics.get("validator_trust"),
            }
        )
        self.ctx.note("registered", True)
        self.ctx.note("incentive", metrics.get("incentive"))

        details = {"uid": uid, **metrics}
        if axon:
            details["axon"] = axon
        summary = (
            f"Registered on subnet {self.config.netuid}, UID {uid} "
            f"(incentive {_fmt(metrics.get('incentive'))}, emission {_fmt(metrics.get('emission'))})."
        )
        reg_result = self.result(
            "bt_metagraph",
            "Subnet registration",
            CheckStatus.OK,
            summary,
            details=details,
        )

        results = [reg_result]
        results.append(self._drop_result(metrics))
        return results

    def _extract_metrics(self, metagraph, uid: int) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, attr in (
            ("rank", "ranks"),
            ("trust", "trust"),
            ("consensus", "consensus"),
            ("incentive", "incentive"),
            ("emission", "emission"),
            ("stake", "stake"),
            ("dividends", "dividends"),
            ("validator_trust", "validator_trust"),
        ):
            out[key] = _index_float(getattr(metagraph, attr, None), uid)
        # active is boolean-ish
        active = _index_value(getattr(metagraph, "active", None), uid)
        out["active"] = bool(active) if active is not None else None
        last_update = _index_value(getattr(metagraph, "last_update", None), uid)
        if last_update is not None:
            out["last_update"] = int(last_update)
        return out

    def _extract_axon(self, metagraph, uid: int) -> Optional[dict[str, Any]]:
        axons = getattr(metagraph, "axons", None)
        if not axons:
            return None
        try:
            axon = axons[uid]
        except Exception:  # noqa: BLE001
            return None
        try:
            return {
                "ip": getattr(axon, "ip", None),
                "port": getattr(axon, "port", None),
                "ip_type": getattr(axon, "ip_type", None),
            }
        except Exception:  # noqa: BLE001
            return None

    def _drop_result(self, metrics: dict[str, Any]) -> CheckResult:
        prev = self.ctx.previous_snapshot
        if not prev:
            return self.result(
                "bt_drops",
                "Metric drops",
                CheckStatus.SKIPPED,
                "No previous snapshot available yet. Run again later to detect drops.",
            )

        th = self.config.thresholds
        comparisons = [
            ("incentive", "incentive", th.incentive_drop_percent),
            ("emission", "emission", th.emission_drop_percent),
            ("rank", "rank", th.rank_drop_percent),
        ]
        drops: list[str] = []
        details: dict[str, Any] = {}
        for label, key, threshold in comparisons:
            drop = percent_drop(prev.get(key), metrics.get(key))
            if drop is None:
                continue
            details[f"{label}_drop_percent"] = round(drop, 1)
            if drop >= threshold:
                drops.append(f"{label} dropped {drop:.0f}% (>= {threshold:.0f}%)")

        if drops:
            return self.result(
                "bt_drops",
                "Metric drops",
                CheckStatus.WARNING,
                "; ".join(drops) + " since the last snapshot.",
                details=details,
                suggested_fixes=[
                    "A drop often follows downtime, stale data, or stronger competition.",
                    "Check process uptime, data freshness, and scraper health below.",
                ],
            )
        return self.result(
            "bt_drops",
            "Metric drops",
            CheckStatus.OK,
            "No significant incentive/emission/rank drop since the last snapshot.",
            details=details,
        )

    # ------------------------------------------------------------------ #
    def _skipped(self, id: str, title: str, reason: str) -> CheckResult:
        return self.result(id, title, CheckStatus.SKIPPED, reason)


# --------------------------------------------------------------------------- #
# Tensor/array helpers (tolerant of torch tensors, numpy arrays, or lists)
# --------------------------------------------------------------------------- #
def _index_value(container: Any, uid: int) -> Any:
    if container is None:
        return None
    try:
        value = container[uid]
    except Exception:  # noqa: BLE001
        return None
    # Unwrap 0-d tensors / numpy scalars.
    for attr in ("item",):
        if hasattr(value, attr):
            try:
                return getattr(value, attr)()
            except Exception:  # noqa: BLE001
                pass
    return value


def _index_float(container: Any, uid: int) -> Optional[float]:
    value = _index_value(container, uid)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"
