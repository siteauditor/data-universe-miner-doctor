"""Shareable support bundle: a zip of the report in every format.

Everything written is already redacted (the reporters redact; the JSON is the
masked DoctorReport). Bundling is explicit and on-demand — nothing is uploaded.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Optional

from du_doctor.models import DoctorReport
from du_doctor.reporters.html_reporter import render_html
from du_doctor.reporters.json_reporter import render_json
from du_doctor.reporters.markdown_reporter import render_markdown

DEFAULT_BUNDLE_PATH = "du-doctor-bundle.zip"


def write_bundle(
    report: DoctorReport,
    path: str | Path = DEFAULT_BUNDLE_PATH,
    extra_files: Optional[dict[str, str]] = None,
) -> Path:
    """Write a zip with the report as json/md/html plus any ``extra_files``.

    ``extra_files`` maps archive filename -> text content (caller must ensure
    it is already safe to share — e.g. env var NAMES only, never values).
    """
    out = Path(path)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("du-doctor-report.json", render_json(report))
        zf.writestr("du-doctor-report.md", render_markdown(report))
        zf.writestr("du-doctor-report.html", render_html(report))
        for name, content in (extra_files or {}).items():
            zf.writestr(name, content)
    return out
