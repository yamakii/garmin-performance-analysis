"""Tests for db_writer schema synchronization with production DuckDB."""

import tempfile
from pathlib import Path

import duckdb
import pytest

from tools.database.db_writer import GarminDBWriter


@pytest.fixture
def temp_db():
    """Create a temporary DuckDB database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
        yield db_path


class TestDBWriterSchema:
    """Test db_writer schema matches production DuckDB."""

    def test_ensure_tables_creates_36_column_activities_table(self, temp_db):
        """Test that _ensure_tables creates activities table with 36 columns."""
        _ = GarminDBWriter(temp_db)  # Trigger _ensure_tables()

        # Connect and describe activities table
        conn = duckdb.connect(str(temp_db), read_only=True)
        result = conn.execute("DESCRIBE activities").fetchall()
        conn.close()

        # Extract column names
        column_names = [row[0] for row in result]

        # Expected 36 columns from production schema
        expected_columns = [
            "activity_id",
            "date",  # NOT activity_date
            "activity_name",
            "start_time_local",
            "start_time_gmt",
            "total_time_seconds",  # NOT duration_seconds
            "total_distance_km",  # NOT distance_km
            "avg_pace_seconds_per_km",
            "avg_heart_rate",
            "max_heart_rate",
            "avg_cadence",
            "avg_power",
            "normalized_power",
            "cadence_stability",
            "power_efficiency",
            "pace_variability",
            "aerobic_te",
            "anaerobic_te",
            "training_effect_source",
            "power_to_weight",
            "weight_kg",  # NEW
            "weight_source",  # NEW
            "weight_method",  # NEW
            "stability_score",
            "external_temp_c",
            "external_temp_f",
            "humidity",
            "wind_speed_ms",
            "wind_direction_compass",
            "gear_name",
            "gear_type",
            "created_at",
            "updated_at",
            "total_elevation_gain",
            "total_elevation_loss",
            "location_name",
        ]

        assert len(column_names) == 36, f"Expected 36 columns, got {len(column_names)}"
        for expected_col in expected_columns:
            assert (
                expected_col in column_names
            ), f"Missing column: {expected_col}. Found: {column_names}"

    def test_insert_activity_with_weight_parameters(self, temp_db):
        """Test that insert_activity() inserts weight_kg, weight_source, weight_method."""
        writer = GarminDBWriter(temp_db)

        # Insert activity with weight data
        result = writer.insert_activity(
            activity_id=20594901208,
            activity_date="2025-10-05",
            activity_name="Test Run",
            location_name="Tokyo",
            weight_kg=77.3,
            weight_source="statistical_7d_median",
            weight_method="median",
            distance_km=4.33,
            duration_seconds=1920,
            avg_pace_seconds_per_km=443.4,
            avg_heart_rate=127,
        )

        assert result is True

        # Verify weight data was inserted
        conn = duckdb.connect(str(temp_db), read_only=True)
        row = conn.execute(
            "SELECT weight_kg, weight_source, weight_method FROM activities WHERE activity_id = 20594901208"
        ).fetchone()
        conn.close()

        assert row is not None, "Activity not found in database"
        assert row[0] == 77.3, f"Expected weight_kg=77.3, got {row[0]}"
        assert (
            row[1] == "statistical_7d_median"
        ), f"Expected weight_source='statistical_7d_median', got {row[1]}"
        assert row[2] == "median", f"Expected weight_method='median', got {row[2]}"

    def test_insert_activity_without_weight_parameters(self, temp_db):
        """Test backward compatibility: insert_activity() works without weight parameters."""
        writer = GarminDBWriter(temp_db)

        # Insert activity without weight data
        result = writer.insert_activity(
            activity_id=20594901208,
            activity_date="2025-10-05",
            activity_name="Test Run",
            location_name="Tokyo",
            distance_km=4.33,
            duration_seconds=1920,
            avg_pace_seconds_per_km=443.4,
            avg_heart_rate=127,
        )

        assert result is True

        # Verify activity was inserted with NULL weight values
        conn = duckdb.connect(str(temp_db), read_only=True)
        row = conn.execute(
            "SELECT activity_id, activity_name, weight_kg FROM activities WHERE activity_id = 20594901208"
        ).fetchone()
        conn.close()

        assert row is not None, "Activity not found in database"
        assert row[0] == 20594901208
        assert row[1] == "Test Run"
        assert row[2] is None, f"Expected weight_kg=None, got {row[2]}"

    def test_column_name_consistency_with_production(self, temp_db):
        """Test that column names match production schema (date, total_distance_km, total_time_seconds)."""
        writer = GarminDBWriter(temp_db)

        # Insert activity using production column names
        writer.insert_activity(
            activity_id=20594901208,
            activity_date="2025-10-05",  # Maps to 'date' column
            activity_name="Test Run",
            distance_km=4.33,  # Maps to 'total_distance_km' column
            duration_seconds=1920,  # Maps to 'total_time_seconds' column
            avg_pace_seconds_per_km=443.4,
            avg_heart_rate=127,
        )

        # Verify using production column names
        conn = duckdb.connect(str(temp_db), read_only=True)
        row = conn.execute(
            """
            SELECT date, total_distance_km, total_time_seconds
            FROM activities
            WHERE activity_id = 20594901208
            """
        ).fetchone()
        conn.close()

        assert row is not None, "Activity not found in database"
        assert str(row[0]) == "2025-10-05", f"Expected date='2025-10-05', got {row[0]}"
        assert row[1] == 4.33, f"Expected total_distance_km=4.33, got {row[1]}"
        assert row[2] == 1920, f"Expected total_time_seconds=1920, got {row[2]}"
