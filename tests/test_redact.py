"""Redaction + hotkey masking."""

from __future__ import annotations

from du_doctor.utils.redact import REDACTED, is_sensitive_key, mask_hotkey, redact_secrets

SS58 = "5F3sa2TJAWMqDhXG6jhV4N8koP5Gy8TpaNS1Repo9XaBcD12"  # 48-char ss58-like


def test_mask_hotkey_shows_first_and_last_six():
    masked = mask_hotkey(SS58)
    assert masked == f"{SS58[:6]}...{SS58[-6:]}"
    assert "..." in masked
    # The middle must be hidden.
    assert SS58[6:-6] not in masked


def test_mask_hotkey_show_full_returns_original():
    assert mask_hotkey(SS58, show_full=True) == SS58


def test_mask_hotkey_none():
    assert mask_hotkey(None) is None
    assert mask_hotkey("") is None


def test_redact_api_keys():
    text = "APIFY_API_TOKEN=apify_api_supersecretvalue123"
    out = redact_secrets(text)
    assert "supersecretvalue123" not in out
    assert REDACTED in out


def test_redact_env_values():
    text = "REDDIT_CLIENT_SECRET: my-reddit-secret-xyz"
    out = redact_secrets(text)
    assert "my-reddit-secret-xyz" not in out
    assert REDACTED in out


def test_redact_bearer_token():
    text = "Authorization: Bearer abcDEF1234567890token"
    out = redact_secrets(text)
    assert "abcDEF1234567890token" not in out


def test_redact_masks_ss58_in_text():
    text = f"miner hotkey {SS58} connected"
    out = redact_secrets(text)
    assert SS58 not in out
    assert f"{SS58[:6]}...{SS58[-6:]}" in out


def test_redact_preserves_benign_text():
    text = "miner started ok, scraping reddit labels"
    assert redact_secrets(text) == text


def test_redact_structure_recurses_and_preserves_shape():
    from du_doctor.utils.redact import redact_structure

    data = {
        "netuid": 13,
        "active": True,
        "checks": [
            {"summary": "APIFY_API_TOKEN=apify_api_supersecret", "rows": 5, "ok": None},
            {"evidence": [f"hotkey {SS58} seen"]},
        ],
    }
    out = redact_structure(data)
    assert out["netuid"] == 13  # numbers preserved
    assert out["active"] is True  # bools preserved
    assert out["checks"][0]["rows"] == 5
    assert out["checks"][0]["ok"] is None
    blob = str(out)
    assert "apify_api_supersecret" not in blob
    assert SS58 not in blob  # full ss58 masked
    assert "REDACTED" in blob


def test_is_sensitive_key():
    assert is_sensitive_key("APIFY_API_TOKEN")
    assert is_sensitive_key("REDDIT_CLIENT_SECRET")
    assert is_sensitive_key("WALLET_PASSWORD")
    # A plain username is not a secret.
    assert is_sensitive_key("REDDIT_USERNAME") is False
