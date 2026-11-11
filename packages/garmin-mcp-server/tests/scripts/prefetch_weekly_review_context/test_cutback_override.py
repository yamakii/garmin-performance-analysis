"""Proven-distance exemption and the owner override in the weekly bundle (#1568)."""

from __future__ import annotations

from pathlib import Path

import pytest

from garmin_mcp.database.inserters.plan import insert_training_blocks
from garmin_mcp.scripts.prefetch_weekly_review_context import (
    prefetch_weekly_review_context,
)
from tests.scripts.prefetch_weekly_review_context._helpers import (
    _mock_prefetch,
    _weeks,
)


@pytest.mark.unit
def test_override_on_step_sets_flag() -> None:
    """W's ladder step override ships as the bundle's cutback_override."""
    override = {"reason": "r", "decided_on": "2026-11-12"}
    ladder_step = {
        "current": {
            "week_start": "2026-07-06",
            "target_km": 22.0,
            "cutback_override": override,
        },
        "previous": None,
        "next": None,
    }

    with _mock_prefetch(ladder_step=ladder_step):
        result = prefetch_weekly_review_context("this", today="2026-07-10")

    assert result["cutback_override"]["reason"] == "r"
    assert result["cutback_override"]["decided_on"] == "2026-11-12"


@pytest.mark.unit
def test_override_absent_is_null() -> None:
    """A step without an override (or no step at all) -> null."""
    with _mock_prefetch():
        result = prefetch_weekly_review_context("this", today="2026-07-10")

    assert result["cutback_override"] is None


@pytest.mark.unit
def test_invalid_override_rejected_on_save(initialized_db_path: Path) -> None:
    """An override with an empty reason is rejected before anything is written."""
    block = {
        "phase": "build",
        "title": "復帰ラダー",
        "start_date": "2026-11-02",
        "end_date": "2026-11-29",
        "long_run_ladder": [
            {
                "week_start": "2026-11-09",
                "target_minutes": 100,
                "cutback_override": {"reason": ""},
            }
        ],
    }

    with pytest.raises(ValueError, match="cutback_override.reason"):
        insert_training_blocks([block], db_path=str(initialized_db_path))


@pytest.mark.unit
def test_long_run_gate_exempts_steps_inside_proven_run() -> None:
    """A return ladder inside the proven run does not trigger a cutback."""
    week_starts = ["2026-06-08", "2026-06-15", "2026-06-22", "2026-06-29"]
    proven = {"duration_sec": 6000, "distance_km": 14.0, "activity_date": "2026-03-01"}
    with _mock_prefetch() as reader:
        reader.get_load_trend.return_value = _weeks(
            list(zip(week_starts, [3600, 4000, 4400, 4900], strict=True))
        )
        reader.get_proven_long_run.return_value = proven
        result = prefetch_weekly_review_context("this", today="2026-07-10")

    long_run = result["load_trend"]["long_run"]
    assert long_run["long_run_build_weeks"] == 0
    assert long_run["cutback_due_long_run"] is False
    assert long_run["proven_exempt_weeks"] == 3
    assert long_run["proven_long_run"] == proven
    # Measured before the plain streak's first counted week.
    assert reader.get_proven_long_run.call_args.args == ("2026-06-15",)
