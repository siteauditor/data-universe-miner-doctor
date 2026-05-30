# Data Universe Miner Doctor — Runbooks

Standard remediation steps keyed by `CheckResult.id`. Turns a diagnostic into a
repeatable fix workflow (and the basis of a paid setup/debug service). Work the
report's **Suggested fixes (priority order)** top-down; each entry below maps an
`id` (visible in `du-doctor check --json`) to what it means and how to fix it.

## Bittensor / registration
- **`bt_sdk` (CRITICAL)** — bittensor not importable. `pip install bittensor` in the miner venv (or run du-doctor from it).
- **`bt_subtensor` (CRITICAL)** — can't reach the chain. Check connectivity/endpoint; confirm `network` (finney).
- **`bt_hotkey` (WARNING)** — couldn't resolve a hotkey. Pass `--hotkey <ss58>` or set `hotkey_ss58`.
- **`bt_metagraph` (CRITICAL)** — hotkey not registered on SN13. Register it (`btcli subnet register --netuid 13`). Until then the miner earns nothing.
- **`bt_drops` (WARNING)** — incentive/emission/rank fell vs last snapshot. Usually downtime, stale data, or stronger competition — work the data/process checks below.

## Process / PM2
- **`pm2_installed` (WARNING)** — PM2 missing. `npm install -g pm2` (or use another process manager).
- **`pm2_process` (CRITICAL)** — miner not running under PM2. Start it:
  `pm2 start python -- ./neurons/miner.py --wallet.name <w> --wallet.hotkey <hk>`.
- **`pm2_process` (WARNING, high restarts)** — restart loop. `pm2 logs <name>` to find the crash; fix the root cause before tuning data.
- **`process_search` (CRITICAL)** — no miner process at all. Start the miner (as above).

## Repo / code
- **`repo_path` / `repo_is_git` (CRITICAL)** — wrong path or not a clone. `git clone https://github.com/macrocosm-os/data-universe`.
- **`repo_behind` (WARNING/CRITICAL)** — outdated. `cd <repo> && git pull`, then restart the miner.
- **`repo_files` (CRITICAL)** — `neurons/miner.py` missing → re-clone / fix `--repo-path`.

## Scraping config & credentials
- **`du_config_json` (CRITICAL)** — invalid JSON. `python -m json.tool scraping_config.json` and fix.
- **`du_cred_apify` (CRITICAL)** — Apify enabled, no token. Add `APIFY_API_TOKEN` (or `APIFY_TOKEN`) to `.env`.
- **`du_cred_reddit` (CRITICAL)** — add `REDDIT_CLIENT_ID/SECRET/USERNAME/PASSWORD` to `.env`.
- **`du_cred_x` (WARNING)** — X/Twitter scraping enabled; set the token it needs (often `APIFY_API_TOKEN`).
- **`du_config_cadence` / `du_config_max_entities` (WARNING)** — set/raise `cadence_seconds` and `max_data_entities`.
- **`du_config_labels` (WARNING)** — labels empty/too generic. Review label strategy against subnet docs.

## Data
- **`du_data_files` (WARNING)** — no local DB found. Confirm `data_paths` and that the scraper writes data.
- **`du_data_freshness` (WARNING/CRITICAL)** — data stale. Check the scraper is running and not erroring.
- **`du_data_growth` (WARNING)** — DB not growing. Inspect logs for rate limits/auth failures/empty responses.

## Network / axon
- **`axon_port` (CRITICAL)** — configured port not listening. Confirm the miner serves its axon on that port.
- **`axon_advertised` (WARNING)** — on-chain axon port/IP differs from config. Align them.

## Logs & system
- **`logs_critical` (CRITICAL)** — see the matched patterns/excerpts; address the specific error.
- **`logs_warning` (WARNING)** — rate limits / upload errors; slow cadence or rotate credentials.
- **`disk` / `ram` (CRITICAL)** — free resources; a full disk causes "no space left on device".

## Earning heuristics (`score_*`)
These are *heuristics* (possible reasons), not the exact scoring formula. Use them to prioritize the
concrete checks above; verify specifics against the subnet docs.
