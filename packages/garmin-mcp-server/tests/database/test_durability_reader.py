"""Integration tests for DurabilityReader (long-run cardiac decoupling).

Each test builds a tmp DuckDB (schema via the ``reader_db_path`` fixture) and
inserts an activity row plus a synthetic ``time_series_metrics`` series whose
first/second halves differ, then asserts decoupling / trend output. No real
data is used.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.readers.durability import DurabilityReader


def _insert_activity(
    db_path: Path,
    *,
    activity_id: int,
    activity_date: str,
    distance_km: float,
) -> None:
    """Insert one running activity row with a given distance."""
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO activities (
                activity_id, activity_date, total_distance_km,
                total_time_seconds, avg_pace_seconds_per_km, avg_heart_rate
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                activity_id,
                activity_date,
                distance_km,
                int(distance_km * 300),
                300.0,
                150,
            ],
        )
    finally:
        conn.close()


def _insert_time_series(
    db_path: Path,
    *,
    activity_id: int,
    rows: list[tuple[int, float | None, float | None]],
) -> None:
    """Insert ``(timestamp_s, heart_rate, speed)`` rows for an activity.

    ``seq_no`` is assigned sequentially (PK is activity_id + seq_no).
    """
    conn = duckdb.connect(str(db_path))
    try:
        for seq_no, (timestamp_s, heart_rate, speed) in enumerate(rows):
            conn.execute(
                """
                INSERT INTO time_series_metrics (
                    activity_id, seq_no, timestamp_s, heart_rate, speed
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [activity_id, seq_no, timestamp_s, heart_rate, speed],
            )
    finally:
        conn.close()


def _series(
    *,
    front_hr: float,
    front_speed: float,
    back_hr: float,
    back_speed: float,
    points_per_half: int = 5,
) -> list[tuple[int, float | None, float | None]]:
    """Build a time series with constant first/second-half HR and speed.

    Timestamps 0..(2*points_per_half-1). The first ``points_per_half`` samples
    fall strictly below the midpoint; the rest fall at/above it.
    """
    rows: list[tuple[int, float | None, float | None]] = []
    total = 2 * points_per_half
    for ts in range(total):
        if ts < points_per_half:
            rows.append((ts, front_hr, front_speed))
        else:
            rows.append((ts, back_hr, back_speed))
    return rows


@pytest.mark.integration
def test_activity_durability_basic(reader_db_path: Path) -> None:
    """Second-half HR rises at constant speed -> decoupling_pct > 0."""
    _insert_activity(
        reader_db_path,
        activity_id=5001,
        activity_date="2025-09-01",
        distance_km=18.0,
    )
    # Front: 150 bpm @ 3.0 m/s; back: 165 bpm @ 3.0 m/s (HR cost up 10%).
    _insert_time_series(
        reader_db_path,
        activity_id=5001,
        rows=_series(front_hr=150.0, front_speed=3.0, back_hr=165.0, back_speed=3.0),
    )

    result = DurabilityReader(db_path=str(reader_db_path)).get_activity_durability(5001)

    assert result is not None
    assert set(result) == {
        "activity_id",
        "activity_date",
        "distance_km",
        "decoupling_pct",
        "pace_fade_pct",
    }
    assert result["activity_id"] == 5001
    assert result["activity_date"] == "2025-09-01"
    assert result["distance_km"] == pytest.approx(18.0)
    # (165/3.0)/(150/3.0) - 1 = 0.10 -> 10%
    assert result["decoupling_pct"] == pytest.approx(10.0)
    # Speed constant -> no pace fade.
    assert result["pace_fade_pct"] == pytest.approx(0.0)


@pytest.mark.integration
def test_activity_durability_missing_hr_returns_none(reader_db_path: Path) -> None:
    """All heart_rate values NULL -> no decoupling, returns None."""
    _insert_activity(
        reader_db_path,
        activity_id=5002,
        activity_date="2025-09-02",
        distance_km=20.0,
    )
    _insert_time_series(
        reader_db_path,
        activity_id=5002,
        rows=[(ts, None, 3.0) for ts in range(10)],
    )

    result = DurabilityReader(db_path=str(reader_db_path)).get_activity_durability(5002)

    assert result is None


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
    """Fewer than 2 qualifying activities -> direction='insufficient_data'."""
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
