"""
Integration tests for DuckDB regeneration with --force option.

These tests verify the actual deletion and re-insertion behavior with
a real (in-memory) DuckDB database.
"""

import json
import tempfile
from pathlib import Path

import duckdb
import pytest


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
