"""Architecture guard: the web layer must not re-implement aggregation (#809).

The "今週の注意点" caution card once imported ``FormAnomalyDetector`` from
``garmin_mcp.rag`` and re-derived the material-event aggregation with its own
constants, drifting from the injury-risk signal. That logic now lives behind
``GarminDBReader``. This guard makes any future ``garmin_mcp.rag`` coupling in
the web source a build failure, so a re-implementation cannot silently return.

A single pre-existing import (the heat-adjustment regression *model* consumed by
the trends query) is grandfathered via an allowlist; new rag imports -- and the
form-anomaly detector in particular -- are forbidden.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import garmin_web

# Pre-existing, non-aggregation coupling tracked separately from #809. New
# entries must not be added; the form-anomaly detector must never appear here.
_ALLOWED_RAG_MODULES = {
    "garmin_mcp.rag.queries.heat_adjustment",
}

_RAG_IMPORT_RE = re.compile(
    r"^\s*(?:from|import)\s+(garmin_mcp\.rag[\w.]*)", re.MULTILINE
)


@pytest.mark.unit
def test_web_source_never_imports_rag() -> None:
    """No web-source module imports garmin_mcp.rag beyond the grandfathered set."""
    src_root = Path(garmin_web.__file__).parent

    offenders: list[str] = []
    for py_file in src_root.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        for match in _RAG_IMPORT_RE.finditer(text):
            module = match.group(1)
            if module not in _ALLOWED_RAG_MODULES:
                rel = py_file.relative_to(src_root)
                offenders.append(f"{rel}: {module}")

    assert offenders == [], (
        "garmin_web must consume aggregation via GarminDBReader, not "
        "garmin_mcp.rag. Offending imports: " + "; ".join(offenders)
    )
