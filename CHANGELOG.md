# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [0.1.2] - 2026-06-01

### Changed
- `du-doctor version` now reads the version from the installed package metadata,
  so it always matches the released version (single source of truth is
  `pyproject.toml`; no more drift between the code and the release).

## [0.1.1] - 2026-06-01

### Changed
- README: PyPI-first install instructions, corrected repository URLs (public
  repo), absolute links to example files, and added PyPI / downloads / CI /
  license badges.

## [0.1.0] - 2026-05-30

### Added
- Initial public release — a read-only diagnostic CLI for Bittensor **Data
  Universe** (SN13) miners.
- **Checks:** system (OS/Python/disk/RAM/CPU/internet/GPU); Bittensor
  registration + metagraph metrics (uid, rank, trust, consensus, incentive,
  emission, stake, dividends, validator_trust); repo status; PM2/process;
  network/axon; logs; `scraping_config.json` + scraper credential presence;
  local data freshness; and earning heuristics.
- **Reporters:** terminal (Rich), JSON, Markdown, HTML, and a redacted support
  bundle.
- **Snapshots** with incentive/emission/rank drop detection.
- **Subnet-profile plugin system** (`du_doctor.profiles` entry point).
- Read-only & privacy-first: secret redaction, hotkey masking, never unlocks
  wallets, never moves TAO, never uploads anything.

[0.1.2]: https://github.com/siteauditor/data-universe-miner-doctor/releases/tag/v0.1.2
[0.1.1]: https://github.com/siteauditor/data-universe-miner-doctor/releases/tag/v0.1.1
[0.1.0]: https://github.com/siteauditor/data-universe-miner-doctor/releases/tag/v0.1.0
