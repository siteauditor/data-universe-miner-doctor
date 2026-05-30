# Real-Miner Validation Checklist (live SN13)

The automated suite runs fully offline (the bittensor SDK is mocked). This
checklist covers what **can only be verified against a live SN13 miner** with the
real `bittensor` SDK, PM2, a real `SqliteMinerStorage`, and a real
`scraping_config.json`. Run it on the miner's Ubuntu box.

> Everything here is read-only. Confirm in §6 that the run made **zero writes**
> to the miner and **zero chain submissions**.

## 0. Preconditions
- [ ] Ubuntu/Linux box actively running an SN13 (`Data Universe`) miner.
- [ ] `pip install -e ".[bittensor]"` in (or alongside) the miner's venv.
- [ ] Config or flags set for `--hotkey`, `--repo-path`, `--scraping-config`, `--env-path`.

## 1. Bittensor / metagraph extraction (`du_doctor/checks/bittensor_check.py`)
- [ ] `du-doctor check --hotkey <ss58>`: `bt_sdk` OK with the real SDK version.
- [ ] `bt_subtensor` connects to `finney` and shows a current block.
- [ ] `bt_hotkey` resolves and is masked `first6...last6`.
- [ ] `bt_metagraph` shows the correct UID and populated `rank/trust/consensus/
      incentive/emission/active`; cross-check against `btcli`/Taostats for that UID
      (validates `_extract_metrics`/`_extract_axon` vs the installed SDK's tensor types).
- [ ] Run twice (so a snapshot exists): `bt_drops` computes incentive/emission/rank deltas.

## 2. PM2 jlist parsing (`process_check.py`)
- [ ] Miner under PM2: `pm2_installed` OK; `pm2_process` matches by name/exec-path/args.
- [ ] Correct `status` (online), `restart_time`, `pm_id`, `pid`.
- [ ] Set a high restart count or stop the process → WARNING/CRITICAL as expected.
- [ ] Stop the PM2 daemon → psutil backstop path still finds the miner.
- [ ] `--pm2-process-name <name>` override matches a non-standard app name.

## 3. Real SqliteMinerStorage (`data_universe_data_check.py`)
- [ ] Point `data_paths` at the real DB: `du_data_files` finds it; size/mtime shown.
- [ ] `du_data_freshness` + `du_data_growth` behave across two runs spaced beyond the cadence window.
- [ ] `du_data_tables` opens the DB read-only/immutable, lists real tables (DataEntity store),
      counts rows (exercise the `COUNT(*)`/`MAX(_rowid_)` fallback on a large table),
      and detects a real timestamp column.

## 4. scraping_config.json shapes (`data_universe_config_check.py`)
- [ ] Real config: scrapers detected from real `scraper_id` values (e.g. `reddit.custom`, `x.apidojo`).
- [ ] `cadence_seconds` / `max_data_entities` / labels harvested correctly.
- [ ] Credential checks read real `.env` **names only**; Apify "any-of" vs others "all-of" semantics correct.
- [ ] X/Twitter uncertain-credential path is a WARNING (not a false CRITICAL).

## 5. Reporters
- [ ] `du-doctor report --format markdown` (and `--format html`) — secrets redacted, hotkey masked.

## 6. Safety reconfirmation
- [ ] Confirm zero writes to the miner repo / config / `.env` (e.g. `git status` clean, mtimes unchanged).
- [ ] Confirm no chain submissions occurred.
- [ ] The only files written are under `~/.du-doctor/` and any report you explicitly requested.

## 7. Sign-off

| Date | Box | Miner UID | bittensor version | Sections passed | Notes |
|------|-----|-----------|-------------------|-----------------|-------|
|      |     |           |                   |                 |       |
