"""Redaction helpers.

The whole point of this tool is to be safe to run and safe to share its output.
These helpers guarantee that secrets never make it into a report, a log
excerpt, or the terminal — and that hotkeys are masked unless the user has
explicitly opted in to seeing the full value.
"""

from __future__ import annotations

import re
from typing import Optional

REDACTED = "***REDACTED***"

# Keys whose VALUES must never be shown. Matched as whole-ish identifiers so a
# key like ``APIFY_API_TOKEN`` or ``REDDIT_CLIENT_SECRET`` is caught, but a
# benign word that merely contains "key" is not over-matched on its own.
_SENSITIVE_KEY_PARTS = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "PWD",
    "APIKEY",
    "API_KEY",
    "PRIVATE_KEY",
    "PRIVATEKEY",
    "MNEMONIC",
    "SEED_PHRASE",
    "SEEDPHRASE",
    "ACCESS_KEY",
    "SECRET_KEY",
    "AUTH",
    "CREDENTIAL",
)

# KEY = VALUE  /  KEY: VALUE  (quoted or unquoted value)
_KV_RE = re.compile(r"""(?ix)
    \b([A-Z0-9_.\-]*(?:%s)[A-Z0-9_.\-]*)   # 1: a sensitive-looking key
    \s*([=:])\s*                            # 2: separator
    (['"]?)                                 # 3: optional opening quote
    ([^\s'"]+)                              # 4: the secret value
    \3                                      # matching closing quote
    """ % "|".join(_SENSITIVE_KEY_PARTS))

# Authorization: Bearer <token>
_BEARER_RE = re.compile(r"(?i)\b(bearer|token)\s+([A-Za-z0-9._\-]{12,})")

# Apify tokens look like ``apify_api_XXXXXXXX...`` — redact even if no key= prefix.
_APIFY_TOKEN_RE = re.compile(r"(?i)\bapify_api_[A-Za-z0-9]{6,}\b")

# SS58 addresses (substrate / bittensor). Public, but masked by policy.
_SS58_RE = re.compile(r"\b5[1-9A-HJ-NP-Za-km-z]{46,48}\b")


def mask_hotkey(hotkey: Optional[str], show_full: bool = False) -> Optional[str]:
    """Mask an SS58 hotkey to ``first6...last6``.

    >>> mask_hotkey("5F3abcdefghijklmnopqrstuvwxyzXyZ921")
    '5F3abc...XyZ921'

    Returns ``None`` for falsy input. When ``show_full`` is True the value is
    returned unchanged (only when the user passed ``--unsafe-show-full-hotkey``).
    """
    if not hotkey:
        return None
    hotkey = hotkey.strip()
    if show_full:
        return hotkey
    if len(hotkey) <= 12:
        # Too short to mask meaningfully without revealing most of it.
        return f"{hotkey[:2]}...{hotkey[-2:]}" if len(hotkey) > 4 else REDACTED
    return f"{hotkey[:6]}...{hotkey[-6:]}"


def _mask_ss58(match: re.Match) -> str:
    return mask_hotkey(match.group(0)) or REDACTED


def redact_secrets(text: Optional[str], mask_ss58: bool = True) -> str:
    """Return ``text`` with secrets removed and SS58 addresses masked.

    Safe to call on log lines, command output, and report content. Never raises.
    """
    if not text:
        return ""

    def _kv_sub(m: re.Match) -> str:
        return f"{m.group(1)}{m.group(2)}{REDACTED}"

    # Bearer/Token must run BEFORE the key=value rule, otherwise a header like
    # "Authorization: Bearer <token>" would have "Bearer" consumed as the value
    # and the real token left exposed.
    text = _BEARER_RE.sub(lambda m: f"{m.group(1)} {REDACTED}", text)
    text = _KV_RE.sub(_kv_sub, text)
    text = _APIFY_TOKEN_RE.sub(REDACTED, text)
    if mask_ss58:
        text = _SS58_RE.sub(_mask_ss58, text)
    return text


def redact_lines(lines: list[str], mask_ss58: bool = True) -> list[str]:
    """Redact every line in a list (used for log excerpts)."""
    return [redact_secrets(line, mask_ss58=mask_ss58) for line in lines]


def redact_structure(obj: object, mask_ss58: bool = True) -> object:
    """Recursively redact every string in a JSON-like structure.

    Used to sanitise a whole serialized report — keys and non-string values
    (numbers, bools, None) are preserved so the shape/metrics stay intact while
    secrets in any string leaf are removed.
    """
    if isinstance(obj, str):
        return redact_secrets(obj, mask_ss58=mask_ss58)
    if isinstance(obj, dict):
        return {key: redact_structure(value, mask_ss58=mask_ss58) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [redact_structure(item, mask_ss58=mask_ss58) for item in obj]
    return obj


def is_sensitive_key(name: str) -> bool:
    """True if an env var NAME looks like it holds a secret."""
    upper = name.upper()
    return any(part in upper for part in _SENSITIVE_KEY_PARTS)
