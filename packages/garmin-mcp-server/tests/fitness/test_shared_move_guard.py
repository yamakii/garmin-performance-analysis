"""Guard test: shared code was moved out of training_plan/ (#783).

Ensures no source file still imports the relocated shared modules
(vdot / fitness_assessor / garmin_calendar) or the relocated model
classes (PaceZones / HRZones / FitnessSummary) from
``garmin_mcp.training_plan.*``. These now live in ``garmin_mcp.fitness.*``
and no re-export shim is kept (no-shims principle).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "garmin_mcp"

# Relocated modules: any import of these under training_plan is forbidden.
FORBIDDEN_MODULE_PATTERNS = [
    re.compile(r"from\s+garmin_mcp\.training_plan\.vdot\s+import"),
    re.compile(r"from\s+garmin_mcp\.training_plan\.fitness_assessor\s+import"),
    re.compile(r"from\s+garmin_mcp\.training_plan\.garmin_calendar\s+import"),
    re.compile(r"import\s+garmin_mcp\.training_plan\.vdot\b"),
    re.compile(r"import\s+garmin_mcp\.training_plan\.fitness_assessor\b"),
    re.compile(r"import\s+garmin_mcp\.training_plan\.garmin_calendar\b"),
]

# Relocated model classes: forbidden when imported from training_plan.models.
RELOCATED_MODEL_CLASSES = ("PaceZones", "HRZones", "FitnessSummary")
_MODELS_IMPORT = re.compile(
    r"from\s+garmin_mcp\.training_plan\.models\s+import\s+\(?([^)]*?)\)?\s*$",
    re.MULTILINE | re.DOTALL,
)


@pytest.mark.unit
def test_no_training_plan_import_of_shared_left() -> None:
    """No src file imports the relocated shared code from training_plan.*."""
    offenders: list[str] = []
    for py_file in SRC_ROOT.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")

        for pattern in FORBIDDEN_MODULE_PATTERNS:
            if pattern.search(text):
                offenders.append(f"{py_file}: {pattern.pattern}")

        for match in _MODELS_IMPORT.finditer(text):
            imported = match.group(1)
            for cls in RELOCATED_MODEL_CLASSES:
                if re.search(rf"\b{cls}\b", imported):
                    offenders.append(f"{py_file}: training_plan.models import {cls}")

    assert (
        not offenders
    ), "Relocated shared code still imported from training_plan:\n" + "\n".join(
        offenders
    )
