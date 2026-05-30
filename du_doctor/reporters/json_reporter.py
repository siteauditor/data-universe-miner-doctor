"""Machine-readable JSON output.

This is the integration point for future products (Telegram bot, SaaS
dashboard, incident service): the JSON schema mirrors the Pydantic models
exactly, so anything consuming it gets a stable contract.
"""

from __future__ import annotations

import json

from du_doctor.models import DoctorReport
from du_doctor.utils.redact import redact_structure


def report_to_dict(report: DoctorReport, show_full_hotkey: bool = False) -> dict:
    """Serialise the report to a plain redacted dict (enums as values, ISO datetimes).

    Redaction is applied here too (like the markdown/HTML/terminal reporters) so
    every JSON sink — ``check --json``, the support bundle, the agent payload —
    is safe to share. Idempotent on already-clean fields.

    ``show_full_hotkey`` mirrors the terminal reporter: when the user has
    explicitly opted in (``--unsafe-show-full-hotkey``), the public hotkey ss58
    in the headline ``hotkey_masked`` field is preserved instead of being
    re-masked by the blanket ss58 redaction. This affects ONLY that one field —
    real secrets (tokens, .env values, bearer headers) and any ss58 appearing in
    log excerpts/evidence are still fully redacted.
    """
    data = redact_structure(report.model_dump(mode="json"))
    if show_full_hotkey and report.hotkey_masked:
        data["hotkey_masked"] = report.hotkey_masked
    return data


def render_json(report: DoctorReport, indent: int = 2, show_full_hotkey: bool = False) -> str:
    """Render the report as a JSON string."""
    return json.dumps(
        report_to_dict(report, show_full_hotkey=show_full_hotkey),
        indent=indent,
        ensure_ascii=False,
    )
