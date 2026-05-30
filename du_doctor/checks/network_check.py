"""Network / axon checks. Strictly LOCAL — no aggressive scanning.

Only runs meaningfully when ``miner_port`` is configured. It verifies the port
is actually listening locally, takes a best-effort look at ufw, and compares
the configured port against what the axon advertises on-chain (if the bittensor
check published axon info into the run context).
"""

from __future__ import annotations

import socket

import psutil

from du_doctor.checks.base import BaseCheck
from du_doctor.models import CheckCategory, CheckResult, CheckStatus
from du_doctor.utils.shell import command_exists, run_command


class NetworkCheck(BaseCheck):
    category = CheckCategory.NETWORK
    name = "network"

    def run(self) -> list[CheckResult]:
        port = self.config.miner_port
        if not port:
            return [
                self.result(
                    "axon_port",
                    "Axon / miner port",
                    CheckStatus.SKIPPED,
                    "miner_port not configured; skipping local port and axon checks.",
                    suggested_fixes=[
                        "Set miner_port (the axon port) in config or pass --miner-port to enable.",
                    ],
                )
            ]

        results = [self._check_local_port(port)]
        firewall = self._check_firewall(port)
        if firewall is not None:
            results.append(firewall)
        axon = self._check_axon_advertisement(port)
        if axon is not None:
            results.append(axon)
        return results

    # ------------------------------------------------------------------ #
    def _check_local_port(self, port: int) -> CheckResult:
        # psutil enumeration is reliable only when we can see the owning
        # process's socket (needs root to see other users' sockets on Linux).
        found, enumerated = self._psutil_listening(port)
        if found:
            return self.result(
                "axon_port",
                "Axon / miner port",
                CheckStatus.OK,
                f"Port {port} is listening locally.",
                details={"port": port},
            )

        # Fall back to an actual local TCP connect — this confirms a listener
        # regardless of which user owns it. Loopback only; not a network scan.
        probe = self._probe_loopback(port)
        details = {"port": port, "loopback_probe": probe, "socket_enumeration": enumerated}

        if probe == "open":
            return self.result(
                "axon_port",
                "Axon / miner port",
                CheckStatus.OK,
                f"Port {port} is accepting local connections (confirmed via loopback).",
                details=details,
            )
        if probe == "refused":
            return self.result(
                "axon_port",
                "Axon / miner port",
                CheckStatus.CRITICAL,
                f"Expected miner port {port} is not listening locally (connection refused). "
                "The axon may not be served.",
                details=details,
                suggested_fixes=[
                    "Confirm the miner process is running and serving its axon.",
                    "Check the miner's --axon.port / port argument matches your config.",
                ],
            )
        # Inconclusive (loopback timed out / odd error).
        if not enumerated:
            return self.result(
                "axon_port",
                "Axon / miner port",
                CheckStatus.SKIPPED,
                f"Could not enumerate sockets (needs elevated permissions) and the loopback "
                f"probe for port {port} was inconclusive. Verify manually (e.g. `ss -ltnp`).",
                details=details,
            )
        return self.result(
            "axon_port",
            "Axon / miner port",
            CheckStatus.WARNING,
            f"Port {port} was not found listening and did not answer on loopback; it may bind "
            "only to an external interface. Verify the miner is serving its axon.",
            details=details,
            suggested_fixes=["Confirm the axon is bound to a reachable interface/port."],
        )

    def _psutil_listening(self, port: int) -> tuple[bool, bool]:
        """Return ``(found, enumerated)``.

        ``enumerated`` is False when we lacked permission to list sockets, so a
        "not found" result is inconclusive rather than authoritative.
        """
        try:
            conns = psutil.net_connections(kind="inet")
        except (psutil.AccessDenied, PermissionError):
            return False, False
        except Exception:  # noqa: BLE001
            return False, False
        for conn in conns:
            laddr = conn.laddr
            if conn.status == psutil.CONN_LISTEN and laddr and getattr(laddr, "port", None) == port:
                return True, True
        return False, True

    def _probe_loopback(self, port: int) -> str:
        """Try a local TCP connect. Returns 'open', 'refused', or 'timeout'.

        IPv4 loopback is authoritative (bittensor axons bind 0.0.0.0); only if
        IPv4 is inconclusive (timeout) do we consult IPv6, and a definitive
        'refused' always beats an IPv6 'timeout'.
        """
        ipv4 = self._connect_once("127.0.0.1", socket.AF_INET, port)
        if ipv4 in ("open", "refused"):
            return ipv4
        ipv6 = self._connect_once("::1", socket.AF_INET6, port)
        if ipv6 == "open":
            return "open"
        if ipv6 == "refused":
            return "refused"
        return "timeout"

    @staticmethod
    def _connect_once(host: str, family: int, port: int) -> str:
        """One TCP connect attempt: 'open', 'refused', or 'timeout'."""
        try:
            with socket.socket(family, socket.SOCK_STREAM) as sock:
                sock.settimeout(1.5)
                sock.connect((host, port))
                return "open"
        except socket.timeout:
            return "timeout"
        except OSError:
            # Connection refused / host unreachable / address family unavailable.
            return "refused"

    def _check_firewall(self, port: int) -> CheckResult | None:
        if not command_exists("ufw"):
            return None
        res = run_command(["ufw", "status"], timeout=10)
        if not res.ok:
            # Usually because it needs root. Don't escalate; just inform.
            return self.result(
                "firewall",
                "Firewall (ufw)",
                CheckStatus.SKIPPED,
                "ufw present but status unreadable (likely needs root).",
                details={"stderr": res.stderr.strip()[:200]},
                suggested_fixes=[f"Manually verify: sudo ufw status | grep {port}"],
            )
        out = res.stdout
        if "Status: inactive" in out:
            return self.result(
                "firewall",
                "Firewall (ufw)",
                CheckStatus.OK,
                "ufw is inactive (no firewall blocking).",
                details={"active": False},
            )
        port_mentioned = str(port) in out
        if port_mentioned:
            return self.result(
                "firewall",
                "Firewall (ufw)",
                CheckStatus.OK,
                f"ufw is active and references port {port}.",
                details={"active": True},
            )
        return self.result(
            "firewall",
            "Firewall (ufw)",
            CheckStatus.WARNING,
            f"ufw is active but has no rule mentioning port {port}; it may be blocked.",
            details={"active": True},
            suggested_fixes=[f"If needed, allow it: sudo ufw allow {port}/tcp"],
        )

    def _check_axon_advertisement(self, port: int) -> CheckResult | None:
        axon = self.ctx.axon
        if not axon:
            return self.result(
                "axon_advertised",
                "Advertised axon",
                CheckStatus.SKIPPED,
                "No axon info available from the metagraph (bittensor check did not run "
                "or hotkey not found).",
            )
        advertised_port = axon.get("port")
        advertised_ip = axon.get("ip")
        details = {
            "advertised_ip": advertised_ip,
            "advertised_port": advertised_port,
            "configured_port": port,
        }
        if advertised_port and int(advertised_port) != int(port):
            return self.result(
                "axon_advertised",
                "Advertised axon",
                CheckStatus.WARNING,
                f"On-chain axon advertises port {advertised_port}, but configured miner_port "
                f"is {port}. Validators connect to the advertised port.",
                details=details,
                suggested_fixes=[
                    "Make sure the advertised port matches the port your miner actually serves.",
                ],
            )
        if advertised_ip in (None, "0.0.0.0", "0"):
            return self.result(
                "axon_advertised",
                "Advertised axon",
                CheckStatus.WARNING,
                "Axon advertises no usable IP (0.0.0.0). Validators may not reach this miner.",
                details=details,
                suggested_fixes=[
                    "Ensure the miner serves its axon with a reachable external IP/port.",
                ],
            )
        return self.result(
            "axon_advertised",
            "Advertised axon",
            CheckStatus.OK,
            f"Axon advertises {advertised_ip}:{advertised_port}.",
            details=details,
        )
