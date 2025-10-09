"""
Tests for Splits Inserter

Test coverage:
- Unit tests for insert_splits function
- Integration tests with DuckDB
"""

import json

import pytest

from tools.database.inserters.splits import insert_splits


class TestSplitsInserter:
    """Test suite for Splits Inserter."""

    @pytest.fixture
    def sample_performance_file(self, tmp_path):
        """Create sample performance.json file with split_metrics."""
        performance_data = {
            "basic_metrics": {
                "distance_km": 5.0,
                "duration_seconds": 1500,
            },
            "split_metrics": [
                {
                    "split_number": 1,
                    "distance_km": 1.0,
                    "avg_pace_seconds_per_km": 300,
                    "avg_heart_rate": 140,
                    "avg_cadence": 170,
                    "avg_power": 250,
                    "ground_contact_time_ms": 240,
                    "vertical_oscillation_cm": 7.5,
                    "vertical_ratio_percent": 8.5,
                    "elevation_gain_m": 5,
                    "elevation_loss_m": 2,
                    "terrain_type": "平坦",
                    "role_phase": "warmup",
                },
                {
                    "split_number": 2,
                    "distance_km": 1.0,
                    "avg_pace_seconds_per_km": 295,
                    "avg_heart_rate": 145,
                    "avg_cadence": 172,
                    "avg_power": 255,
                    "ground_contact_time_ms": 238,
                    "vertical_oscillation_cm": 7.3,
                    "vertical_ratio_percent": 8.3,
                    "elevation_gain_m": 3,
                    "elevation_loss_m": 4,
                    "terrain_type": "平坦",
                    "role_phase": "run",
                },
            ],
        }

        performance_file = tmp_path / "20464005432.json"
        with open(performance_file, "w", encoding="utf-8") as f:
            json.dump(performance_data, f, ensure_ascii=False, indent=2)

        return performance_file

    @pytest.mark.unit
    def test_insert_splits_success(self, sample_performance_file, tmp_path):
        """Test insert_splits inserts data successfully."""
        # Setup: Create temporary DuckDB
        db_path = tmp_path / "test.duckdb"

        # Execute
        result = insert_splits(
            performance_file=str(sample_performance_file),
            activity_id=20464005432,
            db_path=str(db_path),
        )

        # Verify
        assert result is True
        assert db_path.exists()

    @pytest.mark.unit
    def test_insert_splits_missing_file(self, tmp_path):
        """Test insert_splits handles missing file."""
        db_path = tmp_path / "test.duckdb"

        result = insert_splits(
            performance_file="/nonexistent/file.json",
            activity_id=12345,
            db_path=str(db_path),
        )

        assert result is False

    @pytest.mark.unit
    def test_insert_splits_no_split_metrics(self, tmp_path):
        """Test insert_splits handles missing split_metrics."""
        # Create performance file without split_metrics
        performance_data = {"basic_metrics": {"distance_km": 5.0}}
        performance_file = tmp_path / "test.json"
        with open(performance_file, "w", encoding="utf-8") as f:
            json.dump(performance_data, f)

        db_path = tmp_path / "test.duckdb"

        result = insert_splits(
            performance_file=str(performance_file),
            activity_id=12345,
            db_path=str(db_path),
        )

        assert result is False

    @pytest.mark.integration
    def test_insert_splits_db_integration(self, sample_performance_file, tmp_path):
        """Test insert_splits actually writes to DuckDB."""
        import duckdb

        db_path = tmp_path / "test.duckdb"

        # Execute
        result = insert_splits(
            performance_file=str(sample_performance_file),
            activity_id=20464005432,
            db_path=str(db_path),
        )

        assert result is True

        # Verify data in DuckDB
        conn = duckdb.connect(str(db_path))

        # Check splits table exists
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        assert "splits" in table_names

        # Check splits data
        splits = conn.execute(
            "SELECT * FROM splits WHERE activity_id = 20464005432 ORDER BY split_index"
        ).fetchall()
        assert len(splits) == 2

        # Verify first split data
        split1 = splits[0]
        assert split1[0] == 20464005432  # activity_id
        assert split1[1] == 1  # split_index
        assert split1[2] == 1.0  # distance
        assert split1[5] == 300  # pace_seconds_per_km
        assert split1[6] == 140  # heart_rate

        # Verify second split data
        split2 = splits[1]
        assert split2[0] == 20464005432  # activity_id
        assert split2[1] == 2  # split_index
        assert split2[2] == 1.0  # distance
        assert split2[5] == 295  # pace_seconds_per_km
        assert split2[6] == 145  # heart_rate

        conn.close()

    @pytest.mark.integration
    def test_insert_splits_with_role_phase(self, sample_performance_file, tmp_path):
        """Test insert_splits correctly inserts role_phase data (4-phase support)."""
        import duckdb

        db_path = tmp_path / "test.duckdb"

        # Execute
        result = insert_splits(
            performance_file=str(sample_performance_file),
            activity_id=20464005432,
            db_path=str(db_path),
        )

        assert result is True

        # Verify role_phase data
        conn = duckdb.connect(str(db_path))

        splits = conn.execute(
            """
            SELECT split_index, role_phase
            FROM splits
            WHERE activity_id = 20464005432
            ORDER BY split_index
            """
        ).fetchall()

        assert len(splits) == 2

        # Verify role_phase values
        assert splits[0][1] == "warmup"  # split 1
        assert splits[1][1] == "run"  # split 2

        conn.close()
