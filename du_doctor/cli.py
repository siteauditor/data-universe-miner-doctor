"""``du-doctor`` command-line interface (Typer + Rich).

Commands:
  * ``init``   — write the default config to ``~/.du-doctor/config.yaml``
  * ``check``  — run all checks once and print a report (``--json`` for machine output)
  * ``doctor`` — alias for ``check``
  * ``watch``  — re-run on an interval and print status changes
  * ``report`` — write a shareable report (markdown/html/json) or a --bundle zip

This tool is strictly read-only. It never asks for seed phrases, mnemonics,
private keys, or wallet passwords, and never moves TAO or registers anything.
"""

from __future__ import annotations

import signal
import sys
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from du_doctor import __version__
from du_doctor.checks import run_checks
from du_doctor.checks.data_universe_config_check import read_env_keys
from du_doctor.config import init_config, load_config
from du_doctor.models import CheckStatus, DoctorReport
from du_doctor.profiles import get_profile, list_profiles
from du_doctor.reporters.bundle import DEFAULT_BUNDLE_PATH, write_bundle
from du_doctor.reporters.html_reporter import DEFAULT_HTML_PATH, write_html
from du_doctor.reporters.json_reporter import render_json
from du_doctor.reporters.markdown_reporter import DEFAULT_REPORT_PATH, write_markdown
from du_doctor.reporters.terminal_reporter import render_terminal
from du_doctor.utils.files import expand_path
from du_doctor.utils.redact import redact_secrets

app = typer.Typer(
    add_completion=False,
    help="Read-only diagnostic CLI for Bittensor Data Universe (SN13) miners.",
    no_args_is_help=True,
)

# Exit codes (useful for cron/automation).
_EXIT_FOR_STATUS = {
    CheckStatus.OK: 0,
    CheckStatus.SKIPPED: 0,
    CheckStatus.WARNING: 1,
    CheckStatus.CRITICAL: 2,
}


def _install_stop_signal_handlers() -> None:
    """Make a graceful stop (`Stopped.`) reachable via more than just Ctrl+C.

    SIGINT (Ctrl+C) already raises ``KeyboardInterrupt``. We additionally route
    SIGTERM (e.g. ``systemctl stop`` / ``kill``) and, on Windows, SIGBREAK
    (Ctrl+Break) into ``KeyboardInterrupt`` so the single ``except
    KeyboardInterrupt`` shutdown path in :func:`watch` runs everywhere. No-ops
    safely if called off the main thread or on a platform missing a signal.
    """

    def _raise_kbd(signum, frame):  # noqa: ANN001 - signal handler signature
        raise KeyboardInterrupt

    for name in ("SIGTERM", "SIGBREAK"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _raise_kbd)
        except (ValueError, OSError):  # not main thread / unsupported platform
            pass


def _make_console(no_color: bool = False) -> Console:
    """Build a Console that won't crash on non-ASCII under a legacy Windows console.

    ``legacy_windows=False`` routes output through the normal (UTF-8 capable)
    file writer instead of the strict cp1252 win32 console API.
    """
    return Console(no_color=no_color, legacy_windows=False)


def _collect_overrides(
    netuid: Optional[int] = None,
    network: Optional[str] = None,
    hotkey: Optional[str] = None,
    wallet_name: Optional[str] = None,
    wallet_hotkey: Optional[str] = None,
    repo_path: Optional[str] = None,
    scraping_config: Optional[str] = None,
    env_path: Optional[str] = None,
    pm2_process_name: Optional[str] = None,
    miner_process_name: Optional[str] = None,
    miner_port: Optional[int] = None,
) -> dict:
    """Build the CLI-override dict consumed by ``load_config``."""
    return {
        "netuid": netuid,
        "network": network,
        "hotkey": hotkey,
        "wallet_name": wallet_name,
        "wallet_hotkey": wallet_hotkey,
        "repo_path": repo_path,
        "scraping_config": scraping_config,
        "env_path": env_path,
        "pm2_process_name": pm2_process_name,
        "miner_process_name": miner_process_name,
        "miner_port": miner_port,
    }


def _resolve_profile(subnet: Optional[str], console: Console):
    """Map a ``--subnet`` key to a SubnetProfile, or exit(2) with the options."""
    try:
        return get_profile(subnet)
    except KeyError:
        avail = ", ".join(sorted(list_profiles()))
        console.print(f"[red]Unknown subnet '{subnet}'. Available: {avail}[/red]")
        raise typer.Exit(code=2) from None


def _build_report(
    config_path: Optional[Path],
    overrides: dict,
    show_full_hotkey: bool = False,
    save_snapshot: bool = True,
    profile=None,
) -> DoctorReport:
    config = load_config(config_path, cli_overrides=overrides, profile=profile)
    return run_checks(
        config,
        save_snapshot_enabled=save_snapshot,
        show_full_hotkey=show_full_hotkey,
        profile=profile,
    )


# --------------------------------------------------------------------------- #
@app.command()
def init(
    force: bool = typer.Option(False, "--force", help="Overwrite an existing config file."),
    repo_path: Optional[str] = typer.Option(
        None, "--repo-path", help="Path to your data-universe clone."
    ),
    hotkey: Optional[str] = typer.Option(None, "--hotkey", help="Your hotkey ss58 address."),
    wallet_name: Optional[str] = typer.Option(
        None, "--wallet-name", help="Coldkey/wallet name (read-only lookup)."
    ),
    wallet_hotkey: Optional[str] = typer.Option(
        None, "--wallet-hotkey", help="Hotkey name within the wallet."
    ),
) -> None:
    """Create the default config at ``~/.du-doctor/config.yaml``."""
    console = Console()
    overrides = _collect_overrides(
        hotkey=hotkey, wallet_name=wallet_name, wallet_hotkey=wallet_hotkey, repo_path=repo_path
    )
    path, created = init_config(force=force, overrides=overrides)
    if created:
        console.print(f"[green]Created config:[/green] {path}")
        console.print("Edit it to set your hotkey, repo path, scraping config, and env path.")
    else:
        console.print(f"[yellow]Config already exists:[/yellow] {path}")
        console.print("Use [bold]--force[/bold] to overwrite it with defaults.")


@app.command()
def check(
    config: Optional[Path] = typer.Option(None, "--config", help="Path to config.yaml."),
    subnet: str = typer.Option("data-universe", "--subnet", help="Subnet profile."),
    netuid: Optional[int] = typer.Option(None, "--netuid"),
    network: Optional[str] = typer.Option(None, "--network"),
    hotkey: Optional[str] = typer.Option(None, "--hotkey", help="Hotkey ss58 (overrides config)."),
    wallet_name: Optional[str] = typer.Option(None, "--wallet-name"),
    wallet_hotkey: Optional[str] = typer.Option(None, "--wallet-hotkey"),
    repo_path: Optional[str] = typer.Option(None, "--repo-path"),
    scraping_config: Optional[str] = typer.Option(None, "--scraping-config"),
    env_path: Optional[str] = typer.Option(None, "--env-path"),
    pm2_process_name: Optional[str] = typer.Option(None, "--pm2-process-name"),
    miner_process_name: Optional[str] = typer.Option(None, "--miner-process-name"),
    miner_port: Optional[int] = typer.Option(None, "--miner-port"),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    verbose: bool = typer.Option(False, "--verbose", help="Show SKIPPED/OK detail too."),
    no_color: bool = typer.Option(False, "--no-color", help="Disable coloured output."),
    unsafe_show_full_hotkey: bool = typer.Option(
        False,
        "--unsafe-show-full-hotkey",
        help="Show the full (unmasked) hotkey. Off by default for safety.",
    ),
) -> None:
    """Run all checks once and print a full health report."""
    profile = _resolve_profile(subnet, _make_console(no_color))
    overrides = _collect_overrides(
        netuid,
        network,
        hotkey,
        wallet_name,
        wallet_hotkey,
        repo_path,
        scraping_config,
        env_path,
        pm2_process_name,
        miner_process_name,
        miner_port,
    )
    report = _build_report(
        config, overrides, show_full_hotkey=unsafe_show_full_hotkey, profile=profile
    )

    if json_output:
        # Plain print so the JSON is clean and pipe-friendly.
        print(render_json(report, show_full_hotkey=unsafe_show_full_hotkey))
    else:
        console = _make_console(no_color)
        render_terminal(report, console=console, verbose=verbose)

    raise typer.Exit(code=_EXIT_FOR_STATUS.get(report.overall_status, 0))


@app.command()
def doctor(
    config: Optional[Path] = typer.Option(None, "--config"),
    subnet: str = typer.Option("data-universe", "--subnet"),
    netuid: Optional[int] = typer.Option(None, "--netuid"),
    network: Optional[str] = typer.Option(None, "--network"),
    hotkey: Optional[str] = typer.Option(None, "--hotkey"),
    wallet_name: Optional[str] = typer.Option(None, "--wallet-name"),
    wallet_hotkey: Optional[str] = typer.Option(None, "--wallet-hotkey"),
    repo_path: Optional[str] = typer.Option(None, "--repo-path"),
    scraping_config: Optional[str] = typer.Option(None, "--scraping-config"),
    env_path: Optional[str] = typer.Option(None, "--env-path"),
    pm2_process_name: Optional[str] = typer.Option(None, "--pm2-process-name"),
    miner_process_name: Optional[str] = typer.Option(None, "--miner-process-name"),
    miner_port: Optional[int] = typer.Option(None, "--miner-port"),
    json_output: bool = typer.Option(False, "--json"),
    verbose: bool = typer.Option(False, "--verbose"),
    no_color: bool = typer.Option(False, "--no-color"),
    unsafe_show_full_hotkey: bool = typer.Option(False, "--unsafe-show-full-hotkey"),
) -> None:
    """Alias for ``check``."""
    check(
        config=config,
        subnet=subnet,
        netuid=netuid,
        network=network,
        hotkey=hotkey,
        wallet_name=wallet_name,
        wallet_hotkey=wallet_hotkey,
        repo_path=repo_path,
        scraping_config=scraping_config,
        env_path=env_path,
        pm2_process_name=pm2_process_name,
        miner_process_name=miner_process_name,
        miner_port=miner_port,
        json_output=json_output,
        verbose=verbose,
        no_color=no_color,
        unsafe_show_full_hotkey=unsafe_show_full_hotkey,
    )


@app.command()
def report(
    fmt: str = typer.Option("markdown", "--format", help="markdown | html | json"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path."),
    bundle: bool = typer.Option(
        False, "--bundle", help="Write a redacted zip with the report in all formats."
    ),
    config: Optional[Path] = typer.Option(None, "--config"),
    subnet: str = typer.Option("data-universe", "--subnet"),
    hotkey: Optional[str] = typer.Option(None, "--hotkey"),
    wallet_name: Optional[str] = typer.Option(None, "--wallet-name"),
    wallet_hotkey: Optional[str] = typer.Option(None, "--wallet-hotkey"),
    repo_path: Optional[str] = typer.Option(None, "--repo-path"),
    scraping_config: Optional[str] = typer.Option(None, "--scraping-config"),
    env_path: Optional[str] = typer.Option(None, "--env-path"),
) -> None:
    """Create a shareable report (markdown/html/json) or a `--bundle` zip.

    All formats are redacted and the hotkey is masked, so output is safe to share.
    """
    console = Console()
    profile = _resolve_profile(subnet, console)
    overrides = _collect_overrides(
        hotkey=hotkey,
        wallet_name=wallet_name,
        wallet_hotkey=wallet_hotkey,
        repo_path=repo_path,
        scraping_config=scraping_config,
        env_path=env_path,
    )
    cfg = load_config(config, cli_overrides=overrides, profile=profile)
    rpt = run_checks(cfg, save_snapshot_enabled=True, show_full_hotkey=False, profile=profile)

    if bundle:
        # A redacted support pack: report in every format + env var NAMES only.
        env_names = sorted(read_env_keys(expand_path(cfg.env_path)))
        summary = "Environment variable NAMES present (values NOT included):\n" + (
            "\n".join(env_names) or "(none found)"
        )
        out_path = write_bundle(
            rpt, output or DEFAULT_BUNDLE_PATH, {"config-env-names.txt": summary}
        )
    else:
        fmt_l = fmt.lower()
        if fmt_l in {"markdown", "md"}:
            out_path = write_markdown(rpt, output or DEFAULT_REPORT_PATH)
        elif fmt_l == "html":
            out_path = write_html(rpt, output or DEFAULT_HTML_PATH)
        elif fmt_l == "json":
            out_path = Path(output or "du-doctor-report.json")
            out_path.write_text(render_json(rpt), encoding="utf-8")
        else:
            console.print(f"[red]Unsupported format '{fmt}'. Use markdown | html | json.[/red]")
            raise typer.Exit(code=2)

    console.print(f"[green]Wrote report:[/green] {out_path}")
    console.print(f"Overall status: {rpt.overall_status.value}")


@app.command()
def watch(
    interval: Optional[int] = typer.Option(
        None, "--interval", help="Seconds between runs (default: config)."
    ),
    config: Optional[Path] = typer.Option(None, "--config"),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON each cycle."),
    no_color: bool = typer.Option(False, "--no-color"),
) -> None:
    """Re-run checks on an interval and print status changes."""
    console = _make_console(no_color)
    _install_stop_signal_handlers()
    cfg = load_config(config)
    period = interval or cfg.check_interval_seconds

    console.print(f"[cyan]Watching every {period}s. Press Ctrl+C to stop.[/cyan]")
    last_status: dict[str, str] = {}
    last_overall: Optional[str] = None

    try:
        while True:
            rpt = _build_report(config, {}, save_snapshot=True)
            stamp = rpt.created_at.strftime("%H:%M:%S")

            if json_output:
                print(render_json(rpt))
            else:
                # Overall status change.
                if rpt.overall_status.value != last_overall:
                    console.print(
                        f"[bold]{stamp}[/bold] Overall: "
                        f"[bold]{rpt.overall_status.value}[/bold]"
                        + (f" (was {last_overall})" if last_overall else "")
                    )
                    last_overall = rpt.overall_status.value

                # Per-check changes.
                changed = 0
                for c in rpt.checks:
                    prev = last_status.get(c.id)
                    if prev != c.status.value:
                        if prev is not None:  # don't spam on the very first run
                            console.print(
                                f"  {stamp} {c.title}: {prev} -> "
                                f"{c.status.value} — {redact_secrets(c.summary)}"
                            )
                            changed += 1
                        last_status[c.id] = c.status.value
                if last_overall and changed == 0:
                    console.print(f"[dim]{stamp} no changes[/dim]")

            time.sleep(period)
    except KeyboardInterrupt:
        console.print("\n[cyan]Stopped.[/cyan]")


@app.command()
def version() -> None:
    """Print the du-doctor version."""
    print(__version__)


def main() -> None:
    """Console-script entry point (see pyproject ``[project.scripts]``)."""
    # Ensure non-ASCII (em dash, arrows) never crashes output on Windows consoles.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001 - older Pythons / non-reconfigurable streams
            pass
    app()


if __name__ == "__main__":
    main()
