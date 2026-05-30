# Data Universe Miner Doctor Report

- **Overall status:** [CRITICAL] CRITICAL
- **Subnet:** Data Universe (NETUID 13)
- **Network:** finney
- **Hotkey:** 5F3abc...XyZ921
- **Created:** 2026-05-30 14:21:09 UTC

## Summary

| Status | Category | Check | Summary |
| --- | --- | --- | --- |
| [OK] | SYSTEM | Operating system | Ubuntu 22.04.4 LTS detected |
| [OK] | SYSTEM | Python version | Python 3.10.12 (requires >=3.10) |
| [OK] | SYSTEM | Disk usage | 61% used on /home/ubuntu (140.2 GB free) |
| [OK] | SYSTEM | RAM usage | 48% RAM used (8.1 GB available) |
| [OK] | SYSTEM | CPU load | 33% CPU, load 1.10 over 4 cores |
| [OK] | SYSTEM | Internet connectivity | Outbound connectivity OK (3/3 reachable) |
| [OK] | SYSTEM | GPU | No GPU detected. Data Universe does not require GPU by default. |
| [OK] | BITTENSOR | Bittensor SDK | bittensor SDK installed (v6.9.3). |
| [OK] | BITTENSOR | Subtensor connection | Connected to 'finney' (block 4129877). |
| [OK] | BITTENSOR | Hotkey resolution | Resolved hotkey 5F3abc...XyZ921 (from config/cli). |
| [OK] | BITTENSOR | Subnet registration | Registered on subnet 13, UID 142 (incentive 0.0123, emission 0.0041). |
| [WARNING] | BITTENSOR | Metric drops | incentive dropped 31% (>= 25%) since the last snapshot. |
| [OK] | REPO | Repo path | Found repo directory: /home/ubuntu/data-universe |
| [OK] | REPO | Expected files | All required Data Universe files present. |
| [OK] | REPO | Git repository | Valid git repository. |
| [OK] | REPO | Git remote | origin points at macrocosm-os/data-universe. |
| [OK] | REPO | Git branch | On branch 'main'. |
| [WARNING] | REPO | Repo up-to-date | 6 commits behind origin/main. |
| [OK] | REPO | Working tree | Working tree is clean. |
| [OK] | PROCESS | PM2 installed | PM2 5.3.1. |
| [CRITICAL] | PROCESS | PM2 miner process | No Data Universe miner process found in PM2. |
| [SKIPPED] | NETWORK | Axon / miner port | miner_port not configured; skipping local port and axon checks. |
| [OK] | DATA_UNIVERSE_CONFIG | scraping_config.json | scraping_config.json is valid JSON. |
| [OK] | DATA_UNIVERSE_CONFIG | Configured scrapers | Detected scrapers: apify, reddit. |
| [OK] | DATA_UNIVERSE_CONFIG | cadence_seconds | cadence_seconds configured ([60, 300]). |
| [OK] | DATA_UNIVERSE_CONFIG | max_data_entities | max_data_entities configured. |
| [WARNING] | DATA_UNIVERSE_CONFIG | Labels | Labels look too generic: ['crypto', 'news']. |
| [CRITICAL] | DATA_UNIVERSE_CONFIG | Apify credentials | Apify scraper enabled but missing credentials: APIFY_API_TOKEN or APIFY_TOKEN. |
| [OK] | DATA_UNIVERSE_CONFIG | Reddit credentials | Reddit scraper enabled and required credentials present. |
| [OK] | DATA_UNIVERSE_DATA | Local data files | Found 1 data file(s), total 1.4 GB. |
| [WARNING] | DATA_UNIVERSE_DATA | Data freshness | Most recent data file was modified 28.0h ago (> 24h). Data may be getting stale. |
| [WARNING] | DATA_UNIVERSE_DATA | Data growth | Local data size has not changed since last check. Scraper may be idle or blocked. |
| [WARNING] | LOGS | Logs (warning patterns) | Found 12 warning log line(s) matching: rate limit, retrying. |
| [CRITICAL] | DATA_UNIVERSE_SCORING | Scraper credentials | An enabled scraper cannot run without credentials, so it likely collects no data. |
| [WARNING] | DATA_UNIVERSE_SCORING | Data freshness | Data appears stale. Freshness may affect miner value — check subnet docs. |
| [WARNING] | DATA_UNIVERSE_SCORING | Rate limiting | Scraper may be throttled (rate-limit messages in logs). |
| [WARNING] | DATA_UNIVERSE_SCORING | Label strategy | Generic labels may be less competitive. Review your label strategy. |

## Detailed checks

### PM2 / process status

**[CRITICAL] PM2 miner process** — No Data Universe miner process found in PM2.

- List PM2 processes: pm2 list
- Start the miner: pm2 start python -- ./neurons/miner.py --wallet.name <wallet-name> --wallet.hotkey <hotkey-name>

### Data Universe scraping config

**[CRITICAL] Apify credentials** — Apify scraper enabled but missing credentials: APIFY_API_TOKEN or APIFY_TOKEN.

- Add the missing variable(s) to /home/ubuntu/data-universe/.env: APIFY_API_TOKEN or APIFY_TOKEN
- An enabled scraper cannot run without its credentials.

### Logs

**[WARNING] Logs (warning patterns)** — Found 12 warning log line(s) matching: rate limit, retrying.

```
miner-error.log: WARN reddit rate limit exceeded, retrying in 60s
miner-error.log: WARN apify request retrying (attempt 3)
```

- Scraper is being throttled; reduce request cadence or rotate credentials.

## Suggested fixes (in priority order)

1. Start the miner process:
   pm2 start python -- ./neurons/miner.py --wallet.name <wallet-name> --wallet.hotkey <hotkey-name>
2. Add the missing scraper credentials to your .env (e.g. APIFY_API_TOKEN / REDDIT_*).
3. Investigate local data — ensure the scraper is producing fresh, growing data.
4. Update the Data Universe repo:
   cd /home/ubuntu/data-universe && git pull   (then restart the miner)
5. Address scraper warnings in the logs (rate limits, upload/storage errors).
6. Improve label/config quality — generic labels may be less competitive (check subnet docs).

---

_Generated by Data Universe Miner Doctor (read-only). Secrets redacted; hotkey masked._
