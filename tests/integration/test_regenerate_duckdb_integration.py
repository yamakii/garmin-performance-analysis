"""
Integration tests for DuckDB regeneration with --force option.

These tests verify the actual deletion and re-insertion behavior with
a real (in-memory) DuckDB database.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from tools.scripts.regenerate_duckdb import DuckDBRegenerator


@pytest.fixture
def temp_db():
    """Create a temporary in-memory DuckDB database with test data."""
    # Use in-memory database for testing
    conn = duckdb.connect(":memory:")

    # Create minimal schema (just activities and splits tables)
    conn.execute(
        """
        CREATE TABLE activities (
            activity_id INTEGER PRIMARY KEY,
            activity_date DATE,
            activity_name VARCHAR
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE splits (
            activity_id INTEGER,
            split_number INTEGER,
            distance FLOAT,
            duration FLOAT,
            PRIMARY KEY (activity_id, split_number)
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE form_efficiency (
            activity_id INTEGER PRIMARY KEY,
            avg_gct FLOAT,
            avg_vo FLOAT
        )
    """
    )

    # Insert test data
    conn.execute(
        """
        INSERT INTO activities VALUES
        (12345, '2025-01-01', 'Test Run 1'),
        (67890, '2025-01-02', 'Test Run 2')
    """
    )

    conn.execute(
        """
        INSERT INTO splits VALUES
        (12345, 1, 1.0, 300.0),
        (12345, 2, 1.0, 310.0),
        (67890, 1, 1.0, 320.0)
    """
    )

    conn.execute(
        """
        INSERT INTO form_efficiency VALUES
        (12345, 250.0, 8.5),
        (67890, 255.0, 8.8)
    """
    )

    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def temp_raw_data_dir():
    """Create temporary raw data directory with test data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        activity_dir = Path(tmpdir) / "activity" / "12345"
        activity_dir.mkdir(parents=True)

        # Create minimal activity.json
        activity_data = {
            "summaryDTO": {
                "activityId": 12345,
                "startTimeLocal": "2025-01-01T10:00:00",
            }
        }
        with open(activity_dir / "activity.json", "w") as f:
            json.dump(activity_data, f)

        yield Path(tmpdir)


class TestForceOptionIntegration:
    """Integration tests for --force option with real DuckDB."""

    def test_force_option_deletes_and_reinserts(
        self, temp_db, temp_raw_data_dir, tmp_path
    ):
        """Test that --force deletes existing records and allows re-insertion."""
        # Arrange: Create a persistent DB file from temp_db
        db_path = tmp_path / "test.duckdb"

        # Copy schema and data to persistent file
        with duckdb.connect(str(db_path)) as conn:
            # Copy schema
            conn.execute(
                """
                CREATE TABLE activities (
                    activity_id INTEGER PRIMARY KEY,
                    activity_date DATE,
                    activity_name VARCHAR
                )
            """
            )
            conn.execute(
                """
                CREATE TABLE splits (
                    activity_id INTEGER,
                    split_number INTEGER,
                    distance FLOAT,
                    duration FLOAT,
                    PRIMARY KEY (activity_id, split_number)
                )
            """
            )
            conn.execute(
                """
                CREATE TABLE form_efficiency (
                    activity_id INTEGER PRIMARY KEY,
                    avg_gct FLOAT,
                    avg_vo FLOAT
                )
            """
            )

            # Copy data
            conn.execute(
                """
                INSERT INTO activities VALUES
                (12345, '2025-01-01', 'Test Run 1'),
                (67890, '2025-01-02', 'Test Run 2')
            """
            )
            conn.execute(
                """
                INSERT INTO splits VALUES
                (12345, 1, 1.0, 300.0),
                (12345, 2, 1.0, 310.0),
                (67890, 1, 1.0, 320.0)
            """
            )
            conn.execute(
                """
                INSERT INTO form_efficiency VALUES
                (12345, 250.0, 8.5),
                (67890, 255.0, 8.8)
            """
            )
            conn.commit()

        # Verify initial state
        with duckdb.connect(str(db_path)) as conn:
            result = conn.execute(
                "SELECT COUNT(*) FROM splits WHERE activity_id = 12345"
            ).fetchone()
            assert result is not None
            assert result[0] == 2, "Should have 2 splits initially"

        # Mock GarminIngestWorker to avoid actual processing
        mock_result = {"performance": "test_performance.json"}
        with patch(
            "tools.scripts.regenerate_duckdb.GarminIngestWorker"
        ) as mock_worker_class:
            mock_worker = MagicMock()
            mock_worker.process_activity.return_value = mock_result
            mock_worker_class.return_value = mock_worker

            # Act: Regenerate with force=True
            regenerator = DuckDBRegenerator(
                raw_dir=temp_raw_data_dir,
                db_path=db_path,
                tables=["splits"],
                force=True,
            )

            api_result = regenerator.regenerate_single_activity(12345, "2025-01-01")

            # Assert
            assert api_result["status"] == "success"
            # PHASE 3: Updated to expect tables parameter
            mock_worker.process_activity.assert_called_once_with(
                12345, "2025-01-01", tables=["splits"]
            )

        # Verify deletion occurred (splits should be deleted before process_activity)
        # Note: In real scenario, process_activity would re-insert data
        # Here we just verify the deletion part worked
        with duckdb.connect(str(db_path)) as conn:
            # Splits should be deleted (mock didn't re-insert)
            result = conn.execute(
                "SELECT COUNT(*) FROM splits WHERE activity_id = 12345"
            ).fetchone()
            assert result is not None
            assert result[0] == 0, "Splits should be deleted by force option"

            # Other activities should be unaffected
            result = conn.execute(
                "SELECT COUNT(*) FROM splits WHERE activity_id = 67890"
            ).fetchone()
            assert result is not None
            assert result[0] == 1, "Other activities should not be affected"

    def test_force_option_without_force_skips_existing(
        self, temp_db, temp_raw_data_dir, tmp_path
    ):
        """Test that without --force, full regeneration (no --tables) skips existing records.

        PHASE 3 Note: When --tables is specified, regeneration proceeds even without --force
        (table-selective regeneration is designed to update specified tables).
        This test now verifies full regeneration (tables=None) skip behavior.
        """
        # Arrange: Create a persistent DB file
        db_path = tmp_path / "test.duckdb"

        # Copy schema and data to persistent file
        with duckdb.connect(str(db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE activities (
                    activity_id INTEGER PRIMARY KEY,
                    activity_date DATE,
                    activity_name VARCHAR
                )
            """
            )
            conn.execute(
                """
                CREATE TABLE splits (
                    activity_id INTEGER,
                    split_number INTEGER,
                    distance FLOAT,
                    duration FLOAT,
                    PRIMARY KEY (activity_id, split_number)
                )
            """
            )
            conn.execute(
                """
                INSERT INTO activities VALUES
                (12345, '2025-01-01', 'Test Run 1'),
                (67890, '2025-01-02', 'Test Run 2')
            """
            )
            conn.execute(
                """
                INSERT INTO splits VALUES
                (12345, 1, 1.0, 300.0),
                (12345, 2, 1.0, 310.0),
                (67890, 1, 1.0, 320.0)
            """
            )
            conn.commit()

        # Verify initial state
        with duckdb.connect(str(db_path)) as conn:
            result = conn.execute(
                "SELECT COUNT(*) FROM splits WHERE activity_id = 12345"
            ).fetchone()
            assert result is not None
            initial_count = result[0]
            assert initial_count == 2, "Should have 2 splits initially"

        # Mock GarminIngestWorker
        with patch(
            "tools.scripts.regenerate_duckdb.GarminIngestWorker"
        ) as mock_worker_class:
            mock_worker = MagicMock()
            mock_worker_class.return_value = mock_worker

            # Act: Full regeneration (tables=None) WITHOUT force should skip
            regenerator = DuckDBRegenerator(
                raw_dir=temp_raw_data_dir,
                db_path=db_path,
                tables=None,  # PHASE 3: Full regeneration (not table-selective)
                force=False,  # No force
            )

            api_result = regenerator.regenerate_single_activity(12345, "2025-01-01")

            # Assert: Should be skipped for full regeneration
            assert api_result["status"] == "skipped"
            assert (
                "DuckDB cache exists" in api_result or api_result["status"] == "skipped"
            )
            mock_worker.process_activity.assert_not_called()

        # Verify data is unchanged
        with duckdb.connect(str(db_path)) as conn:
            result = conn.execute(
                "SELECT COUNT(*) FROM splits WHERE activity_id = 12345"
            ).fetchone()
            assert result is not None
            assert result[0] == initial_count, "Data should be unchanged when skipped"

    def test_force_deletes_multiple_tables(self, temp_db, temp_raw_data_dir, tmp_path):
        """Test that --force deletes from multiple specified tables."""
        # Arrange: Create a persistent DB file
        db_path = tmp_path / "test.duckdb"

        # Copy schema and data to persistent file
        with duckdb.connect(str(db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE activities (
                    activity_id INTEGER PRIMARY KEY,
                    activity_date DATE,
                    activity_name VARCHAR
                )
            """
            )
            conn.execute(
                """
                CREATE TABLE splits (
                    activity_id INTEGER,
                    split_number INTEGER,
                    distance FLOAT,
                    duration FLOAT,
                    PRIMARY KEY (activity_id, split_number)
                )
            """
            )
            conn.execute(
                """
                CREATE TABLE form_efficiency (
                    activity_id INTEGER PRIMARY KEY,
                    avg_gct FLOAT,
                    avg_vo FLOAT
                )
            """
            )
            conn.execute(
                """
                INSERT INTO activities VALUES
                (12345, '2025-01-01', 'Test Run 1'),
                (67890, '2025-01-02', 'Test Run 2')
            """
            )
            conn.execute(
                """
                INSERT INTO splits VALUES
                (12345, 1, 1.0, 300.0),
                (12345, 2, 1.0, 310.0),
                (67890, 1, 1.0, 320.0)
            """
            )
            conn.execute(
                """
                INSERT INTO form_efficiency VALUES
                (12345, 250.0, 8.5),
                (67890, 255.0, 8.8)
            """
            )
            conn.commit()

        # Verify initial state
        with duckdb.connect(str(db_path)) as conn:
            result = conn.execute(
                "SELECT COUNT(*) FROM splits WHERE activity_id = 12345"
            ).fetchone()
            assert result is not None
            splits_count = result[0]

            result = conn.execute(
                "SELECT COUNT(*) FROM form_efficiency WHERE activity_id = 12345"
            ).fetchone()
            assert result is not None
            form_count = result[0]

            assert splits_count == 2
            assert form_count == 1

        # Mock GarminIngestWorker
        with patch(
            "tools.scripts.regenerate_duckdb.GarminIngestWorker"
        ) as mock_worker_class:
            mock_worker = MagicMock()
            mock_worker.process_activity.return_value = {}
            mock_worker_class.return_value = mock_worker

            # Act: Regenerate with force=True for multiple tables
            regenerator = DuckDBRegenerator(
                raw_dir=temp_raw_data_dir,
                db_path=db_path,
                tables=["splits", "form_efficiency"],
                force=True,
            )

            api_result = regenerator.regenerate_single_activity(12345, "2025-01-01")

            # Assert
            assert api_result["status"] == "success"

        # Verify deletion from both tables
        with duckdb.connect(str(db_path)) as conn:
            result = conn.execute(
                "SELECT COUNT(*) FROM splits WHERE activity_id = 12345"
            ).fetchone()
            assert result is not None
            splits_count = result[0]

            result = conn.execute(
                "SELECT COUNT(*) FROM form_efficiency WHERE activity_id = 12345"
            ).fetchone()
            assert result is not None
            form_count = result[0]

            assert splits_count == 0, "Splits should be deleted"
            assert form_count == 0, "Form efficiency should be deleted"

            # Other activities unaffected
            result = conn.execute(
                "SELECT COUNT(*) FROM splits WHERE activity_id = 67890"
            ).fetchone()
            assert result is not None
            splits_67890 = result[0]

            result = conn.execute(
                "SELECT COUNT(*) FROM form_efficiency WHERE activity_id = 67890"
            ).fetchone()
            assert result is not None
            form_67890 = result[0]

            assert splits_67890 == 1, "Other activity splits should remain"
            assert form_67890 == 1, "Other activity form data should remain"
