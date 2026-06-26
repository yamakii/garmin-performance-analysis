"""Unit tests for garmin_web.queries.trends."""

import pytest

from garmin_web.queries.trends import (
    get_efficiency_trend,
    get_form_trend,
    get_heat_adjusted_trend,
    get_physiology_trend,
    get_volume_trend,
)

_INSERT_ACTIVITY = "INSERT INTO activities VALUES (?, ?, ?, ?, ?, ?, ?)"


@pytest.mark.unit
def test_volume_weekly_buckets(trends_conn):
    """2025-10-06 (Mon) and 10-09 share ISO week W41; 10-13 starts W42."""
    trends_conn.executemany(
        _INSERT_ACTIVITY,
        [
            (9000001101, "2025-10-06", "Run A", 10.0, 3600, 360.0, 140),
            (9000001102, "2025-10-09", "Run B", 5.0, 1800, 360.0, 145),
            (9000001103, "2025-10-13", "Run C", 8.0, 2400, 300.0, 150),
        ],
    )

    result = get_volume_trend(trends_conn, granularity="week")

    assert [bucket["bucket"] for bucket in result] == ["2025-W41", "2025-W42"]
    w41 = result[0]
    assert w41["distance_km"] == pytest.approx(15.0)
    assert w41["duration_seconds"] == 5400
    assert w41["run_count"] == 2
    w42 = result[1]
    assert w42["distance_km"] == pytest.approx(8.0)
    assert w42["run_count"] == 1


@pytest.mark.unit
def test_volume_monthly_buckets(trends_conn):
    trends_conn.executemany(
        _INSERT_ACTIVITY,
        [
            (9000001111, "2025-10-06", "Run A", 10.0, 3600, 360.0, 140),
            (9000001112, "2025-10-20", "Run B", 5.0, 1800, 360.0, 145),
            (9000001113, "2025-11-03", "Run C", 8.0, 2400, 300.0, 150),
        ],
    )

    result = get_volume_trend(trends_conn, granularity="month")

    assert [bucket["bucket"] for bucket in result] == ["2025-10", "2025-11"]
    assert result[0]["distance_km"] == pytest.approx(15.0)
    assert result[0]["run_count"] == 2
    assert result[1]["run_count"] == 1


@pytest.mark.unit
def test_volume_invalid_granularity_raises(trends_conn):
    with pytest.raises(ValueError, match="granularity"):
        get_volume_trend(trends_conn, granularity="day")


@pytest.mark.unit
def test_physiology_series_sorted(trends_conn):
    """vo2_max rows inserted in reverse date order come back date-ascending."""
    trends_conn.executemany(
        "INSERT INTO vo2_max VALUES (?, ?, ?, ?, ?)",
        [
            (9000001121, 50.2, 50.0, "2025-10-15", 5),
            (9000001122, 49.8, 50.0, "2025-10-10", 5),
            (9000001123, 49.1, 49.0, "2025-10-05", 5),
        ],
    )
    trends_conn.execute(
        "INSERT INTO lactate_threshold VALUES (?, ?, ?, ?)",
        (9000001121, 168, 3.2, "2025-10-15 06:30:00"),
    )

    result = get_physiology_trend(trends_conn)

    dates = [point["date"] for point in result["vo2max"]]
    assert dates == ["2025-10-05", "2025-10-10", "2025-10-15"]
    assert all(isinstance(date, str) for date in dates)
    assert result["vo2max"][0]["value"] == pytest.approx(49.1)
    lt = result["lactate_threshold"]
    assert lt == [{"date": "2025-10-15", "heart_rate": 168, "speed_mps": 3.2}]


@pytest.mark.unit
def test_form_trend_joins_dates(trends_conn):
    trends_conn.executemany(
        _INSERT_ACTIVITY,
        [
            (9000001131, "2025-10-06", "Run A", 10.0, 3600, 360.0, 140),
            (9000001132, "2025-10-09", "Run B", 5.0, 1800, 360.0, 145),
        ],
    )
    trends_conn.executemany(
        "INSERT INTO form_evaluations VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1, 9000001131, 2.5, 0.4, 0.3, 4.2),
            (2, 9000001132, 1.8, 0.2, 0.1, 4.5),
        ],
    )

    result = get_form_trend(trends_conn)

    assert [(point["date"], point["overall_score"]) for point in result] == [
        ("2025-10-06", pytest.approx(4.2)),
        ("2025-10-09", pytest.approx(4.5)),
    ]
    first = result[0]
    assert first["gct_delta"] == pytest.approx(2.5)
    assert first["vo_delta"] == pytest.approx(0.4)
    assert first["vr_delta"] == pytest.approx(0.3)


@pytest.mark.unit
def test_efficiency_trend_zone_percentages(trends_conn):
    trends_conn.execute(
        _INSERT_ACTIVITY,
        (9000001141, "2025-10-06", "Run A", 10.0, 3600, 360.0, 140),
    )
    trends_conn.execute(
        "INSERT INTO hr_efficiency VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (9000001141, "Zone 2", "good", 10.0, 60.0, 20.0, 8.0, 2.0),
    )

    result = get_efficiency_trend(trends_conn)

    assert len(result) == 1
    point = result[0]
    assert point["date"] == "2025-10-06"
    assert point["zone2_percentage"] == pytest.approx(60.0)
    assert point["primary_zone"] == "Zone 2"
    assert point["aerobic_efficiency"] == "good"


@pytest.mark.integration
def test_queries_heat_adjusted_trend_happy(heat_conn_happy):
    """12 temp-varying runs fit the model and yield per-run neutral HR."""
    result = get_heat_adjusted_trend(heat_conn_happy, "2025-01-01", "2025-12-31")

    assert result["status"] == "ok"
    assert result["coefficients"]["ref_temp_c"] == pytest.approx(15.0)
    points = result["points"]
    assert len(points) == 12
    for point in points:
        # neutral HR is raw HR with the heat-induced uplift removed.
        assert point["neutral_hr"] == pytest.approx(
            point["raw_hr"] - point["heat_cost"]
        )


@pytest.mark.integration
def test_queries_heat_adjusted_trend_insufficient(heat_conn_insufficient):
    """A single run is below the model's fit minimum."""
    result = get_heat_adjusted_trend(heat_conn_insufficient, "2025-01-01", "2025-12-31")

    assert result["status"] == "insufficient_data"
