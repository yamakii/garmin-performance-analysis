"""Tests for the gear usage helpers in the metadata reader (Issue #1207).

Shoes are identified by ``gear_uuid``, not by name: Garmin's newer gear form
leaves ``gear_model`` as the base model, so a replacement pair of the same shoe
reuses the string. ``gear_model`` remains the fallback for rows ingested before
``gear_uuid`` existed.
"""

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.readers.metadata import (
    collect_activity_gear,
    collect_week_gear_usage,
)


def _insert(
    conn: duckdb.DuckDBPyConnection,
    activity_id: int,
    activity_date: str,
    distance_km: float,
    gear_model: str | None = None,
    gear_nickname: str | None = None,
    gear_uuid: str | None = None,
    gear_type: str | None = "Shoes",
) -> None:
    """Insert one activity row with the gear columns under test."""
    conn.execute(
        """
        INSERT INTO activities (
            activity_id, activity_date, total_distance_km,
            gear_type, gear_model, gear_nickname, gear_uuid
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            activity_id,
            activity_date,
            distance_km,
            gear_type if gear_model else None,
            gear_model,
            gear_nickname,
            gear_uuid,
        ],
    )


@pytest.fixture
def gear_conn(reader_db_path: Path) -> duckdb.DuckDBPyConnection:
    """Connection holding one shoe used three times, plus a second shoe."""
    conn = duckdb.connect(str(reader_db_path))
    _insert(conn, 1, "2026-09-01", 10.0, "Test Shoe A", "v1", "uuid-a")
    _insert(conn, 2, "2026-09-03", 12.0, "Test Shoe A", "v1", "uuid-a")
    _insert(conn, 3, "2026-09-05", 8.0, "Test Shoe A", "v1", "uuid-a")
    # 40 km in one outing, so Shoe B outranks Shoe A's 30 km without a tie.
    _insert(conn, 4, "2026-09-03", 40.0, "Test Shoe B", None, "uuid-b")
    return conn


@pytest.mark.integration
class TestCollectActivityGear:
    """Tests for collect_activity_gear()."""

    def test_collect_activity_gear_returns_cumulative_counts(
        self, gear_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Counts are as of the given run, not as of today."""
        result = collect_activity_gear(gear_conn, 2)

        assert result is not None
        assert result["gear_model"] == "Test Shoe A"
        assert result["gear_nickname"] == "v1"
        assert result["gear_label"] == "Test Shoe A (v1)"
        assert result["gear_type"] == "Shoes"
        assert result["first_use_date"] == "2026-09-01"
        assert result["runs_on_gear"] == 2
        assert result["km_on_gear"] == 22.0
        assert result["is_new_gear"] is True

    def test_collect_activity_gear_excludes_other_models(
        self, gear_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """A different shoe on the same day does not inflate the total."""
        result = collect_activity_gear(gear_conn, 4)

        assert result is not None
        assert result["gear_model"] == "Test Shoe B"
        assert result["runs_on_gear"] == 1
        assert result["km_on_gear"] == 40.0

    def test_collect_activity_gear_separates_pairs_sharing_a_model_name(
        self, reader_db_path: Path
    ) -> None:
        """Two generations of one model must not share a mileage total.

        This is the collision Garmin's newer gear form creates: both pairs
        carry ``customMakeModel = "NB 1080"`` and differ only by nickname and
        uuid.
        """
        conn = duckdb.connect(str(reader_db_path))
        _insert(conn, 1, "2026-09-01", 10.0, "NB 1080", "v14", "uuid-v14")
        _insert(conn, 2, "2026-09-03", 12.0, "NB 1080", "v14", "uuid-v14")
        _insert(conn, 3, "2026-09-08", 8.0, "NB 1080", "v15", "uuid-v15")

        result = collect_activity_gear(conn, 3)

        assert result is not None
        assert result["gear_label"] == "NB 1080 (v15)"
        assert result["runs_on_gear"] == 1
        assert result["km_on_gear"] == 8.0
        assert result["first_use_date"] == "2026-09-08"

    def test_collect_activity_gear_falls_back_to_model_without_uuid(
        self, reader_db_path: Path
    ) -> None:
        """Rows ingested before gear_uuid existed still aggregate by name."""
        conn = duckdb.connect(str(reader_db_path))
        _insert(conn, 1, "2026-09-01", 10.0, "Legacy Shoe")
        _insert(conn, 2, "2026-09-03", 12.0, "Legacy Shoe")

        result = collect_activity_gear(conn, 2)

        assert result is not None
        assert result["runs_on_gear"] == 2
        assert result["km_on_gear"] == 22.0
        assert result["gear_label"] == "Legacy Shoe"

    def test_collect_activity_gear_returns_none_without_gear(
        self, reader_db_path: Path
    ) -> None:
        conn = duckdb.connect(str(reader_db_path))
        _insert(conn, 1, "2026-09-01", 10.0)

        assert collect_activity_gear(conn, 1) is None

    def test_collect_activity_gear_returns_none_for_unknown_activity(
        self, gear_conn: duckdb.DuckDBPyConnection
    ) -> None:
        assert collect_activity_gear(gear_conn, 999999) is None


@pytest.mark.integration
class TestCollectWeekGearUsage:
    """Tests for collect_week_gear_usage()."""

    def test_collect_week_gear_usage_orders_by_km_desc(
        self, gear_conn: duckdb.DuckDBPyConnection
    ) -> None:
        result = collect_week_gear_usage(gear_conn, "2026-09-01", "2026-09-07")

        assert len(result) == 2
        assert result[0]["gear_model"] == "Test Shoe B"
        assert result[0]["km"] == 40.0
        assert result[0]["runs"] == 1
        assert result[1]["gear_model"] == "Test Shoe A"
        assert result[1]["km"] == 30.0
        assert result[1]["runs"] == 3

    def test_collect_week_gear_usage_window_is_inclusive(
        self, gear_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Only the runs inside the window count toward runs / km."""
        result = collect_week_gear_usage(gear_conn, "2026-09-01", "2026-09-03")

        by_model = {row["gear_model"]: row for row in result}
        assert by_model["Test Shoe A"]["runs"] == 2
        assert by_model["Test Shoe A"]["km"] == 22.0

    def test_collect_week_gear_usage_totals_are_cumulative(
        self, gear_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """runs_on_gear_total spans the shoe's life through the window end."""
        result = collect_week_gear_usage(gear_conn, "2026-09-05", "2026-09-07")

        assert len(result) == 1
        assert result[0]["gear_model"] == "Test Shoe A"
        assert result[0]["runs"] == 1
        assert result[0]["runs_on_gear_total"] == 3
        assert result[0]["is_new_gear"] is True

    def test_collect_week_gear_usage_empty_window(
        self, gear_conn: duckdb.DuckDBPyConnection
    ) -> None:
        assert collect_week_gear_usage(gear_conn, "2020-01-01", "2020-01-07") == []
