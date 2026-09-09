"""GarminIngestWorker: activity date lookup and activity-id resolution (DuckDB first, API fallback)."""

from unittest.mock import patch

import pytest

from garmin_mcp.ingest.garmin_worker import GarminIngestWorker


class TestActivityResolution:
    @pytest.mark.unit
    def test_get_activity_date_from_db(self, tmp_path):
        """Test get_activity_date retrieves date from DuckDB."""
        import duckdb

        # Setup: Create temporary DuckDB with activity
        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activities (
                activity_id BIGINT PRIMARY KEY,
                activity_date DATE NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO activities (activity_id, activity_date) VALUES (12345, '2025-09-22')"
        )
        conn.close()

        # Execute
        worker = GarminIngestWorker(db_path=str(db_path))
        result = worker.get_activity_date(12345)

        # Verify
        assert result == "2025-09-22"

    @pytest.mark.unit
    def test_get_activity_date_not_found(self, tmp_path):
        """Test get_activity_date returns None for missing activity."""
        import duckdb

        # Setup: Create empty DuckDB
        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activities (
                activity_id BIGINT PRIMARY KEY,
                activity_date DATE NOT NULL
            )
        """)
        conn.close()

        # Execute
        worker = GarminIngestWorker(db_path=str(db_path))
        result = worker.get_activity_date(99999)

        # Verify
        assert result is None

    @pytest.mark.unit
    def test_resolve_from_duckdb_initializes_reader(self, tmp_path):
        """DuckDB-first resolution lazily inits the reader (issue #816).

        A worker with ``_db_reader=None`` whose DuckDB already contains the
        activity resolves the ID from DuckDB and never touches the API resolver.
        """
        import duckdb

        # Setup: DuckDB already has the run for the date
        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activities (
                activity_id BIGINT PRIMARY KEY,
                activity_date DATE NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO activities (activity_id, activity_date) "
            "VALUES (23471484304, '2026-07-04')"
        )
        conn.close()

        worker = GarminIngestWorker(db_path=str(db_path))
        assert worker._db_reader is None  # not yet initialized

        with patch.object(worker, "_resolve_activity_id_from_api") as mock_api:
            resolved = worker._resolve_activity_id_from_duckdb("2026-07-04")

        assert resolved == 23471484304
        mock_api.assert_not_called()
        # Reader was lazily initialized as a side effect.
        assert worker._db_reader is not None

    @pytest.mark.unit
    def test_resolve_falls_back_to_api_when_not_in_db(self, tmp_path):
        """When DuckDB has no activity for the date, fall back to the API resolver.

        The DuckDB-first path returns None and ``process_activity_by_date``
        delegates to ``_resolve_activity_id_from_api`` (issue #816).
        """
        import duckdb

        # Setup: empty activities table (no row for the date)
        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activities (
                activity_id BIGINT PRIMARY KEY,
                activity_date DATE NOT NULL
            )
        """)
        conn.close()

        worker = GarminIngestWorker(db_path=str(db_path))

        with (
            patch.object(
                worker, "_resolve_activity_id_from_api", return_value=111
            ) as mock_api,
            patch.object(
                worker,
                "process_activity",
                side_effect=lambda aid, date: {"activity_id": aid},
            ),
        ):
            result = worker.process_activity_by_date("2026-01-01")

        mock_api.assert_called_once_with("2026-01-01")
        assert result["activity_id"] == 111
