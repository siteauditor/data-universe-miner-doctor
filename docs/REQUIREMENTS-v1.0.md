# Data Universe Miner Doctor  
## Full Project Requirements & Implementation Checklist

**Document version:** 1.0  
**Target product:** Data Universe Miner Doctor  
**Target subnet:** Bittensor SN13 Data Universe  
**Primary format:** Local CLI diagnostic tool  
**Main purpose:** Help a Bittensor Data Universe miner/operator understand why their miner is not earning well.

---

## 1. Project Summary

**Project name:** Data Universe Miner Doctor  
**CLI command:** `du-doctor`  
**Target subnet:** Bittensor SN13 Data Universe  
**NETUID:** `13`  
**Target repo:** `https://github.com/macrocosm-os/data-universe`  
**Main user:** Data Universe miner/operator  
**Main problem:** “My miner is online, but why am I not earning well?”

The tool must run locally on a miner’s Ubuntu/Linux server and diagnose the miner setup, process health, repo status, Bittensor registration, scraping configuration, local data freshness, logs, and possible earning issues.

This is **not** a generic Bittensor dashboard.  
This is a **subnet-specific diagnostic CLI tool**.

---

## 2. Main Product Goal

The tool should answer these questions:

```text
1. Is my hotkey registered on SN13?
2. Is my miner process running?
3. Is PM2 running correctly?
4. Is the Data Universe repo installed correctly?
5. Is the repo outdated?
6. Is my Python/server environment correct?
7. Is scraping_config.json valid?
8. Are required scraper credentials present?
9. Is local data being collected?
10. Is local data fresh or stale?
11. Are logs showing scraper/API/Bittensor errors?
12. Did my incentive/emission/rank drop?
13. What should I fix first?
```

---

## 3. MVP Scope

### Must Have

The current implementation should include:

```text
CLI app
Config loader
System checks
Bittensor checks
Repo checks
PM2/process checks
Log checks
Data Universe config checks
Data freshness checks
Snapshot comparison
Terminal report
JSON report
Markdown report
Tests
README
```

### Should Not Have Yet

These are future features, not required in MVP:

```text
Hosted SaaS dashboard
Stripe billing
User accounts
Telegram bot
Discord alerts
Automatic code updates
Automatic TAO registration
Wallet unlock
Cloud log upload
Multi-subnet support
```

---

## 4. Required Tech Stack

The implementation should use:

```text
Python 3.10+
Typer
Rich
Pydantic
PyYAML
psutil
pytest
bittensor SDK
GitPython or subprocess git commands
sqlite3/pathlib where needed
```

Expected `pyproject.toml` dependencies:

```text
typer
rich
pydantic
pyyaml
psutil
pytest
bittensor
gitpython or equivalent git subprocess usage
```

---

## 5. Required Project Structure

The project should roughly follow this structure:

```text
data-universe-miner-doctor/
  README.md
  pyproject.toml
  Dockerfile
  .gitignore

  du_doctor/
    __init__.py
    cli.py
    config.py
    models.py

    checks/
      __init__.py
      base.py
      system_check.py
      bittensor_check.py
      repo_check.py
      process_check.py
      network_check.py
      log_check.py
      data_universe_config_check.py
      data_universe_data_check.py
      data_universe_scoring_check.py

    reporters/
      __init__.py
      terminal_reporter.py
      json_reporter.py
      markdown_reporter.py

    storage/
      __init__.py
      snapshots.py

    utils/
      __init__.py
      redact.py
      shell.py
      files.py
      versioning.py
      formatting.py

  tests/
    test_config.py
    test_redact.py
    test_models.py
    test_status_aggregation.py
    test_log_check.py
    test_markdown_reporter.py
    test_json_reporter.py
    test_data_universe_config_check.py

  examples/
    config.example.yaml
    sample-report.md
```

Small differences are okay, but the architecture should be modular.

Bad sign:

```text
Everything is inside one huge main.py file.
```

Good sign:

```text
Each checker is separated and returns a structured result.
```

---

## 6. CLI Requirements

### 6.1 `du-doctor init`

Required behavior:

```text
Creates ~/.du-doctor/config.yaml
Does not overwrite existing config unless --force is passed
Accepts optional values like repo path, hotkey, wallet name
Prints next-step instructions
```

Required command examples:

```bash
du-doctor init
du-doctor init --force
du-doctor init --repo-path /home/ubuntu/data-universe
du-doctor init --hotkey 5xxxx
```

Pass criteria:

```text
Config file is created successfully.
Default NETUID is 13.
Default network is finney.
Default subnet name is Data Universe.
No secrets are requested.
```

---

### 6.2 `du-doctor check`

Required behavior:

```text
Runs all diagnostic checks once
Prints Rich terminal report
Aggregates overall status
Saves snapshot
Does not crash if one checker fails
```

Required command examples:

```bash
du-doctor check
du-doctor check --hotkey 5xxxx
du-doctor check --repo-path /home/ubuntu/data-universe
du-doctor check --scraping-config /home/ubuntu/data-universe/scraping_config.json
du-doctor check --env-path /home/ubuntu/data-universe/.env
```

Pass criteria:

```text
Runs without crashing.
Prints checks grouped by category.
Shows OK/WARNING/CRITICAL/SKIPPED.
Shows suggested fixes.
Masks sensitive values.
```

---

### 6.3 `du-doctor check --json`

Required behavior:

```text
Returns valid JSON only
No Rich UI
No extra text before/after JSON
Machine-readable output
```

Required JSON fields:

```json
{
  "overall_status": "WARNING",
  "subnet_name": "Data Universe",
  "netuid": 13,
  "network": "finney",
  "hotkey_masked": "5F3abc...XyZ921",
  "created_at": "...",
  "checks": [],
  "suggested_fix_order": []
}
```

Pass criteria:

```text
Output can be parsed by jq.
Every check has id, title, category, status, summary, details, evidence, suggested_fixes, timestamp.
```

Test:

```bash
du-doctor check --json | jq .
```

---

### 6.4 `du-doctor watch`

Required behavior:

```text
Runs checks repeatedly
Uses default interval from config
Can override interval from CLI
Shows changed statuses
Does not spam full report every time unless designed intentionally
```

Command:

```bash
du-doctor watch --interval 300
```

Pass criteria:

```text
Runs continuously.
Can be stopped with Ctrl+C.
Handles errors gracefully.
```

---

### 6.5 `du-doctor report --format markdown`

Required behavior:

```text
Creates du-doctor-report.md
Includes full diagnostic summary
Masks secrets
Useful for sending to support/client
```

Pass criteria:

```text
Markdown file is created.
No API keys or .env values appear.
Hotkey is masked.
Suggested fixes are included.
```

---

### 6.6 `du-doctor doctor`

Required behavior:

```text
Alias for du-doctor check
```

Pass criteria:

```text
du-doctor doctor works exactly like du-doctor check.
```

---

## 7. Config Requirements

Default config path:

```text
~/.du-doctor/config.yaml
```

Required default config:

```yaml
netuid: 13
network: finney
subnet_name: "Data Universe"
subnet_repo_url: "https://github.com/macrocosm-os/data-universe"

hotkey_ss58: ""
wallet_name: ""
wallet_hotkey_name: ""

subnet_repo_path: ""
miner_process_name: "miner.py"
pm2_process_name: ""
miner_port: null

log_paths:
  - "./logs"
  - "./pm2.log"
  - "~/.pm2/logs"

data_paths:
  - "./data"
  - "./database"
  - "./storage"
  - "./local_storage"

scraping_config_path: "./scraping_config.json"
env_path: "./.env"

check_interval_seconds: 300

thresholds:
  incentive_drop_percent: 25
  emission_drop_percent: 25
  rank_drop_percent: 25
  disk_usage_warning_percent: 85
  ram_usage_warning_percent: 85
  cpu_usage_warning_percent: 90
  stale_data_warning_hours: 24
  stale_data_critical_hours: 72
  pm2_restart_warning_count: 5
  repo_behind_warning_commits: 3
  repo_behind_critical_commits: 15

data_universe:
  requires_gpu: false
  required_python_version: ">=3.10"
```

Pass criteria:

```text
YAML loads correctly.
Missing optional values do not crash the tool.
CLI values override config values.
Invalid config gives useful error message.
```

---

## 8. Security & Privacy Requirements

This is extremely important.

The tool must be **read-only**.

### Must Never Ask For

```text
seed phrase
mnemonic
private key
coldkey password
wallet password
```

### Must Never Do

```text
TAO transfer
hotkey registration
staking
unstaking
wallet unlock
automatic repo update
automatic miner restart without confirmation
external telemetry
cloud log upload
```

### Must Redact

```text
API keys
.env values
tokens
passwords
private keys
full hotkey
authorization headers
cookies
```

Hotkey masking rule:

```text
Show first 6 and last 6 characters only.
```

Example:

```text
5F3abc...XyZ921
```

Pass criteria:

```text
No command asks for secrets.
Reports do not expose tokens.
Markdown reports do not expose .env values.
JSON reports do not expose secrets.
```

---

## 9. Data Models Requirements

### 9.1 CheckStatus

Required statuses:

```text
OK
WARNING
CRITICAL
SKIPPED
```

### 9.2 CheckCategory

Required categories:

```text
SYSTEM
BITTENSOR
REPO
PROCESS
NETWORK
LOGS
DATA_UNIVERSE_CONFIG
DATA_UNIVERSE_DATA
DATA_UNIVERSE_SCORING
```

### 9.3 CheckResult

Required fields:

```text
id: str
title: str
category: CheckCategory
status: CheckStatus
summary: str
details: dict
evidence: list[str]
suggested_fixes: list[str]
timestamp: datetime
```

### 9.4 DoctorReport

Required fields:

```text
overall_status: CheckStatus
subnet_name: str
netuid: int
network: str
hotkey_masked: str | None
checks: list[CheckResult]
suggested_fix_order: list[str]
created_at: datetime
```

Pass criteria:

```text
All checkers return CheckResult.
Reporters consume DoctorReport.
No checker returns random dicts only.
```

---

## 10. Overall Status Aggregation

Rules:

```text
If any check is CRITICAL -> overall_status = CRITICAL
Else if any check is WARNING -> overall_status = WARNING
Else if all checks are OK/SKIPPED -> overall_status = OK
SKIPPED alone should not cause WARNING
```

Pass criteria:

```text
Critical always wins.
Warning wins over OK.
Skipped does not make report bad.
```

---

## 11. System Check Requirements

File:

```text
du_doctor/checks/system_check.py
```

Required checks:

### OS Check

```text
OK if Linux
WARNING if macOS
CRITICAL if Windows
Show distro if available
```

### Python Version

```text
OK if Python >= 3.10
WARNING if below 3.10
```

### Disk Usage

```text
OK below threshold
WARNING above configured threshold
CRITICAL above 95%
```

### RAM Usage

```text
OK below threshold
WARNING above configured threshold
CRITICAL above 95%
```

### CPU Usage

```text
WARNING if sustained CPU usage is too high
```

### GPU Check

Data Universe does **not** require GPU by default.

Required behavior:

```text
If nvidia-smi exists, show GPU info.
If no GPU, do not mark critical.
Return OK or SKIPPED with:
“No GPU detected. Data Universe does not require GPU by default.”
```

Pass criteria:

```text
No GPU should not fail SN13 health check.
```

---

## 12. Bittensor Check Requirements

File:

```text
du_doctor/checks/bittensor_check.py
```

Required checks:

### SDK Import

```text
Try import bittensor as bt.
Show version if possible.
If missing, CRITICAL.
```

### Subtensor Connection

```text
Connect to finney by default.
Get current block if possible.
If connection fails, CRITICAL.
```

### Hotkey Resolution

Accept:

```text
hotkey_ss58 directly
wallet_name + wallet_hotkey_name if safe
```

Important:

```text
Do not unlock wallet.
Do not ask for password.
If wallet lookup is unsafe/complex, ask user to pass hotkey_ss58 directly.
```

### Metagraph Check

Required behavior:

```text
Load metagraph for netuid 13.
Find hotkey in metagraph.hotkeys.
If missing, CRITICAL.
If found, return UID and metrics if available.
```

Metrics to collect if available:

```text
uid
rank
trust
consensus
incentive
emission
active
axon info
last update
stake
dividends
validator trust
```

Pass criteria:

```text
Missing SDK field does not crash tool.
Unknown metric becomes SKIPPED or omitted with explanation.
```

---

## 13. Snapshot Requirements

File:

```text
du_doctor/storage/snapshots.py
```

Snapshot path:

```text
~/.du-doctor/snapshots.json
```

Required stored data:

```text
timestamp
netuid
hotkey
uid
rank
trust
consensus
incentive
emission
active
local data file sizes
local data modified times
pm2 restart count
```

Required comparison logic:

```text
Warn if incentive drops more than threshold.
Warn if emission drops more than threshold.
Warn if rank drops more than threshold.
Critical if hotkey was previously registered but now missing.
Skipped if no previous snapshot exists.
```

Pass criteria:

```text
First run creates snapshot.
Second run compares with previous snapshot.
No previous snapshot does not cause error.
```

---

## 14. Repo Check Requirements

File:

```text
du_doctor/checks/repo_check.py
```

Required checks:

### Repo Path

```text
CRITICAL if repo path missing.
CRITICAL if path is not a git repo.
```

### Remote Origin

```text
OK if origin contains macrocosm-os/data-universe.
WARNING if remote is different.
```

### Branch

```text
Show current branch.
WARNING if detached HEAD.
```

### Behind Upstream

```text
Run git fetch origin safely.
Detect origin/main or origin/master.
WARNING if behind by threshold.
CRITICAL if far behind.
```

### Dirty Tree

```text
WARNING if uncommitted changes exist.
Message must say local changes may be intentional.
```

### Expected Files

Required files:

```text
neurons/miner.py
requirements.txt
README.md
```

Optional files:

```text
scraping_config.json
.env
```

Pass criteria:

```text
Missing neurons/miner.py = CRITICAL.
Missing requirements.txt = WARNING or CRITICAL.
Missing .env = WARNING unless credentials are required.
```

---

## 15. PM2 / Process Check Requirements

File:

```text
du_doctor/checks/process_check.py
```

Required checks:

### PM2 Installed

```text
Run pm2 --version.
If missing, WARNING.
```

### PM2 Process List

Use:

```bash
pm2 jlist
```

Find process by:

```text
configured pm2_process_name
command containing neurons/miner.py
command containing miner.py
```

Required behavior:

```text
OK if process online.
CRITICAL if process missing.
WARNING if stopped/errored.
WARNING if restart count above threshold.
```

### psutil Fallback

If PM2 not found:

```text
Search local processes for miner.py or neurons/miner.py.
If process found, OK with warning:
“Miner process found, but PM2 not detected.”
```

Suggested fixes should include:

```bash
pm2 list
pm2 logs
pm2 restart <name>
pm2 start python -- ./neurons/miner.py --wallet.name <wallet-name> --wallet.hotkey <hotkey-name>
```

Pass criteria:

```text
Stopped miner is CRITICAL.
High restart count is WARNING or CRITICAL.
PM2 missing does not crash tool.
```

---

## 16. Network / Axon Check Requirements

File:

```text
du_doctor/checks/network_check.py
```

Required checks:

### Internet Connectivity

```text
Check basic outbound connectivity.
Do not depend on only one fragile endpoint.
```

### Local Port

If `miner_port` is configured:

```text
Check whether local port is listening.
CRITICAL if configured port is not listening.
```

### UFW Firewall

If `ufw` exists:

```text
Run ufw status.
Warn if configured miner port may be blocked.
```

### Metagraph Axon Comparison

If axon info is available:

```text
Show advertised IP/port.
Warn if advertised port differs from configured miner_port.
```

Pass criteria:

```text
No aggressive scanning.
Only local safe checks.
```

---

## 17. Log Check Requirements

File:

```text
du_doctor/checks/log_check.py
```

Required behavior:

```text
Expand ~ paths.
Support file paths and directory paths.
If directory, scan recent .log files.
Read only last 500 lines per file.
Never print full logs.
Redact secrets.
Show matching excerpts only.
```

Critical patterns:

```text
traceback
hotkey not registered
not registered
cannot connect to subtensor
failed to serve axon
address already in use
permission denied
no module named
database is locked
sqlite database is locked
invalid signature
authentication failed
invalid apify token
reddit authentication failed
no space left on device
out of disk
```

Warning patterns:

```text
timeout
retrying
rate limit
too many requests
deprecated
no data scraped
empty response
validator rejected
stale
upload failed
miner index
storage upload
s3 upload
```

Each match should return:

```text
file path
severity
matched pattern
redacted excerpt
suggested fix
```

Pass criteria:

```text
Secrets are redacted.
Only relevant log lines are shown.
Large logs do not crash tool.
Missing logs return SKIPPED or WARNING.
```

---

## 18. Data Universe Config Check Requirements

File:

```text
du_doctor/checks/data_universe_config_check.py
```

This is one of the most important modules.

### Locate Config

Search priority:

```text
CLI --scraping-config
config scraping_config_path
repo root / scraping_config.json
common paths under repo
```

### Validate JSON

```text
CRITICAL if invalid JSON.
WARNING if missing.
```

### Detect Scrapers

Look for keys/values containing:

```text
apify
reddit
x
twitter
youtube
transcript
huggingface
label
labels
cadence_seconds
max_data_entities
```

### Check Cadence

```text
WARNING if cadence_seconds missing.
WARNING if cadence_seconds is non-numeric.
WARNING if cadence seems extremely slow.
```

### Check Max Data Entities

```text
WARNING if max_data_entities missing.
WARNING if too low.
```

### Check Labels

```text
WARNING if labels empty.
WARNING if labels are too generic.
WARNING if label list is too small.
```

Important:

```text
Do not promise exact earning improvement.
Use careful wording.
```

### Check Credentials

Read `.env` safely.

Never print values.

If Apify appears enabled, require one of:

```text
APIFY_API_TOKEN
APIFY_TOKEN
```

If Reddit custom scraper appears enabled, check:

```text
REDDIT_CLIENT_ID
REDDIT_CLIENT_SECRET
REDDIT_USERNAME
REDDIT_PASSWORD
```

If X/Twitter scraper appears enabled:

```text
Check likely token names.
WARNING if missing unless exact requirement is known.
```

Pass criteria:

```text
Apify enabled but token missing = CRITICAL.
Reddit enabled but credentials missing = CRITICAL.
Invalid JSON = CRITICAL.
Empty/generic labels = WARNING.
```

---

## 19. Data Universe Data Health Requirements

File:

```text
du_doctor/checks/data_universe_data_check.py
```

Required behavior:

### Find Data Paths

Check:

```text
data/
database/
storage/
local_storage/
configured data_paths
```

### Find DB Files

Search:

```text
*.db
*.sqlite
*.sqlite3
```

### DB File Status

For each DB/data file:

```text
show size
show last modified time
warning if stale over threshold
critical if stale over critical threshold
```

### Data Growth

Use snapshots to compare:

```text
file size changed?
modified time changed?
new files created?
```

If no growth:

```text
WARNING:
“Local data size has not changed since last check. Scraper may be idle or blocked.”
```

### SQLite Read-Only Inspection

If possible:

```text
Open SQLite DB read-only.
List table names.
Count rows in likely data tables.
Detect latest timestamp column if obvious.
```

Possible timestamp columns:

```text
created_at
datetime
timestamp
scraped_at
updated_at
```

Pass criteria:

```text
Unknown schema does not crash.
No data files = WARNING.
Stale DB = WARNING/CRITICAL.
Read-only only.
```

---

## 20. Data Universe Scoring Heuristic Requirements

File:

```text
du_doctor/checks/data_universe_scoring_check.py
```

This should not pretend to know exact scoring.

Use wording like:

```text
possible reason
heuristic warning
may reduce value
check Data Universe docs
```

Required heuristics:

### Stale Data

```text
If data files are old, warn:
“Data appears stale. Freshness may affect miner value.”
```

### Low Scrape Activity

```text
If logs show no data scraped or DB not growing, warn.
```

### Credential Failure

```text
If scraper enabled but credentials missing, critical.
```

### Rate Limiting

```text
If logs show rate limit, warning.
```

### Generic Labels

```text
If labels are too generic, warning.
```

### PM2 Restart Loop

```text
If restart count is high, critical or warning.
```

Pass criteria:

```text
No fake earning claims.
No exact reward prediction unless real verified data exists.
```

---

## 21. Terminal Reporter Requirements

File:

```text
du_doctor/reporters/terminal_reporter.py
```

Use Rich.

Required sections:

```text
Header
Overall status
Summary table
Detailed check groups
Suggested fix order
```

Header should show:

```text
Data Universe Miner Doctor
Subnet: Data Universe / NETUID 13
Network: finney
Hotkey: masked
Created: timestamp
```

Summary table columns:

```text
Status
Category
Check
Summary
```

Pass criteria:

```text
Readable terminal output.
Colorized statuses.
No secrets.
Suggested fixes visible.
```

---

## 22. JSON Reporter Requirements

File:

```text
du_doctor/reporters/json_reporter.py
```

Required behavior:

```text
Valid JSON
No Rich formatting
No logs mixed into stdout
Suitable for future SaaS/Telegram bot
```

Pass criteria:

```bash
du-doctor check --json | jq .
```

must work.

---

## 23. Markdown Reporter Requirements

File:

```text
du_doctor/reporters/markdown_reporter.py
```

Required output:

```text
# Data Universe Miner Doctor Report

Overall status
Subnet
NETUID
Network
Hotkey masked
Timestamp
Summary table
Detailed checks
Suggested fixes
Privacy note
```

Pass criteria:

```text
Markdown file generated.
Secrets redacted.
Useful for sharing with support.
```

---

## 24. Suggested Fix Ordering Requirements

Suggested fixes should be prioritized:

```text
1. Hotkey not registered
2. Cannot connect to Subtensor
3. Miner process not running
4. PM2 restart loop
5. Missing scraping credentials
6. Invalid scraping_config.json
7. No local data / stale data
8. Repo very outdated
9. Axon/port problem
10. Rate limits / scraper errors
11. Generic labels / low config quality
```

Pass criteria:

```text
Critical fixes appear before minor warnings.
Suggested fixes are practical commands or clear next steps.
```

---

## 25. Error Handling Requirements

The tool must never crash because one check fails.

Bad behavior:

```text
Bittensor SDK missing -> whole app crashes
PM2 missing -> whole app crashes
scraping_config missing -> whole app crashes
Git repo missing -> whole app crashes
```

Correct behavior:

```text
Each failure becomes a CheckResult.
Status should be WARNING, CRITICAL, or SKIPPED.
User gets suggested fix.
```

Example:

```text
[CRITICAL] Bittensor SDK is not installed.
Fix: Install bittensor SDK in your miner environment.
```

---

## 26. Test Requirements

Required tests:

### Redaction Tests

```text
API keys redacted
.env values redacted
hotkey masked
tokens redacted
```

### Config Tests

```text
default config loads
YAML config loads
CLI overrides config
invalid YAML handled
```

### Status Aggregation Tests

```text
critical wins
warning wins over OK
skipped does not affect overall status
```

### Log Check Tests

```text
critical pattern detected
warning pattern detected
secret values redacted
large logs handled
```

### Data Universe Config Tests

```text
invalid JSON = critical
missing Apify token = critical
missing Reddit credentials = critical
generic labels = warning
valid config = OK
```

### Reporter Tests

```text
JSON valid
Markdown generated
Terminal reporter does not crash
```

Important:

```text
Tests should not require live Bittensor network.
Bittensor SDK should be mocked.
```

Run:

```bash
pytest
```

Pass criteria:

```text
All tests pass.
No live network needed for unit tests.
```

---

## 27. README Requirements

README must include:

```text
What is Data Universe Miner Doctor?
Who it is for
What it checks
What it does not do
Safety/privacy policy
Installation
Quick start
Config examples
CLI examples
Example output
How to interpret results
Common Data Universe miner problems
Roadmap
Commercial roadmap
```

Required quick start:

```bash
git clone <repo>
cd data-universe-miner-doctor
python -m venv .venv
source .venv/bin/activate
pip install -e .

du-doctor init

du-doctor check \
  --hotkey <your-hotkey-ss58> \
  --repo-path /path/to/data-universe \
  --scraping-config /path/to/data-universe/scraping_config.json \
  --env-path /path/to/data-universe/.env
```

README must clearly say:

```text
This tool is read-only.
It never asks for seed phrases.
It never asks for private keys.
It never transfers TAO.
It never registers hotkeys.
It never uploads logs.
```

---

## 28. Current Implementation Audit Checklist

Use this to review your current code.

### Basic

```text
[ ] Project installs with pip install -e .
[ ] du-doctor command works
[ ] du-doctor init works
[ ] du-doctor check works
[ ] du-doctor check --json works
[ ] du-doctor report --format markdown works
[ ] du-doctor watch works
[ ] pytest passes
```

### Architecture

```text
[ ] Code is modular
[ ] Each checker is in separate file
[ ] Each checker returns CheckResult
[ ] Reporters consume DoctorReport
[ ] Config is loaded from YAML
[ ] CLI overrides config
[ ] Snapshot storage exists
```

### Security

```text
[ ] No seed phrase requested
[ ] No private key requested
[ ] No wallet unlock
[ ] No TAO transaction
[ ] No hotkey registration
[ ] .env values redacted
[ ] API tokens redacted
[ ] Hotkey masked
[ ] Logs are not uploaded
```

### Data Universe Specific

```text
[ ] NETUID defaults to 13
[ ] Subnet name defaults to Data Universe
[ ] Repo URL defaults to macrocosm-os/data-universe
[ ] PM2 process is checked
[ ] neurons/miner.py is checked
[ ] scraping_config.json is checked
[ ] .env credentials are checked safely
[ ] Apify token check exists
[ ] Reddit credential check exists
[ ] Data paths are checked
[ ] DB freshness is checked
[ ] Log patterns include scraper/rate-limit errors
```

### Bittensor

```text
[ ] bittensor SDK import handled
[ ] Subtensor connection handled
[ ] Metagraph loaded for netuid 13
[ ] Hotkey registration checked
[ ] UID returned if registered
[ ] Incentive/emission/rank collected if available
[ ] Missing SDK fields do not crash
```

### Reports

```text
[ ] Terminal report readable
[ ] JSON report valid
[ ] Markdown report generated
[ ] Suggested fixes are included
[ ] Critical issues shown first
```

---

## 29. Pass / Fail Definition

### MVP Passes If

```text
A Data Universe miner can run one command and get a useful diagnostic report.
```

Minimum passing command:

```bash
du-doctor check \
  --hotkey 5xxxx \
  --repo-path /home/ubuntu/data-universe \
  --scraping-config /home/ubuntu/data-universe/scraping_config.json \
  --env-path /home/ubuntu/data-universe/.env
```

The output should clearly show:

```text
registered or not registered
miner process running or stopped
repo healthy or outdated
scraping config valid or broken
credentials present or missing
data fresh or stale
important log errors
suggested fixes
```

### MVP Fails If

```text
Tool crashes easily.
Tool asks for wallet secrets.
Tool only shows generic system info.
Tool does not check Data Universe config.
Tool does not check PM2/miner process.
Tool does not check local data freshness.
Tool does not provide suggested fixes.
Tool exposes secrets in output.
```

---

## 30. Best Final Standard

The current implementation is good if it can answer this clearly:

```text
Your miner is registered on SN13, but it is likely earning poorly because:

1. PM2 restarted 12 times in the last day.
2. Apify scraper is enabled but APIFY_API_TOKEN is missing.
3. Local DB has not changed in 32 hours.
4. Logs show rate-limit errors.
5. Repo is 8 commits behind origin/main.

Suggested fix order:
1. Add missing Apify token.
2. Restart PM2 miner process.
3. Pull latest repo.
4. Check scraper labels/cadence.
5. Run du-doctor check again in 1 hour.
```

That is the real product value.

---

## 31. Optional Future Roadmap

These are not part of the MVP, but the implementation should leave room for them.

### Phase 2: Telegram Alerts

```text
Telegram bot integration
Alert when miner stops
Alert when incentive/emission drops
Alert when local DB stops growing
Alert when PM2 restart count increases
Alert when scraper credentials fail
```

### Phase 3: Hosted SaaS Dashboard

```text
User accounts
Multiple hotkeys
Multiple servers
JSON agent upload
Dashboard charts
Historical incident reports
Team access
Stripe billing
```

### Phase 4: Multi-Subnet Miner Doctor

```text
General plugin architecture
Subnet-specific rule packs
Rule pack for SN13 Data Universe
Rule pack for Chutes
Rule pack for other active subnets
```

### Phase 5: Paid Services

```text
Setup/debug service for SN13 miners
Custom diagnostic tools for subnet teams
White-label Miner Doctor for managed mining operators
```

---

## 32. Review Notes for Current Implementation

When checking current implementation, do not only look at whether code “runs.” Check whether it solves the real business problem.

The key review question is:

```text
Can this tool quickly explain why a Data Universe miner is not earning well?
```

If the answer is yes, the implementation is going in the right direction.

If the answer is no, the implementation needs more subnet-specific checks, especially:

```text
scraping_config.json quality
credentials
PM2 stability
local data freshness
log diagnosis
Bittensor registration/metagraph metrics
```
