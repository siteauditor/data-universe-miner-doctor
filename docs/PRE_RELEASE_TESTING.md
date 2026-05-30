# Pre-Release Testing Guide (`du-doctor` CLI)

A practical checklist to run **before tagging a release** of the `du-doctor` CLI to PyPI. It verifies
the package builds, installs cleanly from the built artifact, every command works, secrets stay
redacted, and the release pipeline is primed.

**Scope.** This guide covers *packaging + CLI behavior + safety* on a clean machine. It deliberately
does **not** duplicate:
- [`VALIDATION.md`](./VALIDATION.md) — live-miner validation against a real SN13 box (bittensor SDK,
  PM2, real SqliteMinerStorage). Run that **once** on a real miner before a first public release.
- [`RUNBOOKS.md`](./RUNBOOKS.md) — operator remediation steps per check id.

Commands are shown for **bash** (Linux/macOS, the deployment target). PowerShell equivalents are noted
where they differ. Most steps run on any OS — note that the OS check reports `OK` on Linux, `WARNING`
on macOS, and `CRITICAL` on Windows, so do final sign-off on Linux.

---

## 0. Prerequisites

```bash
python --version          # 3.10, 3.11, or 3.12
pip install build twine   # for packaging + metadata checks
# jq is handy for the JSON step (optional)
```

Use a throwaway config home for every test so you never touch a real `~/.du-doctor`:

```bash
export DU_DOCTOR_HOME="$(mktemp -d)/.du-doctor"          # bash
```
```powershell
$env:DU_DOCTOR_HOME = Join-Path ([System.IO.Path]::GetTempPath()) "du-doctor-test\.du-doctor"  # PowerShell
```

---

## 1. Automated gate (mirror CI)

Use a **fresh** venv for the dev install (`python -m venv .venv && pip install -e ".[dev]"`).
Then run from that venv:

```bash
ruff check .
black --check .
pytest -q                 # expect: 79 passed
```

All three must be green. This is the same gate CI runs on Python 3.10/3.11/3.12.

> **Run from the project venv, not a global Python**, so a stale global package can't interfere.
> The suite is fully offline (the bittensor SDK is mocked).

---

## 2. Clean-room build + install (the most important step)

Build the distribution and install the **wheel** into a brand-new venv — this catches missing
`package_data`, bad entry points, and dependency gaps that an editable install hides.

```bash
rm -rf dist build *.egg-info
python -m build                       # produces dist/*.whl and dist/*.tar.gz
twine check dist/*                     # metadata sanity (long-description, URLs)

python -m venv /tmp/du-clean
/tmp/du-clean/bin/pip install dist/*.whl
/tmp/du-clean/bin/du-doctor version    # entry point resolves, prints version
```

> On **Windows** the venv launchers live in `Scripts\`, not `bin/` (use the PowerShell block below or
> swap `bin/` → `Scripts\`). The rest of this guide's bash snippets assume Linux/macOS (the deployment
> target); on Windows run them in Git Bash and substitute `Scripts/` for `bin/`.

```powershell
Remove-Item -Recurse -Force dist,build -ErrorAction SilentlyContinue
python -m build
twine check dist/*
python -m venv $env:TEMP\du-clean
& "$env:TEMP\du-clean\Scripts\pip.exe" install (Get-ChildItem dist\*.whl).FullName
& "$env:TEMP\du-clean\Scripts\du-doctor.exe" version
```

**Verify metadata:** `twine check` passes and the wheel's `Project-URL: Repository` is
`https://github.com/siteauditor/data-universe-miner-doctor`:

```bash
python -m pip show -f data-universe-miner-doctor | grep -i repository    # or inspect dist METADATA
```

---

## 3. CLI smoke matrix

Run each in the clean venv (or the dev install) with the throwaway `DU_DOCTOR_HOME` set.

| # | Command | Expected |
| --- | --- | --- |
| 1 | `du-doctor init` | Creates `$DU_DOCTOR_HOME/config.yaml`; NETUID 13, network finney, "Data Universe". |
| 2 | `du-doctor init` (again) | "Config already exists"; **not** overwritten. |
| 3 | `du-doctor init --force --repo-path /tmp/x --hotkey 5F3sa2TJ...` | Overwrites; values land in the YAML; **no secret prompts**. |
| 4 | `du-doctor check` | Full Rich report; grouped by category; OK/WARNING/CRITICAL/SKIPPED shown; exit code reflects worst status. |
| 5 | `du-doctor check --json` | Clean JSON only; `du-doctor check --json \| jq .` succeeds; `overall_status`, `netuid`, `hotkey_masked`, `checks[]`, `suggested_fix_order[]` present. |
| 6 | `du-doctor doctor` | Identical output to `check` (alias). |
| 7 | `du-doctor check --verbose` | Also shows OK/SKIPPED detail. |
| 8 | `du-doctor check --no-color` | No ANSI colour codes. |
| 9 | `du-doctor watch --interval 5` | Loops; prints the "Watching every Ns" banner + per-cycle status; **Ctrl+C exits cleanly** ("Stopped."). |
| 10 | `du-doctor report --format markdown` | Writes `du-doctor-report.md`. |
| 11 | `du-doctor report --format html` | Writes `du-doctor-report.html`. |
| 12 | `du-doctor report --format json -o /tmp/r.json` | Writes valid JSON to the given path. |
| 13 | `du-doctor report --bundle` | Writes a redacted `.zip` (report in all formats + env-var **names** only). |
| 14 | `du-doctor check --subnet nope` | Exits non-zero with "Unknown subnet" + available list. |
| 15 | `du-doctor --help` / `du-doctor check --help` | Help renders for all commands. |

> **Testing `watch` (#9):** it shuts down gracefully (prints `Stopped.`, exit 0) on Ctrl+C **and** on
> SIGTERM / Ctrl+Break (so `systemctl stop` / `kill` are clean too). Quick manual check: run it, watch a
> couple of cycles, press Ctrl+C.
> - **Linux/macOS — automate:** `timeout -s INT 8 du-doctor watch --interval 3` (also works with `-s TERM`).
> - **Windows — automate:** a Git-Bash `timeout -s INT` does *not* reach a native console app. Drive it
>   from Python instead — launch with `creationflags=CREATE_NEW_PROCESS_GROUP`, then
>   `proc.send_signal(signal.CTRL_BREAK_EVENT)`; assert the output contains `Stopped.` and the exit code
>   is 0. (This is exactly how the shutdown path is verified during development.)

**Exit codes** (handy to assert in a script): `0`=OK, `1`=WARNING, `2`=CRITICAL.

```bash
du-doctor check >/dev/null 2>&1; echo "exit=$?"     # bash
```
```powershell
& du-doctor check *> $null; "exit=$LASTEXITCODE"     # PowerShell
```

JSON field completeness one-liner:

```bash
du-doctor check --json | python -c "import sys,json;d=json.load(sys.stdin);req={'id','title','category','status','summary','details','evidence','suggested_fixes','timestamp'};print('missing:',[c['id'] for c in d['checks'] if req-set(c)] or 'NONE')"
```

---

## 4. Safety / redaction spot-check (do not skip)

Create a throwaway scraping config, `.env`, and log with **fake** secrets, then confirm nothing leaks.

```bash
work=$(mktemp -d)
printf '{"scraper_configs":[{"scraper_id":"reddit.custom","cadence_seconds":300,"labels":["r/bittensor","r/MachineLearning","r/python"]}]}' > "$work/scraping_config.json"
printf 'APIFY_API_TOKEN=apify_api_SECRET123456\nREDDIT_CLIENT_SECRET=topsecret\n' > "$work/.env"
mkdir -p "$work/logs"
printf 'INFO ok\nAuthorization: Bearer abcdef1234567890\nrate limit exceeded\n5F3sa2TJAZ1jZsd8Z3kn1xpcyd2pHnY1Gh8M2KjQ9F3abcde\n' > "$work/logs/miner.log"

du-doctor check \
  --scraping-config "$work/scraping_config.json" \
  --env-path "$work/.env" \
  --hotkey 5F3sa2TJAZ1jZsd8Z3kn1xpcyd2pHnY1Gh8M2KjQ9F3abcde \
  --json > "$work/out.json"

# Must print NOTHING (zero leaked secrets):
grep -E 'apify_api_SECRET123456|topsecret|abcdef1234567890' "$work/out.json" && echo "LEAK!" || echo "clean"
```

Confirm in the output:
- API token / secret values appear as `***REDACTED***` (only the env-var **names** are referenced).
- The hotkey is masked `5F3sa2...F3abcde` (first6…last6).
- The SS58 in the log excerpt is masked.
- `Authorization: Bearer …` token is redacted.
- The Reddit credential check is `CRITICAL` (enabled but `REDDIT_*` incomplete), proving the credential
  logic reads names only.

Then verify the explicit opt-in works in **both** the terminal and JSON:
`du-doctor check --unsafe-show-full-hotkey --hotkey <ss58>` (and `... --json`) shows the full public
hotkey — and only with the flag. Real secrets (tokens, `.env` values, bearer headers) stay redacted
even with the flag, and the shareable `report` command always masks the hotkey regardless.

Also eyeball the generated `du-doctor-report.md` / `.html` / bundle for the same — they share the
redaction path, but a human glance is cheap insurance before sharing examples publicly.

---

## 5. With vs without the `bittensor` extra

- **Without** (`pip install dist/*.whl`): the three Bittensor checks report `CRITICAL`/`SKIPPED` with an
  install hint — the tool must **not** crash. This is the default release install.
- **With** (`pip install "dist/*.whl[bittensor]"`, in the miner's venv): `du-doctor check` connects to
  finney read-only and reports registration/UID/metrics. Full live coverage lives in
  [`VALIDATION.md`](./VALIDATION.md) — run that on a real miner box for a first public release.

---

## 6. Platform / version coverage

| Platform | Expectation |
| --- | --- |
| Ubuntu/Linux (target) | OS check `OK`; full PM2/process/log/ufw coverage. **Final sign-off here.** |
| macOS | OS check `WARNING` (fine for dev); rest works. |
| Windows | OS check `CRITICAL`; PM2/process/log checks unreliable — dev only. |
| Python 3.10 / 3.11 / 3.12 | All supported; CI matrix covers all three. |

---

## 7. Release dry-run (TestPyPI), then publish

Before the real PyPI release, validate end-to-end on **TestPyPI**:

```bash
twine upload --repository testpypi dist/*
python -m venv /tmp/du-testpypi
/tmp/du-testpypi/bin/pip install -i https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple data-universe-miner-doctor
/tmp/du-testpypi/bin/du-doctor version && /tmp/du-testpypi/bin/du-doctor check --json | jq .overall_status
```

Then the real release (handled by `.github/workflows/release.yml`):

1. Bump `version` in `pyproject.toml` (and `du_doctor/__init__.py` if it carries one).
2. Commit + push to `main`; confirm CI is green.
3. Tag and push: `git tag v0.1.0 && git push origin v0.1.0`
   — the workflow **fails the build if the tag ≠ `pyproject` version**, then publishes to PyPI via
   Trusted Publishing (no token needed).
4. Confirm the package page and `pip install data-universe-miner-doctor` in a fresh venv.

---

## 8. Optional: Docker smoke

Requires a **running Docker daemon** (e.g. Docker Desktop started, or a Linux Docker host / CI). A
`.dockerignore` keeps the build context lean (it excludes `.venv/`, `dist/`, caches), so the build
should be quick.

```bash
docker build -t du-doctor .
docker run --rm du-doctor version
docker run --rm -v "$PWD":/work -w /work du-doctor check --json | jq .overall_status
```

> If you see `failed to connect to the docker API ... dockerDesktopLinuxEngine`, the daemon isn't
> running — start Docker Desktop (or run this step on a Linux/CI host) and retry.

---

## 9. Go / No-Go checklist

- [ ] `ruff` + `black --check` + `pytest -q` (79) all green on 3.10–3.12.
- [ ] `python -m build` + `twine check dist/*` pass; Repository URL is `siteauditor/data-universe-miner-doctor`.
- [ ] Wheel installs clean in a fresh venv; `du-doctor version` works.
- [ ] CLI smoke matrix (§3) all pass; `check --json | jq .` valid; exit codes correct.
- [ ] Redaction spot-check (§4) prints `clean` — zero leaked secrets; hotkey masked.
- [ ] No-bittensor install does not crash; with-bittensor live run sane (or VALIDATION.md done).
- [ ] Linux final sign-off done.
- [ ] TestPyPI install verified.
- [ ] `pyproject` version bumped; tag matches; CI green.
