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
            cadence DOUBLE
        )
    """)
    conn.execute("""
        CREATE TABLE performance_trends (
            activity_id BIGINT,
            run_splits VARCHAR
        )
    """)


@pytest.mark.integration
class TestGetSplitsDataWithRunSplits:
    """Test get_splits_data when run_splits exist in performance_trends."""

    def test_with_run_splits(self, tmp_path: Path) -> None:
        """Only splits matching run_splits indices should be averaged."""
        db_path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(db_path)
        _create_tables(conn)

        # Insert performance_trends with run_splits="2,3"
        conn.execute(
            "INSERT INTO performance_trends VALUES (?, ?)",
            [100, "2,3"],
        )

        # Insert splits: index 1 should be excluded, indices 2 and 3 included
        conn.execute(
            "INSERT INTO splits VALUES (?, ?, ?, ?, ?, ?, ?)",
            [100, 1, 300.0, 250.0, 10.0, 8.0, 180.0],
        )
        conn.execute(
            "INSERT INTO splits VALUES (?, ?, ?, ?, ?, ?, ?)",
            [100, 2, 320.0, 240.0, 9.0, 7.0, 175.0],
        )
        conn.execute(
            "INSERT INTO splits VALUES (?, ?, ?, ?, ?, ?, ?)",
            [100, 3, 340.0, 260.0, 11.0, 9.0, 185.0],
        )
        conn.close()

        result = get_splits_data(db_path, 100)

        # Only splits 2 and 3 should be averaged
        assert result["pace_s_per_km"] == pytest.approx(330.0)  # (320+340)/2
        assert result["gct_ms"] == pytest.approx(250.0)  # (240+260)/2
        assert result["vo_cm"] == pytest.approx(10.0)  # (9+11)/2
        assert result["vr_pct"] == pytest.approx(8.0)  # (7+9)/2
        assert result["cadence"] == pytest.approx(180.0)  # (175+185)/2


@pytest.mark.integration
class TestGetSplitsDataWithoutRunSplits:
    """Test get_splits_data when no run_splits in performance_trends."""

    def test_without_run_splits(self, tmp_path: Path) -> None:
        """All splits should be used when run_splits is absent."""
        db_path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(db_path)
        _create_tables(conn)

        # Insert performance_trends without run_splits (NULL)
        conn.execute(
            "INSERT INTO performance_trends VALUES (?, ?)",
            [200, None],
        )

        # Insert 3 splits - all should be included
        conn.execute(
            "INSERT INTO splits VALUES (?, ?, ?, ?, ?, ?, ?)",
            [200, 1, 300.0, 240.0, 9.0, 7.0, 170.0],
        )
        conn.execute(
            "INSERT INTO splits VALUES (?, ?, ?, ?, ?, ?, ?)",
            [200, 2, 330.0, 250.0, 10.0, 8.0, 180.0],
        )
        conn.execute(
            "INSERT INTO splits VALUES (?, ?, ?, ?, ?, ?, ?)",
            [200, 3, 360.0, 260.0, 11.0, 9.0, 190.0],
        )
        conn.close()

        result = get_splits_data(db_path, 200)

        # All 3 splits should be averaged
        assert result["pace_s_per_km"] == pytest.approx(330.0)  # (300+330+360)/3
        assert result["gct_ms"] == pytest.approx(250.0)  # (240+250+260)/3
        assert result["vo_cm"] == pytest.approx(10.0)  # (9+10+11)/3
        assert result["vr_pct"] == pytest.approx(8.0)  # (7+8+9)/3
        assert result["cadence"] == pytest.approx(180.0)  # (170+180+190)/3


@pytest.mark.integration
class TestGetSplitsDataNoSplits:
    """Test get_splits_data raises ValueError when no splits found."""

    def test_no_splits_raises_value_error(self, tmp_path: Path) -> None:
        """ValueError should be raised when no matching splits exist."""
        db_path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(db_path)
        _create_tables(conn)

        # Insert performance_trends but no splits at all
        conn.execute(
            "INSERT INTO performance_trends VALUES (?, ?)",
            [300, None],
        )
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
        # Insert split with NULL cadence
        conn.execute(
            "INSERT INTO splits VALUES (?, ?, ?, ?, ?, ?, ?)",
            [400, 1, 300.0, 240.0, 9.0, 7.0, None],
        )
        conn.close()

        result = get_splits_data(db_path, 400)

        assert result["cadence"] == 0.0
        # Other metrics should still be populated
        assert result["pace_s_per_km"] == pytest.approx(300.0)
        assert result["gct_ms"] == pytest.approx(240.0)
        assert result["vo_cm"] == pytest.approx(9.0)
        assert result["vr_pct"] == pytest.approx(7.0)
