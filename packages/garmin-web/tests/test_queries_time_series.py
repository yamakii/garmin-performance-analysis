"""Unit tests for garmin_web.queries.time_series.get_time_series."""

import pytest
from garmin_mcp.database.connection import get_connection

from garmin_web.queries.time_series import ALLOWED_METRICS, get_time_series

FULL_ACTIVITY_ID = 9000000101  # 2000 time-series rows
PARTIAL_ACTIVITY_ID = 9000000102  # 300 time-series rows


@pytest.mark.unit
def test_time_series_downsamples_to_max_points(detail_db_path):
    with get_connection(detail_db_path) as conn:
        result = get_time_series(
            conn, FULL_ACTIVITY_ID, ["heart_rate", "speed"], max_points=500
        )

    assert len(result["timestamps"]) <= 500
    assert len(result["metrics"]["heart_rate"]) == len(result["timestamps"])
    assert len(result["metrics"]["speed"]) == len(result["timestamps"])

    # First (seq_no=0) and last (seq_no=1999) rows must be kept
    assert result["timestamps"][0] == 0
    assert result["timestamps"][-1] == 1999
    assert result["metrics"]["heart_rate"][0] == 140.0  # 140 + 0 % 20
    assert result["metrics"]["heart_rate"][-1] == 159.0  # 140 + 1999 % 20


@pytest.mark.unit
def test_time_series_below_max_returns_all(detail_db_path):
    with get_connection(detail_db_path) as conn:
        result = get_time_series(
            conn, PARTIAL_ACTIVITY_ID, ["heart_rate"], max_points=500
        )

    assert len(result["timestamps"]) == 300
    assert len(result["metrics"]["heart_rate"]) == 300
    assert result["timestamps"][0] == 0
    assert result["timestamps"][-1] == 299


@pytest.mark.unit
def test_time_series_unknown_metric_raises(detail_db_path):
    with (
        get_connection(detail_db_path) as conn,
        pytest.raises(ValueError, match="Unknown metrics: bogus"),
    ):
        get_time_series(conn, FULL_ACTIVITY_ID, ["bogus"])


@pytest.mark.unit
def test_allowed_metrics_excludes_key_columns():
    assert "activity_id" not in ALLOWED_METRICS
    assert "seq_no" not in ALLOWED_METRICS
    assert "timestamp_s" not in ALLOWED_METRICS
    assert "heart_rate" in ALLOWED_METRICS
    assert "speed" in ALLOWED_METRICS
