"""DurabilityReader trend qualifiers (#845): absolute assessment, fragility, direction caveat, backward-compatible keys."""

from __future__ import annotations

from pathlib import Path

import pytest

from garmin_mcp.database.readers.durability import (
    _P_VALUE_THRESHOLD,
    DurabilityReader,
)
from tests.database.readers.durability._helpers import _WINDOW_845, _fragility_activity


@pytest.mark.unit
def test_absolute_assessment_all_strong_band(tmp_path: Path) -> None:
    """Every run <5% -> band=strong, all_within_strong_band, recent = last run."""
    reader = DurabilityReader(db_path=str(tmp_path / "unit.duckdb"))

    trend = reader._build_trend(_WINDOW_845)

    aa = trend["absolute_assessment"]
    assert aa["band"] == "strong"
    assert aa["all_within_strong_band"] is True
    assert aa["recent_decoupling_pct"] == 0.39  # most recent (last) run
    # median of [-6.8, -1.51, -0.39, 0.68, 0.39] = -0.39
    assert aa["window_median_decoupling_pct"] == -0.39


@pytest.mark.unit
def test_absolute_assessment_poor_band(tmp_path: Path) -> None:
    """Median >=10% -> band=poor, not all within strong band."""
    reader = DurabilityReader(db_path=str(tmp_path / "unit.duckdb"))

    activities = [
        _fragility_activity(
            activity_id=1, activity_date="2025-09-01", decoupling_pct=8.0
        ),
        _fragility_activity(
            activity_id=2, activity_date="2025-09-08", decoupling_pct=12.0
        ),
        _fragility_activity(
            activity_id=3, activity_date="2025-09-15", decoupling_pct=14.0
        ),
    ]

    trend = reader._build_trend(activities)

    aa = trend["absolute_assessment"]
    assert aa["band"] == "poor"  # median 12.0
    assert aa["all_within_strong_band"] is False


@pytest.mark.unit
def test_absolute_assessment_present_when_insufficient_data(tmp_path: Path) -> None:
    """<3 runs still carry an absolute_assessment; fragile stays False."""
    reader = DurabilityReader(db_path=str(tmp_path / "unit.duckdb"))

    activities = [
        _fragility_activity(
            activity_id=1, activity_date="2025-09-01", decoupling_pct=3.0
        ),
        _fragility_activity(
            activity_id=2, activity_date="2025-09-08", decoupling_pct=4.0
        ),
    ]

    trend = reader._build_trend(activities)

    assert trend["direction"] == "insufficient_data"
    assert trend["absolute_assessment"]["band"] == "strong"
    assert trend["fragile"] is False
    assert trend["direction_caveat"] is None


@pytest.mark.unit
def test_fragility_single_leverage_point(tmp_path: Path) -> None:
    """The #845 window is worsening but fragile, leaning on the 6/05 outlier.

    Full slope is significant (p=0.049) yet removing any single run drops it
    below significance; the reported leverage point is the most slope-influential
    run (6/05, -6.8%), not merely the largest resulting p-value.
    """
    reader = DurabilityReader(db_path=str(tmp_path / "unit.duckdb"))

    trend = reader._build_trend(_WINDOW_845)

    assert trend["direction"] == "worsening"
    assert trend["fragile"] is True
    reason = trend["fragile_reason"]
    assert reason["leverage_point"]["activity_date"] == "2026-06-05"
    assert reason["leverage_point"]["activity_id"] == 1
    assert reason["direction_without_leverage_point"] == "stable"
    assert reason["p_without_leverage_point"] > _P_VALUE_THRESHOLD
    # Every single removal flips this borderline trend.
    assert reason["single_removals_that_flip"] == 5
    assert reason["n_points"] == 5


@pytest.mark.unit
def test_fragility_robust_worsening_not_fragile(tmp_path: Path) -> None:
    """A strong monotone worsening survives every single-point removal."""
    reader = DurabilityReader(db_path=str(tmp_path / "unit.duckdb"))

    # Equally spaced, tightly linear, clearly rising decoupling -> robust.
    activities = [
        _fragility_activity(
            activity_id=i,
            activity_date=d,
            decoupling_pct=v,
        )
        for i, (d, v) in enumerate(
            [
                ("2025-09-01", 1.0),
                ("2025-09-08", 3.0),
                ("2025-09-15", 5.0),
                ("2025-09-22", 7.0),
                ("2025-09-29", 9.0),
            ],
            start=1,
        )
    ]

    trend = reader._build_trend(activities)

    assert trend["direction"] == "worsening"
    assert trend["fragile"] is False
    assert trend["fragile_reason"] is None


@pytest.mark.unit
def test_fragility_three_points_significant_flags_note(tmp_path: Path) -> None:
    """A significant 3-point trend is fragile with a not-gate-testable note."""
    reader = DurabilityReader(db_path=str(tmp_path / "unit.duckdb"))

    # Perfectly linear 3 points -> p is tiny (significant) -> worsening.
    activities = [
        _fragility_activity(
            activity_id=1, activity_date="2025-09-01", decoupling_pct=2.0
        ),
        _fragility_activity(
            activity_id=2, activity_date="2025-09-08", decoupling_pct=6.0
        ),
        _fragility_activity(
            activity_id=3, activity_date="2025-09-15", decoupling_pct=10.0
        ),
    ]

    trend = reader._build_trend(activities)

    assert trend["direction"] == "worsening"
    assert trend["fragile"] is True
    assert trend["fragile_reason"]["leverage_point"] is None
    assert "only 3 long runs" in trend["fragile_reason"]["note"]


@pytest.mark.unit
def test_direction_caveat_worsening_strong_and_fragile(tmp_path: Path) -> None:
    """Caveat names both the strong absolute band and the fragility."""
    reader = DurabilityReader(db_path=str(tmp_path / "unit.duckdb"))

    caveat = reader._build_trend(_WINDOW_845)["direction_caveat"]

    assert caveat is not None
    assert "strong band" in caveat
    assert "fragile" in caveat
    # Maximally fragile phrasing + the leaning-on date.
    assert "any single long run" in caveat
    assert "2026-06-05" in caveat


@pytest.mark.unit
def test_direction_caveat_none_when_stable(tmp_path: Path) -> None:
    """A non-significant (stable) direction produces no caveat and no fragility."""
    reader = DurabilityReader(db_path=str(tmp_path / "unit.duckdb"))

    # Noisy / flat -> not significant.
    activities = [
        _fragility_activity(
            activity_id=1, activity_date="2025-09-01", decoupling_pct=3.0
        ),
        _fragility_activity(
            activity_id=2, activity_date="2025-09-08", decoupling_pct=2.5
        ),
        _fragility_activity(
            activity_id=3, activity_date="2025-09-15", decoupling_pct=3.2
        ),
        _fragility_activity(
            activity_id=4, activity_date="2025-09-22", decoupling_pct=2.8
        ),
    ]

    trend = reader._build_trend(activities)

    assert trend["direction"] == "stable"
    assert trend["fragile"] is False
    assert trend["direction_caveat"] is None


@pytest.mark.unit
def test_build_trend_backward_compat_keys(tmp_path: Path) -> None:
    """Existing trend keys are unchanged alongside the new #845 fields."""
    reader = DurabilityReader(db_path=str(tmp_path / "unit.duckdb"))

    trend = reader._build_trend(_WINDOW_845)

    for key in (
        "decoupling_slope_per_day",
        "data_points",
        "direction",
        "gct_fade_slope_per_day",
        "form_direction",
    ):
        assert key in trend
    assert trend["data_points"] == 5
