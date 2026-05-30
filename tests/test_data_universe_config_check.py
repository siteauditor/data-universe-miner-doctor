"""Data Universe scraping_config.json + credential checks."""

from __future__ import annotations

import json

from du_doctor.checks.base import RunContext
from du_doctor.checks.data_universe_config_check import DataUniverseConfigCheck
from du_doctor.config import load_config
from du_doctor.models import CheckStatus


def _run(tmp_path, monkeypatch, config_obj, env_lines=None, clear_env=()):
    for name in clear_env:
        monkeypatch.delenv(name, raising=False)

    scraping = tmp_path / "scraping_config.json"
    if isinstance(config_obj, str):
        scraping.write_text(config_obj, encoding="utf-8")  # allow raw/invalid JSON
    else:
        scraping.write_text(json.dumps(config_obj), encoding="utf-8")

    env_path = tmp_path / ".env"
    env_path.write_text("\n".join(env_lines or []), encoding="utf-8")

    cfg = load_config()
    cfg.scraping_config_path = str(scraping)
    cfg.env_path = str(env_path)
    cfg.subnet_repo_path = ""  # avoid picking up any repo-root config
    ctx = RunContext()
    return DataUniverseConfigCheck(cfg, ctx).run(), ctx


def _by_id(results):
    return {r.id: r for r in results}


def test_invalid_json_is_critical(tmp_path, monkeypatch):
    results, _ = _run(tmp_path, monkeypatch, "{ this is : not json, }")
    by_id = _by_id(results)
    assert by_id["du_config_json"].status == CheckStatus.CRITICAL


def test_valid_json_is_ok(tmp_path, monkeypatch):
    cfg = {
        "scraper_configs": [
            {
                "scraper_id": "Reddit.custom",
                "cadence_seconds": 60,
                "labels_to_scrape": [
                    {
                        "label_choices": ["r/Bitcoin", "r/wallstreetbets", "r/solana"],
                        "max_data_entities": 100,
                    }
                ],
            }
        ]
    }
    results, _ = _run(
        tmp_path,
        monkeypatch,
        cfg,
        env_lines=[
            "REDDIT_CLIENT_ID=x",
            "REDDIT_CLIENT_SECRET=y",
            "REDDIT_USERNAME=z",
            "REDDIT_PASSWORD=w",
        ],
    )
    by_id = _by_id(results)
    assert by_id["du_config_json"].status == CheckStatus.OK


def test_apify_enabled_but_token_missing_is_critical(tmp_path, monkeypatch):
    cfg = {
        "scraper_configs": [
            {
                "scraper_id": "Apify.actor",
                "cadence_seconds": 300,
                "labels_to_scrape": [
                    {
                        "label_choices": ["#bitcoin", "#ethereum", "#solana"],
                        "max_data_entities": 100,
                    }
                ],
            }
        ]
    }
    results, ctx = _run(tmp_path, monkeypatch, cfg, clear_env=("APIFY_API_TOKEN", "APIFY_TOKEN"))
    by_id = _by_id(results)
    assert "du_cred_apify" in by_id
    assert by_id["du_cred_apify"].status == CheckStatus.CRITICAL
    assert ctx.get("credentials_missing") is True


def test_reddit_credentials_missing_is_critical(tmp_path, monkeypatch):
    cfg = {
        "scraper_configs": [
            {
                "scraper_id": "Reddit.custom",
                "cadence_seconds": 60,
                "labels_to_scrape": [
                    {
                        "label_choices": ["r/Bitcoin", "r/ethfinance", "r/solana"],
                        "max_data_entities": 100,
                    }
                ],
            }
        ]
    }
    results, _ = _run(
        tmp_path,
        monkeypatch,
        cfg,
        env_lines=["REDDIT_CLIENT_ID=only_this_one"],
        clear_env=("REDDIT_CLIENT_SECRET", "REDDIT_USERNAME", "REDDIT_PASSWORD"),
    )
    by_id = _by_id(results)
    assert "du_cred_reddit" in by_id
    assert by_id["du_cred_reddit"].status == CheckStatus.CRITICAL
    missing = by_id["du_cred_reddit"].details.get("missing", [])
    assert "REDDIT_CLIENT_SECRET" in missing


def test_generic_labels_warning(tmp_path, monkeypatch):
    cfg = {
        "scraper_configs": [
            {
                "scraper_id": "Reddit.custom",
                "cadence_seconds": 60,
                "labels_to_scrape": [
                    {"label_choices": ["news", "crypto"], "max_data_entities": 100}
                ],
            }
        ]
    }
    results, ctx = _run(
        tmp_path,
        monkeypatch,
        cfg,
        env_lines=[
            "REDDIT_CLIENT_ID=x",
            "REDDIT_CLIENT_SECRET=y",
            "REDDIT_USERNAME=z",
            "REDDIT_PASSWORD=w",
        ],
    )
    by_id = _by_id(results)
    assert by_id["du_config_labels"].status == CheckStatus.WARNING
    assert ctx.get("generic_labels") is True


def test_x_scraper_detected_via_scraper_id(tmp_path, monkeypatch):
    # X.apidojo uses Apify under the hood; with no token present we expect the
    # X/Twitter credential WARNING and x/twitter in the detected scrapers.
    cfg = {
        "scraper_configs": [
            {
                "scraper_id": "X.apidojo",
                "cadence_seconds": 300,
                "labels_to_scrape": [
                    {"label_choices": ["#ai", "#defi", "#gaming"], "max_data_entities": 100}
                ],
            }
        ]
    }
    results, ctx = _run(tmp_path, monkeypatch, cfg, clear_env=("APIFY_API_TOKEN", "APIFY_TOKEN"))
    by_id = _by_id(results)
    assert "x/twitter" in by_id["du_config_scrapers"].details.get("scrapers", [])
    assert by_id["du_cred_x"].status == CheckStatus.WARNING
    # The uncertain X warning must NOT escalate the scoring heuristic.
    assert ctx.get("credentials_missing") is False


def test_reddit_only_config_has_no_false_x_detection(tmp_path, monkeypatch):
    cfg = {
        "scraper_configs": [
            {
                "scraper_id": "Reddit.custom",
                "cadence_seconds": 60,
                "labels_to_scrape": [
                    {
                        "label_choices": ["r/Bitcoin", "r/solana", "r/ethfinance"],
                        "max_data_entities": 100,
                    }
                ],
            }
        ]
    }
    results, _ = _run(
        tmp_path,
        monkeypatch,
        cfg,
        env_lines=[
            "REDDIT_CLIENT_ID=x",
            "REDDIT_CLIENT_SECRET=y",
            "REDDIT_USERNAME=z",
            "REDDIT_PASSWORD=w",
        ],
    )
    by_id = _by_id(results)
    assert "du_cred_x" not in by_id
    assert "x/twitter" not in by_id["du_config_scrapers"].details.get("scrapers", [])


def test_missing_cadence_warns(tmp_path, monkeypatch):
    cfg = {
        "scraper_configs": [
            {
                "scraper_id": "Reddit.custom",
                "labels_to_scrape": [{"label_choices": ["r/a", "r/b", "r/c"]}],
            }
        ]
    }
    results, _ = _run(
        tmp_path,
        monkeypatch,
        cfg,
        env_lines=[
            "REDDIT_CLIENT_ID=x",
            "REDDIT_CLIENT_SECRET=y",
            "REDDIT_USERNAME=z",
            "REDDIT_PASSWORD=w",
        ],
    )
    by_id = _by_id(results)
    assert by_id["du_config_cadence"].status == CheckStatus.WARNING
