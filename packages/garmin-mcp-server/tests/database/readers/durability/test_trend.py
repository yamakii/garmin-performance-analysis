"""DurabilityReader trend: short-run filter, date axis, insufficient data, form worsening, build_trend / regress_form."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from garmin_mcp.database.readers.durability import (
    DurabilityReader,
)
from tests.database.readers.durability._helpers import (
    _durability_activity,
    _form_series,
    _insert_activity,
    _insert_time_series,
    _insert_time_series_with_form,
    _series,
)


@pytest.mark.integration
def test_durability_trend_filters_short_runs(reader_db_path: Path) -> None:
    """min_distance_km=15 keeps the 18km run and drops the 10km run."""
    reader = DurabilityReader(db_path=str(reader_db_path))

    # Short run (10km) - should be excluded.
    _insert_activity(
        reader_db_path,
        activity_id=6001,
        activity_date="2025-09-05",
        distance_km=10.0,
    )
    _insert_time_series(
        reader_db_path,
        activity_id=6001,
        rows=_series(front_hr=150.0, front_speed=3.0, back_hr=160.0, back_speed=3.0),
    )
    # Long run (18km) - should be included.
    _insert_activity(
        reader_db_path,
        activity_id=6002,
        activity_date="2025-09-06",
        distance_km=18.0,
    )
    _insert_time_series(
        reader_db_path,
        activity_id=6002,
        rows=_series(front_hr=150.0, front_speed=3.0, back_hr=158.0, back_speed=3.0),
    )

    result = reader.get_durability_trend(
        "2025-09-01", "2025-09-30", min_distance_km=15.0
    )

    activity_ids = [a["activity_id"] for a in result["activities"]]
    assert activity_ids == [6002]


@pytest.mark.integration
def test_durability_trend_uses_date_axis(reader_db_path: Path) -> None:
    """Decoupling falling over time -> direction='improving' (date x-axis).

    Activities are inserted in NON-monotonic id/insertion order to prove the
    regression uses elapsed days (not insertion/index order).
    """
    reader = DurabilityReader(db_path=str(reader_db_path))

    # decoupling decreases with later dates: 12% (Sep 1) -> 8% (Sep 15) ->
    # 4% (Oct 1) -> 1% (Oct 20). Insert in scrambled order.
    plan = [
        ("2025-10-01", 7003, 4.0),
        ("2025-09-01", 7001, 12.0),
        ("2025-10-20", 7004, 1.0),
        ("2025-09-15", 7002, 8.0),
    ]
    for activity_date, activity_id, decoupling_pct in plan:
        _insert_activity(
            reader_db_path,
            activity_id=activity_id,
            activity_date=activity_date,
            distance_km=20.0,
        )
        # back_hr chosen so (back/front - 1) == decoupling_pct/100 at speed 3.0.
        back_hr = 150.0 * (1.0 + decoupling_pct / 100.0)
        _insert_time_series(
            reader_db_path,
            activity_id=activity_id,
            rows=_series(
                front_hr=150.0, front_speed=3.0, back_hr=back_hr, back_speed=3.0
            ),
        )

    result = reader.get_durability_trend("2025-09-01", "2025-10-31")

    assert result["trend"]["data_points"] == 4
    # activities ordered by date ascending regardless of insertion order.
    dates = [a["activity_date"] for a in result["activities"]]
    assert dates == ["2025-09-01", "2025-09-15", "2025-10-01", "2025-10-20"]
    assert result["trend"]["decoupling_slope_per_day"] < 0
    assert result["trend"]["direction"] == "improving"


@pytest.mark.integration
def test_durability_trend_insufficient(reader_db_path: Path) -> None:
    """Fewer than 3 qualifying activities -> direction='insufficient_data'."""
    reader = DurabilityReader(db_path=str(reader_db_path))

    _insert_activity(
        reader_db_path,
        activity_id=8001,
        activity_date="2025-09-10",
        distance_km=18.0,
    )
    _insert_time_series(
        reader_db_path,
        activity_id=8001,
        rows=_series(front_hr=150.0, front_speed=3.0, back_hr=160.0, back_speed=3.0),
    )

    result = reader.get_durability_trend("2025-09-01", "2025-09-30")

    assert result["trend"]["data_points"] == 1
    assert result["trend"]["direction"] == "insufficient_data"
    assert result["trend"]["decoupling_slope_per_day"] == 0.0


@pytest.mark.integration
def test_durability_trend_form_worsening(reader_db_path: Path) -> None:
    """Rising GCT fade across 3 long runs -> form_direction='worsening'."""
    reader = DurabilityReader(db_path=str(reader_db_path))

    # GCT fade rises over time: 2% -> 6% -> 10%.
    plan = [
        ("2025-09-01", 7101, 250.0, 255.0),  # +2%
        ("2025-09-15", 7102, 250.0, 265.0),  # +6%
        ("2025-10-01", 7103, 250.0, 275.0),  # +10%
    ]
    for activity_date, activity_id, front_gct, back_gct in plan:
        _insert_activity(
            reader_db_path,
            activity_id=activity_id,
            activity_date=activity_date,
            distance_km=20.0,
        )
        _insert_time_series_with_form(
            reader_db_path,
            activity_id=activity_id,
            rows=_form_series(
                front_hr=150.0,
                front_speed=3.0,
                back_hr=156.0,
                back_speed=3.0,
                front_gct=front_gct,
                back_gct=back_gct,
            ),
        )

    result = reader.get_durability_trend("2025-09-01", "2025-10-31")

    assert result["trend"]["form_direction"] == "worsening"
    assert result["trend"]["gct_fade_slope_per_day"] is not None
    assert result["trend"]["gct_fade_slope_per_day"] > 0


@pytest.mark.integration
def test_durability_trend_form_insufficient(reader_db_path: Path) -> None:
    """Fewer than 3 activities with form data -> form_direction insufficient.

    Three qualifying long runs exist (so the decoupling trend is computed), but
    only two carry GCT data, so the form regression is insufficient (with only
    two points ``linregress`` returns ``p_value == nan``, which would bypass the
    significance gate).
    """
    reader = DurabilityReader(db_path=str(reader_db_path))

    # Two runs with form data.
    _insert_activity(
        reader_db_path,
        activity_id=7201,
        activity_date="2025-09-05",
        distance_km=18.0,
    )
    _insert_time_series_with_form(
        reader_db_path,
        activity_id=7201,
        rows=_form_series(
            front_hr=150.0,
            front_speed=3.0,
            back_hr=158.0,
            back_speed=3.0,
            front_gct=250.0,
            back_gct=260.0,
        ),
    )
    _insert_activity(
        reader_db_path,
        activity_id=7202,
        activity_date="2025-09-12",
        distance_km=18.5,
    )
    _insert_time_series_with_form(
        reader_db_path,
        activity_id=7202,
        rows=_form_series(
            front_hr=150.0,
            front_speed=3.0,
            back_hr=158.0,
            back_speed=3.0,
            front_gct=250.0,
            back_gct=265.0,
        ),
    )
    # Run WITHOUT form data (GCT null).
    _insert_activity(
        reader_db_path,
        activity_id=7203,
        activity_date="2025-09-20",
        distance_km=19.0,
    )
    _insert_time_series_with_form(
        reader_db_path,
        activity_id=7203,
        rows=_form_series(
            front_hr=150.0,
            front_speed=3.0,
            back_hr=159.0,
            back_speed=3.0,
            front_gct=None,
            back_gct=None,
        ),
    )

    result = reader.get_durability_trend("2025-09-01", "2025-09-30")

    # Decoupling trend is computed (3 qualifying runs)...
    assert result["trend"]["data_points"] == 3
    assert result["trend"]["direction"] != "insufficient_data"
    # ...but only two have form data -> form regression insufficient.
    assert result["trend"]["form_direction"] == "insufficient_data"
    assert result["trend"]["gct_fade_slope_per_day"] is None


@pytest.mark.unit
def test_build_trend_two_long_runs_insufficient_data(tmp_path: Path) -> None:
    """Two long runs must NOT classify: linregress p=nan bypasses the gate.

    With exactly 2 points scipy.stats.linregress returns ``p_value == nan``
    (df=0), and ``nan > 0.05`` is False, so the pre-fix code would confidently
    report a durability direction. The >=3 guard returns insufficient_data.
    """
    reader = DurabilityReader(db_path=str(tmp_path / "unit.duckdb"))

    activities = [
        _durability_activity("2025-09-01", 4.0),
        _durability_activity("2025-09-04", 6.0),  # 3 days later
    ]

    trend = reader._build_trend(activities)

    assert trend["direction"] == "insufficient_data"
    assert trend["decoupling_slope_per_day"] == 0.0
    assert trend["data_points"] == 2


@pytest.mark.unit
def test_build_trend_three_long_runs_classifies(tmp_path: Path) -> None:
    """Three long runs restore the significance gate with a finite slope."""
    reader = DurabilityReader(db_path=str(tmp_path / "unit.duckdb"))

    activities = [
        _durability_activity("2025-09-01", 4.0),  # day 0
        _durability_activity("2025-09-04", 5.0),  # day 3
        _durability_activity("2025-09-07", 6.0),  # day 6
    ]

    trend = reader._build_trend(activities)

    assert trend["data_points"] == 3
    assert trend["direction"] in {"stable", "worsening"}
    slope = trend["decoupling_slope_per_day"]
    assert slope is not None
    assert not math.isnan(slope)


@pytest.mark.unit
def test_regress_form_two_points_insufficient_data(tmp_path: Path) -> None:
    """Three runs but only two with GCT data -> form regression insufficient.

    Decoupling has 3 points (classified normally) while the GCT-fade regression
    sees only 2 non-null points; with 2 points ``linregress`` returns
    ``p_value == nan``, so the >=3 guard reports insufficient_data / None slope.
    """
    reader = DurabilityReader(db_path=str(tmp_path / "unit.duckdb"))

    activities = [
        _durability_activity("2025-09-01", 4.0, gct_fade_pct=2.0),  # day 0
        _durability_activity("2025-09-04", 5.0, gct_fade_pct=4.0),  # day 3
        _durability_activity("2025-09-07", 6.0, gct_fade_pct=None),  # day 6
    ]

    trend = reader._build_trend(activities)

    # Decoupling classified (3 points), form insufficient (only 2 points).
    assert trend["direction"] != "insufficient_data"
    assert trend["form_direction"] == "insufficient_data"
    assert trend["gct_fade_slope_per_day"] is None
