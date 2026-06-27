"""Integration tests for TrainingLoadReader (distance-based ACWR).

Each test builds a tmp DuckDB (schema via the ``reader_db_path`` fixture) and
inserts running activities, then asserts the ACWR / load-trend output. The load
metric is distance only, so these never depend on ``avg_heart_rate``.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.readers.training_load import TrainingLoadReader

# A fixed reference day so windows are deterministic across runs.
END_DATE = "2025-10-28"


def _insert_activity(
    db_path: Path,
    *,
    activity_id: int,
    activity_date: str,
    distance_km: float,
    avg_heart_rate: int | None = 150,
) -> None:
    """Insert one running activity with a given distance (HR optional)."""
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
                avg_heart_rate,
            ],
        )
    finally:
        conn.close()


def _seed_even_load(db_path: Path, *, daily_km: float, days: int = 28) -> None:
    """Insert one activity per day for ``days`` days ending on END_DATE.

    With equal daily load, acute (7d) and chronic-weekly (28d/4) are equal, so
    ACWR == 1.0 (optimal).
    """
    from datetime import datetime, timedelta

    end = datetime.strptime(END_DATE, "%Y-%m-%d").date()
    for i in range(days):
        day = (end - timedelta(days=i)).strftime("%Y-%m-%d")
        _insert_activity(
            db_path,
            activity_id=1000 + i,
            activity_date=day,
            distance_km=daily_km,
        )


@pytest.mark.integration
def test_acwr_optimal_range(reader_db_path: Path) -> None:
    """Even daily distance over 28 days -> acwr ~= 1.0, status=optimal."""
    _seed_even_load(reader_db_path, daily_km=10.0, days=28)

    result = TrainingLoadReader(db_path=str(reader_db_path)).get_acwr(end_date=END_DATE)

    assert result["load_metric"] == "distance_km"
    assert result["end_date"] == END_DATE
    # acute = 7 * 10 = 70; chronic weekly = (28 * 10) / 4 = 70 -> acwr 1.0
    assert result["acute_load_7d"] == 70.0
    assert result["chronic_load_28d_weekly"] == 70.0
    assert result["acwr"] == pytest.approx(1.0)
    assert result["status"] == "optimal"


@pytest.mark.integration
def test_acwr_high_risk_spike(reader_db_path: Path) -> None:
    """A big recent spike on a small chronic base -> acwr>1.5, high_risk."""
    from datetime import datetime, timedelta

    end = datetime.strptime(END_DATE, "%Y-%m-%d").date()
    # Small chronic base: 2 km on each of days 8-28 (outside the acute window).
    for i in range(7, 28):
        day = (end - timedelta(days=i)).strftime("%Y-%m-%d")
        _insert_activity(
            reader_db_path,
            activity_id=2000 + i,
            activity_date=day,
            distance_km=2.0,
        )
    # Large acute load: 20 km on each of the last 7 days.
    for i in range(7):
        day = (end - timedelta(days=i)).strftime("%Y-%m-%d")
        _insert_activity(
            reader_db_path,
            activity_id=2100 + i,
            activity_date=day,
            distance_km=20.0,
        )

    result = TrainingLoadReader(db_path=str(reader_db_path)).get_acwr(end_date=END_DATE)

    # acute = 7 * 20 = 140; chronic total = 140 + (21 * 2) = 182; weekly = 45.5
    assert result["acute_load_7d"] == 140.0
    assert result["acwr"] is not None
    assert result["acwr"] > 1.5
    assert result["status"] == "high_risk"


@pytest.mark.integration
def test_acwr_insufficient_data(reader_db_path: Path) -> None:
    """No activities -> chronic 0, acwr None, status=insufficient_data."""
    result = TrainingLoadReader(db_path=str(reader_db_path)).get_acwr(end_date=END_DATE)

    assert result["chronic_load_28d_weekly"] == 0.0
    assert result["acwr"] is None
    assert result["status"] == "insufficient_data"
    assert result["load_metric"] == "distance_km"


@pytest.mark.integration
def test_acwr_distance_only_no_hr_dependency(reader_db_path: Path) -> None:
    """Activities with NULL avg_heart_rate still yield a distance-based ACWR."""
    _seed_even_load(reader_db_path, daily_km=8.0, days=28)
    # Overwrite the HR-bearing rows with NULL HR rows on the same days.
    from datetime import datetime, timedelta

    conn = duckdb.connect(str(reader_db_path))
    try:
        conn.execute("DELETE FROM activities")
    finally:
        conn.close()
    end = datetime.strptime(END_DATE, "%Y-%m-%d").date()
    for i in range(28):
        day = (end - timedelta(days=i)).strftime("%Y-%m-%d")
        _insert_activity(
            reader_db_path,
            activity_id=3000 + i,
            activity_date=day,
            distance_km=8.0,
            avg_heart_rate=None,
        )

    result = TrainingLoadReader(db_path=str(reader_db_path)).get_acwr(end_date=END_DATE)

    # Computed purely from distance; no exception despite NULL HR.
    assert result["acwr"] == pytest.approx(1.0)
    assert result["status"] == "optimal"
    assert result["acute_load_7d"] == 56.0


@pytest.mark.integration
def test_get_load_trend_weekly_buckets(reader_db_path: Path) -> None:
    """12-week trend yields 12 contiguous calendar-week buckets (Monday-aligned).

    The newest bucket is a partial week (its Monday through END_DATE); the older
    buckets are full 7-day weeks.
    """
    from datetime import datetime, timedelta

    # Seed even 5 km/day load over the whole lookback span so each bucket is
    # populated. 12 calendar weeks span more than 12 * 7 days once partial weeks
    # are involved, so seed a generous window.
    end = datetime.strptime(END_DATE, "%Y-%m-%d").date()
    for i in range(13 * 7):
        day = (end - timedelta(days=i)).strftime("%Y-%m-%d")
        _insert_activity(
            reader_db_path,
            activity_id=4000 + i,
            activity_date=day,
            distance_km=5.0,
        )

    result = TrainingLoadReader(db_path=str(reader_db_path)).get_load_trend(
        lookback_weeks=12, end_date=END_DATE
    )

    weeks = result["weeks"]
    assert result["load_metric"] == "distance_km"
    assert len(weeks) == 12

    # Buckets are contiguous, chronological and aligned to Monday (start_day=0).
    starts = [datetime.strptime(w["week_start"], "%Y-%m-%d").date() for w in weeks]
    for prev, nxt in zip(starts, starts[1:], strict=False):
        assert (nxt - prev) == timedelta(days=7)
    for s in starts:
        assert s.weekday() == 0  # Monday

    # Full (older) weeks carry a complete 7-day load; the newest is partial.
    for w in weeks[:-1]:
        assert w["load_km"] == 35.0  # 7 days * 5 km
        assert w["acwr"] is not None
    # END_DATE 2025-10-28 is a Tuesday -> newest bucket = Mon 10-27 .. Tue 10-28.
    assert weeks[-1]["week_start"] == "2025-10-27"
    assert weeks[-1]["load_km"] == 10.0  # 2 days * 5 km (partial week)


@pytest.mark.integration
def test_load_trend_weeks_align_to_monday(reader_db_path: Path) -> None:
    """With the default config (no profile row) every week_start is a Monday."""
    from datetime import datetime, timedelta

    end_date = "2026-06-24"  # a Wednesday
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    for i in range(12 * 7):
        day = (end - timedelta(days=i)).strftime("%Y-%m-%d")
        _insert_activity(
            reader_db_path,
            activity_id=5000 + i,
            activity_date=day,
            distance_km=5.0,
        )

    result = TrainingLoadReader(db_path=str(reader_db_path)).get_load_trend(
        lookback_weeks=12, end_date=end_date
    )

    weeks = result["weeks"]
    assert len(weeks) == 12
    for w in weeks:
        ws = datetime.strptime(w["week_start"], "%Y-%m-%d").date()
        assert ws.weekday() == 0  # Monday


@pytest.mark.integration
def test_load_trend_weeks_align_to_configured_day(reader_db_path: Path) -> None:
    """With week_start_day=6 (Sunday) every week_start is a Sunday."""
    from datetime import datetime, timedelta

    # Configure Sunday-start weeks.
    conn = duckdb.connect(str(reader_db_path))
    try:
        conn.execute(
            "INSERT INTO athlete_profile (user_id, week_start_day) VALUES (?, ?)",
            ["default", 6],
        )
    finally:
        conn.close()

    end_date = "2026-06-24"  # a Wednesday
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    for i in range(12 * 7):
        day = (end - timedelta(days=i)).strftime("%Y-%m-%d")
        _insert_activity(
            reader_db_path,
            activity_id=6000 + i,
            activity_date=day,
            distance_km=5.0,
        )

    result = TrainingLoadReader(db_path=str(reader_db_path)).get_load_trend(
        lookback_weeks=12, end_date=end_date
    )

    weeks = result["weeks"]
    assert len(weeks) == 12
    for w in weeks:
        ws = datetime.strptime(w["week_start"], "%Y-%m-%d").date()
        assert ws.weekday() == 6  # Sunday
    # Sunday on/before Wed 2026-06-24 is 2026-06-21.
    assert weeks[-1]["week_start"] == "2026-06-21"


@pytest.mark.integration
def test_load_trend_latest_bucket_is_partial_week(reader_db_path: Path) -> None:
    """The newest bucket aggregates only week-start day .. end_date (partial)."""
    from datetime import datetime, timedelta

    end_date = "2026-06-24"  # Wednesday -> Monday-week starts 2026-06-22
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    # Seed 5 km/day across the partial week (Mon 06-22 .. Wed 06-24) and earlier.
    for i in range(12 * 7):
        day = (end - timedelta(days=i)).strftime("%Y-%m-%d")
        _insert_activity(
            reader_db_path,
            activity_id=7000 + i,
            activity_date=day,
            distance_km=5.0,
        )

    result = TrainingLoadReader(db_path=str(reader_db_path)).get_load_trend(
        lookback_weeks=12, end_date=end_date
    )

    newest = result["weeks"][-1]
    assert newest["week_start"] == "2026-06-22"  # Monday
    # Mon/Tue/Wed = 3 days * 5 km = 15 km (partial week, not a full 35 km).
    assert newest["load_km"] == 15.0


@pytest.mark.unit
def test_acwr_unchanged_rolling(mocker) -> None:
    """get_acwr stays rolling: acute = last 7 days, chronic = last 28 days / 4.

    It must be independent of calendar-week bucketing (no week_start_day read).
    """
    from datetime import date, timedelta

    reader = TrainingLoadReader.__new__(TrainingLoadReader)
    reader.db_path = mocker.MagicMock()

    end = date(2026, 6, 24)
    daily: dict[date, float] = {}
    for i in range(7):  # last 7 days: 10 km each -> acute 70
        daily[end - timedelta(days=i)] = 10.0
    for i in range(7, 28):  # days 8-28: 5 km each
        daily[end - timedelta(days=i)] = 5.0
    mocker.patch.object(reader, "_daily_loads", return_value=daily)

    result = reader.get_acwr(end_date="2026-06-24")

    # acute = 7 * 10 = 70; chronic total = 70 + 21 * 5 = 175; weekly = 43.75
    assert result["acute_load_7d"] == 70.0
    assert result["chronic_load_28d_weekly"] == pytest.approx(43.75)
    assert result["acwr"] == pytest.approx(1.6)
    assert result["status"] == "high_risk"
