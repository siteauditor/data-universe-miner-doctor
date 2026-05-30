# Data Universe Miner Doctor — Requirements (Current)

**Document version:** 1.1 (updated to match the shipped implementation)
**Supersedes:** [`REQUIREMENTS-v1.0.md`](./REQUIREMENTS-v1.0.md) — the original MVP spec, kept verbatim as the historical baseline.
**Target product:** Data Universe Miner Doctor (`du-doctor`)
**Target subnet:** Bittensor SN13 Data Universe (NETUID 13)
**Primary format:** Local, read-only CLI diagnostic tool
**Repository:** https://github.com/siteauditor/data-universe-miner-doctor
**Last reviewed:** 2026-05-30 — full audit **PASS** (see §A).

---

## 0. How this document relates to v1.0

The original spec (`REQUIREMENTS-v1.0.md`) defined the MVP. This **open-source CLI** meets every MVP
requirement. The original roadmap's optional layers (Telegram alerts, a push agent, a hosted
ingest/dashboard/billing server) have been built but are developed as a **separate project** and are
**not part of this repository** (see §B). The subnet-profile plugin system *does* ship here.

This document keeps the v1.0 requirements as the contract and annotates each area with its current
status. Where this document and v1.0 disagree, **this document wins** for the current codebase; v1.0
remains the record of original intent.

Status legend: ✅ implemented · ⏳ partial/future.

---

## A. Implementation status summary (2026-05-30)

| Area | Status | Notes |
| --- | --- | --- |
| CLI (`init`/`check`/`check --json`/`watch`/`report`/`doctor`) | ✅ | + `version`, `report --format html\|json`, `report --bundle`, `--subnet`, `--unsafe-show-full-hotkey`, exit codes 0/1/2 |
| Config loader (YAML + CLI overrides + deep-merge) | ✅ | never crashes on a bad file; falls back to defaults |
| Data models (CheckStatus/Category/Result, DoctorReport) | ✅ | Pydantic v2 |
| Status aggregation (CRITICAL > WARNING > OK; SKIPPED ignored) | ✅ | |
| System / Bittensor / Repo / Process / Network / Log checks | ✅ | |
| Data Universe config / data / scoring checks | ✅ | |
| Snapshots + drop detection | ✅ | rolling history in `~/.du-doctor/snapshots.json` |
| Terminal / JSON / Markdown reporters | ✅ | + HTML reporter and a redacted support **bundle** |
| Redaction & hotkey masking | ✅ | secrets never printed; SS58 masked `first6...last6` |
| Tests (offline, bittensor mocked) | ✅ | 79 tests passing |
| README | ✅ | |
| Telegram alerts / push agent / hosted server | — | Separate project; **not part of this CLI repo** (see §B) |

---

## 4. Tech stack (as built)

Core install (`pip install -e .`): **typer, rich, pydantic v2, PyYAML, psutil**. Python **3.10–3.12**.
Git operations use `subprocess` (no GitPython dependency). SQLite via stdlib `sqlite3` (read-only).

Optional extras (declared in `pyproject.toml`): `bittensor` (live chain/metagraph checks) and
`dev` (pytest, pytest-cov, ruff, black).

> The `bittensor` SDK is intentionally **optional** — every other check runs without it; the chain
> checks degrade to `CRITICAL` with an install hint rather than crashing.

---

## 5. Project structure (actual)

```text
data-universe-miner-doctor/
  README.md  pyproject.toml  Dockerfile  LICENSE  .gitignore  .dockerignore  PRIVACY.md

  du_doctor/                      # the CLI (the released product)
    __init__.py  cli.py  config.py  models.py
    checks/   base.py system_check.py bittensor_check.py repo_check.py
              process_check.py network_check.py log_check.py
              data_universe_config_check.py data_universe_data_check.py
              data_universe_scoring_check.py  __init__.py (registry + run_checks)
    reporters/  terminal_reporter.py json_reporter.py markdown_reporter.py
                html_reporter.py  bundle.py  __init__.py
    storage/    snapshots.py  __init__.py
    profiles/   base.py data_universe.py __init__.py   # subnet-profile plugin system
    utils/      redact.py shell.py files.py versioning.py formatting.py __init__.py

  docs/      REQUIREMENTS*.md, RUNBOOKS.md, VALIDATION.md, PRE_RELEASE_TESTING.md
  examples/  config.example.yaml, sample-report.md
  tests/     offline test suite (bittensor mocked)
```

The architecture is modular: each checker is its own file returning `CheckResult`; reporters consume
`DoctorReport`; the engine (`run_checks`, `load_config`) is profile-agnostic.

---

## 6. CLI (as built)

All v1.0 commands behave as specified. Additions:

| Command / flag | Behavior |
| --- | --- |
| `du-doctor version` | Prints the package version. |
| `du-doctor report --format html` | Writes a self-contained HTML report (`du-doctor-report.html`). |
| `du-doctor report --format json` | Writes a redacted JSON report. |
| `du-doctor report --bundle` | Writes a redacted zip: report in every format + env-var **names** only. |
| `du-doctor check --subnet <key>` | Selects a `SubnetProfile` (default `data-universe`). |
| `du-doctor check --unsafe-show-full-hotkey` | Opt-in to show the unmasked hotkey (off by default). |
| `du-doctor watch` shutdown | Graceful (`Stopped.`, exit 0) on Ctrl+C, SIGTERM, and Ctrl+Break — clean under `systemctl stop`/`kill`. |
| Exit codes | `0`=OK/SKIPPED, `1`=WARNING, `2`=CRITICAL — for cron/automation. |

`check --json` emits clean JSON (redacted) on stdout with all v1.0 top-level and per-check fields; the
non-zero exit code does not pollute the JSON.

---

## 12. Bittensor metagraph metrics (updated)

`_extract_metrics` (`du_doctor/checks/bittensor_check.py`) now collects, when the SDK exposes them:

```text
uid · rank · trust · consensus · incentive · emission · active · last_update
stake · dividends · validator_trust      # ← added in v1.1 to complete the spec list
```

Missing attributes degrade to `None` (never crash). `stake`, `dividends`, and `validator_trust` are
also persisted into the snapshot (`build_snapshot`) alongside the existing metrics. Drop detection
(`bt_drops`) still tracks only incentive/emission/rank, per §10/§13.

> Covered by `tests/test_bittensor_check.py` (fake metagraph; no SDK / chain needed).

---

## 13. Snapshot (updated)

Stored fields now include `stake`, `dividends`, `validator_trust` in addition to the v1.0 set
(timestamp, netuid, hotkey, uid, rank, trust, consensus, incentive, emission, active, data file
sizes/mtimes, pm2 restart count, registered). History is bounded (`MAX_HISTORY = 50`) and written
atomically.

---

## 26. Tests (actual)

All v1.0-required test areas exist (redaction, config, status aggregation, log check, DU config,
reporters) plus: `test_models`, `test_data_universe_data_check`, `test_network_check`,
`test_terminal_reporter`, `test_html_reporter`, `test_files_util`, `test_profiles`,
`test_bittensor_check`, and `test_cli_watch`.

Run: `pytest -q` → **79 passing**, fully offline (the bittensor SDK is mocked).

---

## B. Optional layers (separate project)

v1.0 §31 listed Telegram alerts, a hosted SaaS dashboard, and multi-subnet support as future work. A
push agent, a Telegram alert layer, and a hosted ingest/dashboard/billing server have been built — but
they live in a **separate (commercial) project**, not in this open-source CLI repository.

This repo deliberately ships only the **read-only CLI**. Its modular checks and stable, redacted JSON
output (`du-doctor check --json`) are designed to integrate with such layers cleanly. The
**subnet-profile plugin system** (`du_doctor/profiles/`) *does* ship here and lets the same engine
target other subnets via the `du_doctor.profiles` entry-point group.

---

## C. Security & privacy (unchanged, reaffirmed)

The tool is **read-only**. It never asks for seed phrases, mnemonics, private keys, or wallet
passwords; never transfers TAO, stakes, registers, or unlocks; never auto-updates the repo or restarts
the miner; never uploads logs or `.env`. Wallet lookup reads only the **public** ss58 from the hotkey
file. Secrets (API keys, tokens, `KEY=VALUE`, Bearer/Authorization, Apify tokens) are redacted in
every output; the JSON reporter re-redacts the whole serialized report (defense in depth). Hotkeys are
masked `first6...last6` unless `--unsafe-show-full-hotkey` is passed. SS58 addresses in logs are masked.

The only files written are under `~/.du-doctor/` (config + local snapshot) and any report you ask for.

---

## D. Release & verification

- CI (`.github/workflows/ci.yml`): lint (ruff + black), test matrix (Ubuntu, Python 3.10/3.11/3.12),
  a core-only smoke install validating `du-doctor check --json`, and a `python -m build`.
- Release (`.github/workflows/release.yml`): push a `vX.Y.Z` tag (must equal `pyproject` `version`)
  → builds sdist+wheel → publishes to PyPI via Trusted Publishing (OIDC).
- Pre-release manual verification: see [`PRE_RELEASE_TESTING.md`](./PRE_RELEASE_TESTING.md).
- Live-miner validation: see [`VALIDATION.md`](./VALIDATION.md). Remediation reference:
  [`RUNBOOKS.md`](./RUNBOOKS.md).
