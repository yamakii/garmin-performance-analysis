"""Tests for form_baseline.data_fetcher module."""

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.form_baseline.data_fetcher import get_splits_data


def _create_tables(conn: duckdb.DuckDBPyConnection) -> None:
    """Create minimal splits and performance_trends tables for testing."""
    conn.execute("""
        CREATE TABLE splits (
            activity_id BIGINT,
            split_index INTEGER,
            pace_seconds_per_km DOUBLE,
            ground_contact_time DOUBLE,
            vertical_oscillation DOUBLE,
            vertical_ratio DOUBLE,
            cadence DOUBLE,
            distance DOUBLE
        )
    """)
    conn.execute("""
        CREATE TABLE performance_trends (
            activity_id BIGINT,
            run_splits VARCHAR
        )
    """)


def _insert_split(
    conn: duckdb.DuckDBPyConnection,
    activity_id: int,
    split_index: int,
    pace: float,
    gct: float,
    vo: float,
    vr: float,
    cadence: float | None,
    distance: float = 1.0,
) -> None:
    """Insert one split row; distance defaults to a full 1 km lap."""
    conn.execute(
        "INSERT INTO splits VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [activity_id, split_index, pace, gct, vo, vr, cadence, distance],
    )


@pytest.mark.integration
class TestGetSplitsDataWithRunSplits:
    """Test get_splits_data when run_splits exist in performance_trends."""

    def test_with_run_splits(self, tmp_path: Path) -> None:
        """Only splits matching run_splits indices should be averaged."""
        db_path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(db_path)
        _create_tables(conn)

        conn.execute("INSERT INTO performance_trends VALUES (?, ?)", [100, "2,3"])

        # index 1 should be excluded, indices 2 and 3 included
        _insert_split(conn, 100, 1, 300.0, 250.0, 10.0, 8.0, 180.0)
        _insert_split(conn, 100, 2, 320.0, 240.0, 9.0, 7.0, 175.0)
        _insert_split(conn, 100, 3, 340.0, 260.0, 11.0, 9.0, 185.0)
        conn.close()

        result = get_splits_data(db_path, 100)

        assert result["pace_s_per_km"] == pytest.approx(330.0)  # (320+340)/2
        assert result["gct_ms"] == pytest.approx(250.0)  # (240+260)/2
        assert result["vo_cm"] == pytest.approx(10.0)  # (9+11)/2
        assert result["vr_pct"] == pytest.approx(8.0)  # (7+9)/2
        assert result["cadence"] == pytest.approx(180.0)  # (175+185)/2

    def test_get_splits_data_applies_filter_within_run_splits(
        self, tmp_path: Path
    ) -> None:
        """A walk lap inside run_splits is still dropped (#878).

        run_splits is phase-based and a deliberate walk break is recorded with
        role_phase='run', so phase selection alone cannot exclude it.
        """
        db_path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(db_path)
        _create_tables(conn)

        conn.execute("INSERT INTO performance_trends VALUES (?, ?)", [110, "1,2,3"])

        _insert_split(conn, 110, 1, 480.0, 275.0, 7.0, 10.0, 175.0)
        _insert_split(conn, 110, 2, 480.0, 275.0, 7.0, 10.0, 175.0)
        # Walk break: inside run_splits, but slower than the 600 s/km ceiling
        _insert_split(conn, 110, 3, 900.0, 278.0, 5.7, 8.2, 76.0, distance=0.5)
        conn.close()

        result = get_splits_data(db_path, 110)

        assert result["cadence"] == pytest.approx(175.0)
        assert result["pace_s_per_km"] == pytest.approx(480.0)
        assert result["running_splits_only"] is True
        assert result["split_count"] == 2
        assert result["excluded_split_count"] == 1


@pytest.mark.integration
class TestGetSplitsDataWithoutRunSplits:
    """Test get_splits_data when no run_splits in performance_trends."""

    def test_without_run_splits(self, tmp_path: Path) -> None:
        """All splits should be used when run_splits is absent."""
        db_path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(db_path)
        _create_tables(conn)

        conn.execute("INSERT INTO performance_trends VALUES (?, ?)", [200, None])

        _insert_split(conn, 200, 1, 300.0, 240.0, 9.0, 7.0, 170.0)
        _insert_split(conn, 200, 2, 330.0, 250.0, 10.0, 8.0, 180.0)
        _insert_split(conn, 200, 3, 360.0, 260.0, 11.0, 9.0, 190.0)
        conn.close()

        result = get_splits_data(db_path, 200)

        assert result["pace_s_per_km"] == pytest.approx(330.0)  # (300+330+360)/3
        assert result["gct_ms"] == pytest.approx(250.0)  # (240+250+260)/3
        assert result["vo_cm"] == pytest.approx(10.0)  # (9+10+11)/3
        assert result["vr_pct"] == pytest.approx(8.0)  # (7+8+9)/3
        assert result["cadence"] == pytest.approx(180.0)  # (170+180+190)/3


@pytest.mark.integration
class TestGetSplitsDataRunningFilter:
    """Walk breaks and GPS fragments must not enter the averages (#878)."""

    def test_get_splits_data_excludes_walk_splits(self, tmp_path: Path) -> None:
        """A deliberate walk lap must not drag the activity averages down."""
        db_path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(db_path)
        _create_tables(conn)

        _insert_split(conn, 500, 1, 480.0, 275.0, 7.0, 10.0, 175.0)
        _insert_split(conn, 500, 2, 480.0, 275.0, 7.0, 10.0, 175.0)
        _insert_split(conn, 500, 3, 900.0, 278.0, 5.7, 8.2, 76.0, distance=0.5)
        conn.close()

        result = get_splits_data(db_path, 500)

        # Unfiltered this would be (175+175+76)/3 = 142.0
        assert result["cadence"] == pytest.approx(175.0)
        # The pace fed to the pace-dependent models must be the running pace
        assert result["pace_s_per_km"] == pytest.approx(480.0)

    def test_get_splits_data_excludes_gps_fragments(self, tmp_path: Path) -> None:
        """Sub-0.4 km manual-lap fragments must not enter the averages."""
        db_path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(db_path)
        _create_tables(conn)

        _insert_split(conn, 510, 1, 480.0, 275.0, 7.0, 10.0, 175.0)
        _insert_split(conn, 510, 2, 480.0, 275.0, 7.0, 10.0, 175.0)
        # 60 m fragment: artificially fast pace, walking cadence
        _insert_split(conn, 510, 3, 244.0, 275.0, 6.0, 8.3, 115.0, distance=0.06)
        conn.close()

        result = get_splits_data(db_path, 510)

        # Unfiltered this would be (175+175+115)/3 = 155.0
        assert result["cadence"] == pytest.approx(175.0)
        assert result["pace_s_per_km"] == pytest.approx(480.0)

    def test_get_splits_data_reports_provenance(self, tmp_path: Path) -> None:
        """Callers can tell how many splits were kept and dropped."""
        db_path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(db_path)
        _create_tables(conn)

        _insert_split(conn, 520, 1, 480.0, 275.0, 7.0, 10.0, 175.0)
        _insert_split(conn, 520, 2, 480.0, 275.0, 7.0, 10.0, 175.0)
        _insert_split(conn, 520, 3, 900.0, 278.0, 5.7, 8.2, 76.0, distance=0.5)
        _insert_split(conn, 520, 4, 244.0, 275.0, 6.0, 8.3, 115.0, distance=0.06)
        conn.close()

        result = get_splits_data(db_path, 520)

        assert result["running_splits_only"] is True
        assert result["split_count"] == 2
        assert result["excluded_split_count"] == 2

    def test_get_splits_data_falls_back_when_all_filtered(self, tmp_path: Path) -> None:
        """Walk-dominated sessions stay evaluable instead of raising.

        Five activities in the history are slower than 10:00/km throughout; the
        filter would leave them with no rows at all.
        """
        db_path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(db_path)
        _create_tables(conn)

        _insert_split(conn, 530, 1, 700.0, 280.0, 6.0, 8.0, 150.0)
        _insert_split(conn, 530, 2, 720.0, 282.0, 6.2, 8.2, 152.0)
        conn.close()

        result = get_splits_data(db_path, 530)

        assert result["pace_s_per_km"] == pytest.approx(710.0)
        assert result["cadence"] == pytest.approx(151.0)
        assert result["running_splits_only"] is False
        assert result["split_count"] == 2
        assert result["excluded_split_count"] == 0


@pytest.mark.integration
class TestGetSplitsDataNoSplits:
    """Test get_splits_data raises ValueError when no splits found."""

    def test_no_splits_raises_value_error(self, tmp_path: Path) -> None:
        """ValueError should be raised when no matching splits exist."""
        db_path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(db_path)
        _create_tables(conn)

        conn.execute("INSERT INTO performance_trends VALUES (?, ?)", [300, None])
        conn.close()

        with pytest.raises(ValueError, match="No splits found"):
            get_splits_data(db_path, 300)


@pytest.mark.integration
class TestGetSplitsDataCadenceNull:
    """Test get_splits_data handles NULL cadence correctly."""

    def test_cadence_null_returns_zero(self, tmp_path: Path) -> None:
        """When cadence is NULL, it should be returned as 0.0."""
        db_path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(db_path)
        _create_tables(conn)

        # No performance_trends row means run_splits will be None
        _insert_split(conn, 400, 1, 300.0, 240.0, 9.0, 7.0, None)
        conn.close()

        result = get_splits_data(db_path, 400)

        assert result["cadence"] == 0.0
        assert result["pace_s_per_km"] == pytest.approx(300.0)
        assert result["gct_ms"] == pytest.approx(240.0)
        assert result["vo_cm"] == pytest.approx(9.0)
        assert result["vr_pct"] == pytest.approx(7.0)
