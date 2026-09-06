"""Throwaway CodeQL control experiment for #1013. DO NOT MERGE.

After migrating to advanced setup we excluded exactly one query. "Zero open
alerts" does not prove that worked: the pre-existing alerts were all dismissed,
so they would stay quiet whether the exclusion took effect or not. This file
introduces two fresh triggers so the two outcomes become distinguishable.

  POSITIVE control -> py/path-injection MUST still be reported.
      If it is silent, the config file disabled more than intended.

  NEGATIVE control -> py/clear-text-logging-sensitive-data must NOT be reported.
      If it fires, the query-filters block is not being applied.

Both shapes are copied from code CodeQL actually flagged in this repo before
#997 / #1013, so they are known-detectable rather than guesses.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

app = FastAPI()

_STATIC_ROOT = Path("/tmp/probe-static")


@app.get("/{full_path:path}", include_in_schema=False)
def probe_path_injection(full_path: str) -> FileResponse:
    """POSITIVE control: the pre-#997 spa_fallback shape, unguarded.

    `full_path` comes straight from the URL and reaches the filesystem with no
    containment check at all. CodeQL reported this shape as py/path-injection
    (alerts 7-9) before #997 added `_resolve_static_file`.
    """
    return FileResponse(_STATIC_ROOT / full_path)


def probe_clear_text_logging(body_mass_kg: float, weight_kg: float) -> None:
    """NEGATIVE control: the backfill_body_mass / sync-outcome shape.

    Printing a dict whose keys are named after body mass and weight is what
    py/clear-text-logging-sensitive-data flagged (alerts 1, 2, 6). With the
    exclusion in .github/codeql/codeql-config.yml this must produce nothing.
    """
    print(json.dumps({"body_mass_kg": body_mass_kg, "weight_kg": weight_kg}))
