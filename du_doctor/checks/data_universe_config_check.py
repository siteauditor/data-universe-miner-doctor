"""Data Universe ``scraping_config.json`` + credential checks.

This is the heart of the "why am I not earning?" diagnosis for SN13: it locates
and validates the scraping config, figures out which scrapers are enabled, and
verifies the credentials those scrapers need are present in ``.env`` (or the
environment) — WITHOUT ever reading or printing a single credential value.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from du_doctor.checks.base import BaseCheck
from du_doctor.models import CheckCategory, CheckResult, CheckStatus
from du_doctor.utils.files import expand_path

# Keywords that indicate a scraper / config concept is present.
_SCRAPER_KEYWORDS = [
    "apify",
    "reddit",
    "twitter",
    "youtube",
    "transcript",
    "huggingface",
    "label",
    "cadence_seconds",
    "max_data_entities",
]

# Labels considered too generic to be competitive on their own.
_GENERIC_LABELS = {
    "news",
    "crypto",
    "bitcoin",
    "btc",
    "eth",
    "ethereum",
    "finance",
    "money",
    "trading",
    "price",
    "general",
}

# JSON keys we harvest recursively (lower-cased for matching).
_HARVEST_KEYS = {
    "cadence_seconds",
    "max_data_entities",
    "label_choices",
    "labels",
    "label",
    "scraper_id",
}

EXTREMELY_SLOW_CADENCE = 86_400  # > 1 day between scrapes
LOW_MAX_ENTITIES = 25  # smallest "reasonable" batch
MIN_DISTINCT_LABELS = 3


def read_env_keys(env_path: Optional[Path]) -> set[str]:
    """Return the set of variable NAMES defined in a .env file (never values).

    Tolerates ``export KEY=...``, comments, and blank lines. Missing file -> ``set()``.
    """
    keys: set[str] = set()
    if env_path is None or not env_path.exists() or not env_path.is_file():
        return keys
    try:
        for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            name = line.split("=", 1)[0].strip()
            if name:
                keys.add(name)
    except Exception:  # noqa: BLE001
        return keys
    return keys


class DataUniverseConfigCheck(BaseCheck):
    category = CheckCategory.DATA_UNIVERSE_CONFIG
    name = "data_universe_config"

    def run(self) -> list[CheckResult]:
        path = self._locate_config()
        if path is None:
            return [
                self.result(
                    "du_config_locate",
                    "scraping_config.json",
                    CheckStatus.WARNING,
                    "Could not find scraping_config.json. The miner may be using defaults.",
                    details={"searched": [str(p) for p in self._candidate_paths()]},
                    suggested_fixes=[
                        "Create or point to your Data Universe scraping_config.json "
                        "(config: scraping_config_path or --scraping-config).",
                    ],
                )
            ]

        # Validate JSON.
        try:
            raw_text = path.read_text(encoding="utf-8", errors="replace")
            data = json.loads(raw_text)
        except Exception as exc:  # noqa: BLE001
            return [
                self.result(
                    "du_config_json",
                    "scraping_config.json",
                    CheckStatus.CRITICAL,
                    f"scraping_config.json is not valid JSON: {exc}",
                    details={"path": str(path)},
                    suggested_fixes=[
                        "Fix the JSON syntax (a stray comma/quote is common).",
                        "Validate with: python -m json.tool scraping_config.json",
                    ],
                )
            ]

        results: list[CheckResult] = [
            self.result(
                "du_config_json",
                "scraping_config.json",
                CheckStatus.OK,
                "scraping_config.json is valid JSON.",
                details={"path": str(path)},
            )
        ]

        raw_lower = raw_text.lower()
        harvested = self._harvest(data)
        scraper_ids = self._scraper_ids(harvested)

        results.append(self._check_scrapers(raw_lower, scraper_ids))
        results.append(self._check_cadence(harvested))
        results.append(self._check_max_entities(harvested))
        results.append(self._check_labels(harvested))
        results.extend(self._check_credentials(raw_lower, scraper_ids))
        return results

    # ------------------------------------------------------------------ #
    def _candidate_paths(self) -> list[Path]:
        candidates: list[Path] = []
        configured = expand_path(self.config.scraping_config_path)
        if configured is not None:
            candidates.append(configured)
        repo = expand_path(self.config.subnet_repo_path)
        if repo is not None:
            candidates.append(repo / "scraping_config.json")
            candidates.append(repo / "neurons" / "scraping_config.json")
        candidates.append(Path.cwd() / "scraping_config.json")
        # Deduplicate preserving order.
        seen: set[str] = set()
        unique = []
        for c in candidates:
            key = str(c)
            if key not in seen:
                seen.add(key)
                unique.append(c)
        return unique

    def _locate_config(self) -> Optional[Path]:
        for c in self._candidate_paths():
            try:
                if c.is_file():
                    return c
            except Exception:  # noqa: BLE001
                continue
        return None

    def _harvest(self, data: Any) -> dict[str, list[Any]]:
        out: dict[str, list[Any]] = {}

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                for k, v in node.items():
                    if k.lower() in _HARVEST_KEYS:
                        out.setdefault(k.lower(), []).append(v)
                    walk(v)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(data)
        return out

    def _scraper_ids(self, harvested: dict[str, list[Any]]) -> list[str]:
        """Lower-cased scraper_id values (e.g. 'reddit.custom', 'x.apidojo')."""
        return [
            str(v).strip().lower() for v in harvested.get("scraper_id", []) if isinstance(v, str)
        ]

    def _x_enabled(self, raw_lower: str, scraper_ids: list[str]) -> bool:
        """Whether an X/Twitter scraper appears enabled.

        Prefer concrete scraper_id values (robust); only fall back to scanning
        the raw text when no scraper_id is present, and even then avoid the
        noisy bare ``x.`` match by requiring a known X scraper id or 'twitter'.
        """
        if scraper_ids:
            return any(
                sid == "x" or sid.startswith("x.") or "twitter" in sid for sid in scraper_ids
            )
        return "twitter" in raw_lower or "x.apidojo" in raw_lower or "x.flash" in raw_lower

    def _check_scrapers(self, raw_lower: str, scraper_ids: list[str]) -> CheckResult:
        found = [kw for kw in _SCRAPER_KEYWORDS if kw in raw_lower]
        if scraper_ids:
            # Classify from concrete scraper_id values (most reliable).
            scrapers = []
            for family, needles in (
                ("reddit", ("reddit",)),
                ("youtube", ("youtube",)),
                ("apify", ("apify",)),
                ("huggingface", ("huggingface", "hugging_face")),
            ):
                if any(any(n in sid for n in needles) for sid in scraper_ids):
                    scrapers.append(family)
        else:
            scrapers = [s for s in ("apify", "reddit", "youtube", "huggingface") if s in found]
        if self._x_enabled(raw_lower, scraper_ids) and "x/twitter" not in scrapers:
            scrapers.append("x/twitter")
        self.ctx.note("scrapers_enabled", scrapers)
        if not scrapers:
            return self.result(
                "du_config_scrapers",
                "Configured scrapers",
                CheckStatus.WARNING,
                "No recognizable scrapers detected in scraping_config.json.",
                details={"keywords_found": found},
                suggested_fixes=["Configure at least one scraper (e.g. Reddit, X, YouTube)."],
            )
        return self.result(
            "du_config_scrapers",
            "Configured scrapers",
            CheckStatus.OK,
            f"Detected scrapers: {', '.join(scrapers)}.",
            details={"scrapers": scrapers, "keywords_found": found},
        )

    def _check_cadence(self, harvested: dict[str, list[Any]]) -> CheckResult:
        values = harvested.get("cadence_seconds", [])
        if not values:
            return self.result(
                "du_config_cadence",
                "cadence_seconds",
                CheckStatus.WARNING,
                "cadence_seconds is missing for the scraper(s).",
                suggested_fixes=["Add a cadence_seconds (how often to scrape) per scraper config."],
            )
        numeric = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if numeric:
            # Published for the data check's cadence-aware idle window.
            self.ctx.note("max_cadence_seconds", max(numeric))
        non_numeric = [v for v in values if not isinstance(v, (int, float)) or isinstance(v, bool)]
        if non_numeric:
            return self.result(
                "du_config_cadence",
                "cadence_seconds",
                CheckStatus.WARNING,
                f"cadence_seconds has non-numeric value(s): {non_numeric}.",
                details={"values": values},
                suggested_fixes=["cadence_seconds must be a number of seconds."],
            )
        slow = [v for v in values if v > EXTREMELY_SLOW_CADENCE]
        if slow:
            return self.result(
                "du_config_cadence",
                "cadence_seconds",
                CheckStatus.WARNING,
                f"cadence_seconds is extremely slow (> 1 day): {slow}. Data may be stale.",
                details={"values": values},
                suggested_fixes=["Lower cadence_seconds so data is scraped more frequently."],
            )
        return self.result(
            "du_config_cadence",
            "cadence_seconds",
            CheckStatus.OK,
            f"cadence_seconds configured ({values}).",
            details={"values": values},
        )

    def _check_max_entities(self, harvested: dict[str, list[Any]]) -> CheckResult:
        values = [v for v in harvested.get("max_data_entities", []) if isinstance(v, (int, float))]
        if not harvested.get("max_data_entities"):
            return self.result(
                "du_config_max_entities",
                "max_data_entities",
                CheckStatus.WARNING,
                "max_data_entities is missing; the scraper may collect very little per cycle.",
                suggested_fixes=[
                    "Set max_data_entities per label so each cycle collects enough data."
                ],
            )
        if values and max(values) < LOW_MAX_ENTITIES:
            return self.result(
                "du_config_max_entities",
                "max_data_entities",
                CheckStatus.WARNING,
                f"max_data_entities looks low (max configured = {max(values)}).",
                details={"values": values},
                suggested_fixes=[
                    "Consider increasing max_data_entities to collect more per cycle."
                ],
            )
        return self.result(
            "du_config_max_entities",
            "max_data_entities",
            CheckStatus.OK,
            "max_data_entities configured.",
            details={"values": values},
        )

    def _check_labels(self, harvested: dict[str, list[Any]]) -> CheckResult:
        labels = self._flatten_labels(harvested)
        normalized = {self._normalize_label(l) for l in labels if isinstance(l, str)}
        normalized.discard("")
        self.ctx.note("label_count", len(normalized))

        if not normalized:
            self.ctx.note("generic_labels", True)
            return self.result(
                "du_config_labels",
                "Labels",
                CheckStatus.WARNING,
                "No labels configured to scrape.",
                suggested_fixes=["Add label_choices so the miner scrapes targeted data."],
            )
        if len(normalized) < MIN_DISTINCT_LABELS:
            self.ctx.note("generic_labels", True)
            return self.result(
                "du_config_labels",
                "Labels",
                CheckStatus.WARNING,
                f"Only {len(normalized)} distinct label(s) configured: {sorted(normalized)}.",
                details={"labels": sorted(normalized)},
                suggested_fixes=[
                    "A very small label set limits how much (and how varied) data you collect.",
                    "Review the subnet docs for which labels are valued.",
                ],
            )
        if normalized.issubset(_GENERIC_LABELS):
            self.ctx.note("generic_labels", True)
            return self.result(
                "du_config_labels",
                "Labels",
                CheckStatus.WARNING,
                f"Labels look too generic: {sorted(normalized)}.",
                details={"labels": sorted(normalized)},
                suggested_fixes=[
                    "Generic labels may be less competitive. Review your label strategy.",
                    "Check the subnet docs for higher-value / less-saturated labels.",
                ],
            )
        self.ctx.note("generic_labels", False)
        return self.result(
            "du_config_labels",
            "Labels",
            CheckStatus.OK,
            f"{len(normalized)} distinct labels configured.",
            details={"label_count": len(normalized)},
        )

    def _flatten_labels(self, harvested: dict[str, list[Any]]) -> list[str]:
        out: list[str] = []
        for key in ("label_choices", "labels", "label"):
            for v in harvested.get(key, []):
                if isinstance(v, str):
                    out.append(v)
                elif isinstance(v, list):
                    out.extend(str(x) for x in v if isinstance(x, (str, int, float)))
        return out

    def _normalize_label(self, label: str) -> str:
        s = label.strip().lower()
        for prefix in ("#", "r/", "u/", "@"):
            if s.startswith(prefix):
                s = s[len(prefix) :]
        return s.strip()

    def _locate_env(self) -> Optional[Path]:
        """Resolve the .env file: configured path first, then <repo>/.env."""
        configured = expand_path(self.config.env_path)
        if configured is not None and configured.is_file():
            return configured
        repo = expand_path(self.config.subnet_repo_path)
        if repo is not None:
            candidate = repo / ".env"
            if candidate.is_file():
                return candidate
        return configured  # may be None or a non-existent path (for the message)

    def _check_credentials(self, raw_lower: str, scraper_ids: list[str]) -> list[CheckResult]:
        env_path = self._locate_env()
        # Names defined in .env, plus names exported in the current environment
        # (the miner may receive credentials either way).
        env_keys = read_env_keys(env_path) | set(os.environ.keys())
        results: list[CheckResult] = []
        any_missing = False

        rules = self.config.data_universe.scraper_credentials
        for scraper_name, rule in rules.items():
            enabled = any(token.lower() in raw_lower for token in rule.enabled_if_config_contains)
            if not enabled:
                continue
            required = rule.required_env_names
            present = [name for name in required if name in env_keys]
            missing = [name for name in required if name not in env_keys]

            # Per-scraper semantics: Apify needs ANY of its tokens; others need ALL.
            any_of = scraper_name.lower() == "apify"
            satisfied = bool(present) if any_of else not missing

            if satisfied:
                results.append(
                    self.result(
                        f"du_cred_{scraper_name}",
                        f"{scraper_name.title()} credentials",
                        CheckStatus.OK,
                        f"{scraper_name.title()} scraper enabled and required credentials present.",
                        details={"present": present},
                    )
                )
            else:
                any_missing = True
                need = " or ".join(required) if any_of else ", ".join(missing)
                results.append(
                    self.result(
                        f"du_cred_{scraper_name}",
                        f"{scraper_name.title()} credentials",
                        CheckStatus.CRITICAL,
                        f"{scraper_name.title()} scraper enabled but missing credentials: {need}.",
                        details={"missing": missing, "required": required},
                        suggested_fixes=[
                            f"Add the missing variable(s) to {env_path or '.env'}: {need}",
                            "An enabled scraper cannot run without its credentials.",
                        ],
                    )
                )

        # X / Twitter: requirement is not always known (often via Apify actor).
        if self._x_enabled(raw_lower, scraper_ids):
            apify_ok = any(k in env_keys for k in ("APIFY_API_TOKEN", "APIFY_TOKEN"))
            twitter_like = any(
                k for k in env_keys if "TWITTER" in k.upper() or k.upper().startswith("X_")
            )
            if not (apify_ok or twitter_like):
                # Deliberately NOT flipping `any_missing`: the X requirement is
                # uncertain (often satisfied via an Apify actor), so this stays a
                # standalone WARNING and must not escalate the scoring heuristic
                # to a CRITICAL "scraper cannot run" verdict.
                results.append(
                    self.result(
                        "du_cred_x",
                        "X / Twitter credentials",
                        CheckStatus.WARNING,
                        "X/Twitter scraping appears enabled but no obvious credentials were found "
                        "(it often runs via an Apify actor — exact requirement unknown).",
                        suggested_fixes=[
                            "If using the Apify X scraper, set APIFY_API_TOKEN.",
                            "Otherwise set the token your X scraper requires.",
                        ],
                    )
                )

        self.ctx.note("credentials_missing", any_missing)

        if not results:
            results.append(
                self.result(
                    "du_credentials",
                    "Scraper credentials",
                    CheckStatus.SKIPPED,
                    "No credential-requiring scrapers detected as enabled.",
                )
            )
        return results
