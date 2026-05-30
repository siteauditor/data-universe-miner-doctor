# Privacy & Data-Handling Policy

This document describes exactly what the `du-doctor` CLI reads, redacts, and
stores. It tracks the actual code behavior and is versioned with releases.

> This repository is the **read-only CLI only**. It has no telemetry and makes
> no outbound calls of its own.

## 1. What the CLI reads locally

- PM2 process list (`pm2 jlist`) and the OS process table (psutil).
- Log files at the configured `log_paths` — only the **last 500 lines** per
  file, and only **matching excerpts** are ever surfaced (redacted).
- `scraping_config.json` (parsed for scraper/label/credential config).
- `.env` — only the **variable NAMES** are read to check credential presence;
  **values are never read into output** (`read_env_keys`).
- Local SQLite data, opened **read-only/immutable**, for size/freshness and an
  optional table/row peek.
- Public chain/metagraph data via the bittensor SDK (read-only).
- The hotkey's **public ss58 only** — the wallet is **never unlocked** and no
  secret key material is read.

## 2. What the tool never does

- No trade, transfer, stake, unstake, or hotkey registration.
- No modification of your repo, config, `.env`, or data.
- No auto-update.
- **No telemetry** — the CLI makes no outbound network calls of its own (it only
  contacts the chain/scraper endpoints you point it at).
- Never asks for a seed phrase, mnemonic, private key, or wallet password.

## 3. Redaction (defence in depth)

Redaction happens at multiple layers and is idempotent
(`du_doctor/utils/redact.py`):

- Hotkeys are masked to `first6...last6` (unless you pass
  `--unsafe-show-full-hotkey`).
- `redact_secrets` removes `KEY=VALUE` secret-like pairs, `Bearer`/token
  headers, and Apify tokens, and masks SS58 addresses.
- Applied to terminal, JSON, and markdown output. The JSON reporter additionally
  re-runs the whole serialized report through `redact_structure`, so secrets
  can't slip into machine output.

## 4. What the CLI writes

The only files written are under `~/.du-doctor/` (your `config.yaml` and a local
metrics `snapshots.json`) and any report you explicitly ask for
(`du-doctor report ...`). Nothing is uploaded anywhere.

## 5. Reporting & changes

Report privacy concerns via the repository's issue tracker. This policy is
updated alongside code changes that affect data handling.
