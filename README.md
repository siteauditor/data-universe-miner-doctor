# Data Universe Miner Doctor (`du-doctor`)

A focused, **read-only** diagnostic CLI for Bittensor **Data Universe** miners
(NETUID **13**, repo [`macrocosm-os/data-universe`](https://github.com/macrocosm-os/data-universe)).

It answers exactly one question:

> **“Why is my Data Universe miner not earning well?”**

This is **not** a general Bittensor dashboard, **not** a TAO portfolio tracker,
and **not** a generic alert bot. It is a subnet-specific doctor that inspects
your miner's setup on the box where it runs and tells you, in priority order,
what to fix.

---

## 1. What is Data Universe Miner Doctor?

`du-doctor` runs locally on your miner's Ubuntu/Linux server and inspects:

1. Bittensor hotkey registration
2. Metagraph miner metrics (UID, rank, trust, consensus, incentive, emission)
3. Data Universe repo status (git remote, branch, behind-upstream, expected files)
4. PM2 miner process status (online / errored / restart loops)
5. Python / server environment (OS, Python, disk, RAM, CPU, internet, GPU)
6. Data Universe scraping configuration (`scraping_config.json`)
7. API credential **presence** (Apify / Reddit / X) — never the values
8. Local database / data freshness (SQLite size, mtime, row counts)
9. Logs and common Data Universe errors (with redacted excerpts)
10. Basic network / axon / port reachability (local only)
11. Heuristic possible reasons for low incentive or low emission

It produces a colourful terminal report, machine-readable JSON, or a shareable
markdown report.

## 2. Who it is for

- Data Universe (SN13) miners debugging low or dropping rewards.
- Operators who want a fast, repeatable health check before/after changes.
- Anyone helping a miner remotely who wants a safe, redacted report to read.

## 3. What it checks

See the list above and the [example output](#10-example-output). Every check
returns one of four statuses:

| Status | Meaning |
| --- | --- |
| `OK` | Looks healthy. |
| `WARNING` | Worth attention; may reduce value. |
| `CRITICAL` | Likely blocking earnings — fix first. |
| `SKIPPED` | Couldn't run (e.g. SDK missing, path not set). Never counts against your overall status. |

The **overall status** is the worst non-skipped status across all checks.

## 4. What it does **not** do

- It does **not** trade, transfer, stake, unstake, or register anything.
- It does **not** modify your miner, repo, config, or `.env`.
- It does **not** auto-update anything.
- It does **not** upload logs, `.env`, or telemetry anywhere.
- It does **not** need (or ask for) your wallet password.

## 5. Safety / privacy policy

**This tool is read-only.**

- It never asks for seed phrases.
- It never asks for mnemonics or private keys.
- It never asks for coldkey/wallet passwords.
- It never transfers TAO.
- It never registers hotkeys.
- It never uploads logs or `.env`.
- It only diagnoses your **local** setup and **public** chain/metagraph data.

**Redaction guarantees:**

- API keys, tokens, secrets, and `KEY=VALUE` pairs are redacted everywhere
  (terminal, JSON, markdown).
- `.env` is read only to check which variable **names** exist — values are never
  read into output.
- Hotkeys are masked to `first6...last6` (e.g. `5F3abc...XyZ921`) unless you
  explicitly pass `--unsafe-show-full-hotkey`.
- SS58 addresses found in logs are masked too.

The only files `du-doctor` writes are under `~/.du-doctor/` (your config and a
local metrics snapshot) and the markdown report you ask it to create.

## 6. Installation

Install from PyPI (Python 3.10+). Run it on the same server as your miner so it
can see PM2, processes, logs, and the DB:

```bash
python3 -m venv ~/du-doctor && source ~/du-doctor/bin/activate
pip install --upgrade pip
pip install data-universe-miner-doctor
```

The `bittensor` SDK is an **optional** extra (it is large). Include it for live
chain/metagraph checks — or install du-doctor into the venv your miner already
uses (which already has the SDK):

```bash
pip install "data-universe-miner-doctor[bittensor]"
```

> Without `bittensor`, every other check still works; the chain checks just
> report `CRITICAL` with an install hint.

Install from source instead (for development):

```bash
git clone https://github.com/siteauditor/data-universe-miner-doctor.git
cd data-universe-miner-doctor
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Docker is supported but optional — see [Docker](#docker-optional).

## 7. Quick start

```bash
du-doctor init

du-doctor check \
  --hotkey <your-hotkey-ss58> \
  --repo-path /path/to/data-universe \
  --scraping-config /path/to/data-universe/scraping_config.json \
  --env-path /path/to/data-universe/.env
```

Or put everything in the config once (`du-doctor init` then edit
`~/.du-doctor/config.yaml`) and just run `du-doctor check`.

## 8. Config examples

`du-doctor init` writes `~/.du-doctor/config.yaml`. A fully-commented example is
in [`examples/config.example.yaml`](examples/config.example.yaml). Key fields:

```yaml
netuid: 13
network: finney

# Provide a hotkey ss58 directly (simplest)...
hotkey_ss58: "5F3sa2TJ...XyZ921"
# ...or a wallet name + hotkey name (only the PUBLIC ss58 is read; never unlocked)
wallet_name: ""
wallet_hotkey_name: ""

subnet_repo_path: "/home/ubuntu/data-universe"
pm2_process_name: ""          # optional exact PM2 app name
miner_port: null              # optional axon port, e.g. 8091

scraping_config_path: "/home/ubuntu/data-universe/scraping_config.json"
env_path: "/home/ubuntu/data-universe/.env"
```

Thresholds (drop %, disk/RAM/CPU %, stale-data hours, PM2 restarts,
repo-behind commits) are all tunable in the config.

## 9. CLI examples

```bash
# Create the config
du-doctor init
du-doctor init --force --repo-path /home/ubuntu/data-universe

# Run all checks once (full terminal report)
du-doctor check
du-doctor doctor                      # alias for check

# Override config at run time
du-doctor check --hotkey 5F3sa2TJ... --repo-path ~/data-universe --miner-port 8091

# Machine-readable JSON (pipe into jq, a bot, a dashboard, ...)
du-doctor check --json | jq .overall_status

# Show OK/SKIPPED detail too, or disable colour
du-doctor check --verbose
du-doctor check --no-color

# Re-run on an interval and print only status changes
du-doctor watch --interval 300

# Write a shareable, redacted markdown report
du-doctor report --format markdown            # -> du-doctor-report.md
du-doctor report -o /tmp/miner-report.md
```

**Exit codes** (handy for cron/automation): `0` = OK, `1` = WARNING, `2` = CRITICAL.

### `du-doctor check` options

`--config`, `--netuid`, `--network`, `--hotkey`, `--wallet-name`,
`--wallet-hotkey`, `--repo-path`, `--scraping-config`, `--env-path`,
`--pm2-process-name`, `--miner-process-name`, `--miner-port`, `--json`,
`--verbose`, `--no-color`, `--unsafe-show-full-hotkey`.

## 10. Example output

```
Data Universe Miner Doctor
Overall status: CRITICAL

[OK] System: Ubuntu 22.04 detected
[OK] System: Python 3.10.12 (requires >=3.10)
[OK] Bittensor: bittensor SDK installed (v6.9.3).
[OK] Bittensor: Connected to 'finney' (block 4129877).
[OK] Bittensor: Registered on subnet 13, UID 142 (incentive 0.0123, emission 0.0041).
[WARNING] Bittensor: incentive dropped 31% (>= 25%) since the last snapshot.
[CRITICAL] Process: No Data Universe miner process found in PM2.
[WARNING] Repo: 6 commits behind origin/main.
[CRITICAL] Config: Apify scraper enabled but missing credentials: APIFY_API_TOKEN or APIFY_TOKEN.
[WARNING] Data: Local data size has not changed since last check. Scraper may be idle or blocked.
[WARNING] Logs: Found 12 warning log line(s) matching: rate limit, retrying.

Suggested fixes (priority order):
 1. Start the miner process:
    pm2 start python -- ./neurons/miner.py --wallet.name <wallet-name> --wallet.hotkey <hotkey-name>
 2. Add the missing scraper credentials to your .env (e.g. APIFY_API_TOKEN / REDDIT_*).
 3. Investigate local data — ensure the scraper is producing fresh, growing data.
 4. Update the Data Universe repo: cd <repo> && git pull
 5. Address scraper warnings in the logs (rate limits, upload/storage errors).
```

A full markdown example is in [`examples/sample-report.md`](examples/sample-report.md).

## 11. How to interpret results

- Start at **Suggested fixes (priority order)** — it lists the highest-impact
  problems first, in roughly this order:
  1. Hotkey not registered
  2. Cannot connect to Subtensor
  3. Miner process not running
  4. PM2 restart loop
  5. Missing scraping credentials
  6. Invalid `scraping_config.json`
  7. No local data / stale data
  8. Repo very outdated
  9. Axon / port problem
  10. Rate limits / scraper errors
  11. Generic labels / low config quality
- `CRITICAL` items almost always block earnings — fix those first.
- The **scoring/earning** section is *heuristic*: it suggests *possible* reasons
  (“may reduce value”, “check subnet docs”), not the exact on-chain formula.

## 12. Common Data Universe miner problems (and what du-doctor shows)

| Symptom | What you'll see |
| --- | --- |
| Miner online but not earning | Registered OK, but stale data / no growth / generic labels warnings |
| Hotkey not registered | `CRITICAL` Subnet registration |
| PM2 process stopped | `CRITICAL` PM2 miner process |
| PM2 restart loop | `WARNING/CRITICAL` restart count + Uptime/stability heuristic |
| Repo outdated | `WARNING/CRITICAL` "N commits behind origin/main" |
| `scraping_config.json` invalid | `CRITICAL` "not valid JSON" |
| Apify/Reddit credentials missing | `CRITICAL` credentials check + scoring heuristic |
| Scraper rate-limited | `WARNING` logs + "Scraper may be throttled" |
| No local data growth | `WARNING` Data growth |
| Data stale | `WARNING/CRITICAL` Data freshness |
| Disk full | `CRITICAL` Disk usage + "no space left on device" in logs |
| Incentive/emission dropped | `WARNING` Metric drops (vs. last snapshot) |

## 13. Roadmap

- [ ] More precise SN13 scoring heuristics as the subnet's rules are confirmed.
- [ ] Optional richer SQLite introspection (per-source freshness).
- [ ] Config "lint" suggestions for label strategy.
- [x] Plugin system so the same engine can doctor other subnets — `du-doctor check
      --subnet <key>` selects a `SubnetProfile` (`du_doctor/profiles/`); third
      parties register their own via the `du_doctor.profiles` entry-point group.

## 14. Commercial roadmap

The architecture (modular checks + stable JSON output) is deliberately ready for:

1. **Free open-source CLI** (this repo).
2. **Paid setup/debug service** for SN13 miners.
3. **Telegram alerts** (maintained as a separate package).
4. **Hosted monitoring SaaS** dashboard (separate, commercial).
5. **Custom "Miner Doctor"** for other subnets.

This repo is the free, open-source CLI. The optional alerting / push-agent /
hosted-server layers are developed separately and are not part of this package.
The CLI's modular checks and stable JSON output are designed to integrate with
them cleanly.

---

## Docker (optional)

Docker is **not required**; local install is the recommended path. If you want it:

```bash
docker build -t du-doctor .                       # without bittensor SDK
docker build --build-arg WITH_BITTENSOR=1 -t du-doctor .   # with it
docker run --rm -v "$PWD":/work -w /work du-doctor check --repo-path /work/data-universe
```

> Inside a container, PM2/process/log visibility depends on what you mount and
> share. Running locally on the miner box is more accurate.


## Development

```bash
pip install -e ".[dev]"
pytest -q
```

Tests mock anything that would need a live chain (the bittensor SDK is mocked),
so the suite runs fully offline.

## License

MIT.
