"""DurabilityReader ranking: best / worst by decoupling, tie-break, serialisability."""

from __future__ import annotations

from pathlib import Path

import pytest

from garmin_mcp.database.readers.durability import (
    DurabilityReader,
)
from tests.database.readers.durability._helpers import _ranking_activity


@pytest.mark.unit
def test_durability_ranking_best_worst_by_decoupling(tmp_path: Path) -> None:
    """Ranking is by decoupling (lower=better), NOT by pace_fade.

    The -0.39 decoupling run has a MORE negative pace_fade (-4.93) than the
    -6.8 run, but pace_fade is not a ranking axis, so the -6.8 run is best.
    """
    reader = DurabilityReader(db_path=str(tmp_path / "unit.duckdb"))

    activities = [
        _ranking_activity(
            activity_id=1,
            activity_date="2025-06-05",
            decoupling_pct=-6.8,
            pace_fade_pct=-8.13,
        ),
        _ranking_activity(
            activity_id=2,
            activity_date="2025-06-21",
            decoupling_pct=-0.39,
            pace_fade_pct=-4.93,
        ),
        _ranking_activity(
            activity_id=3,
            activity_date="2025-06-28",
            decoupling_pct=0.68,
            pace_fade_pct=-0.04,
        ),
    ]

    ranking = reader._build_durability_ranking(activities)

    assert ranking["best_run"]["decoupling_pct"] == -6.8
    assert ranking["best_run"]["activity_id"] == 1
    assert ranking["worst_run"]["decoupling_pct"] == 0.68
    assert ranking["worst_run"]["activity_id"] == 3


@pytest.mark.unit
def test_durability_ranking_present_when_insufficient_data(tmp_path: Path) -> None:
    """Ranking is computed even when the regression gate reports insufficient.

    Two long runs: the trend regression is ``insufficient_data`` (<3 points),
    but the descriptive ranking still resolves best/worst.
    """
    reader = DurabilityReader(db_path=str(tmp_path / "unit.duckdb"))

    activities = [
        _ranking_activity(
            activity_id=10,
            activity_date="2025-06-05",
            decoupling_pct=4.0,
            pace_fade_pct=-1.0,
        ),
        _ranking_activity(
            activity_id=11,
            activity_date="2025-06-12",
            decoupling_pct=6.0,
            pace_fade_pct=-2.0,
        ),
    ]

    trend = reader._build_trend(activities)
    trend.update(reader._build_durability_ranking(activities))

    assert trend["direction"] == "insufficient_data"
    assert trend["best_run"]["decoupling_pct"] == 4.0
    assert trend["worst_run"]["decoupling_pct"] == 6.0


@pytest.mark.unit
def test_durability_ranking_single_activity_null(tmp_path: Path) -> None:
    """A single activity cannot be ranked -> best/worst None, labels present."""
    reader = DurabilityReader(db_path=str(tmp_path / "unit.duckdb"))

    activities = [
        _ranking_activity(
            activity_id=20,
            activity_date="2025-06-05",
            decoupling_pct=2.0,
            pace_fade_pct=-1.0,
        ),
    ]

    ranking = reader._build_durability_ranking(activities)

    assert ranking["best_run"] is None
    assert ranking["worst_run"] is None
    assert "metric_directions" in ranking


@pytest.mark.unit
def test_durability_metric_directions_labels(tmp_path: Path) -> None:
    """metric_directions carries the sign-convention labels for both metrics."""
    reader = DurabilityReader(db_path=str(tmp_path / "unit.duckdb"))

    ranking = reader._build_durability_ranking([])

    assert ranking["metric_directions"]["decoupling_pct"] == "lower_is_better"
    assert (
        ranking["metric_directions"]["pace_fade_pct"]
        == "descriptor_negative_means_faster_second_half"
    )


@pytest.mark.unit
def test_durability_ranking_tie_break_deterministic(tmp_path: Path) -> None:
    """Equal decoupling -> tie-break by (decoupling, activity_date, activity_id).

    Two runs share decoupling 2.0; the earlier date wins the best slot.
    """
    reader = DurabilityReader(db_path=str(tmp_path / "unit.duckdb"))

    activities = [
        _ranking_activity(
            activity_id=31,
            activity_date="2025-06-12",
            decoupling_pct=2.0,
            pace_fade_pct=-1.0,
        ),
        _ranking_activity(
            activity_id=30,
            activity_date="2025-06-05",
            decoupling_pct=2.0,
            pace_fade_pct=-3.0,
        ),
        _ranking_activity(
            activity_id=32,
            activity_date="2025-06-20",
            decoupling_pct=5.0,
            pace_fade_pct=0.0,
        ),
    ]

    ranking = reader._build_durability_ranking(activities)

    # Earliest date among the tied decoupling=2.0 runs is best.
    assert ranking["best_run"]["activity_id"] == 30
    assert ranking["best_run"]["activity_date"] == "2025-06-05"
    assert ranking["worst_run"]["activity_id"] == 32


@pytest.mark.unit
def test_durability_ranking_json_serializable(tmp_path: Path) -> None:
    """The trend dict (with ranking merged) survives the MCP JSON boundary."""
    import json

    reader = DurabilityReader(db_path=str(tmp_path / "unit.duckdb"))

    activities = [
        _ranking_activity(
            activity_id=40,
            activity_date="2025-06-05",
            decoupling_pct=-6.8,
            pace_fade_pct=-8.13,
        ),
        _ranking_activity(
            activity_id=41,
            activity_date="2025-06-12",
            decoupling_pct=-1.51,
            pace_fade_pct=-2.74,
        ),
        _ranking_activity(
            activity_id=42,
            activity_date="2025-06-28",
            decoupling_pct=0.68,
            pace_fade_pct=-0.04,
        ),
    ]

    trend = reader._build_trend(activities)
    trend.update(reader._build_durability_ranking(activities))
    result = {"activities": activities, "trend": trend}

    encoded = json.dumps(result, default=str)

    assert '"best_run"' in encoded
    assert '"metric_directions"' in encoded
