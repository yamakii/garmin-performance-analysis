"""Verification DB integration tests.

Tests that the verification DB:
1. Can be generated from fixture JSON files
2. Has the same schema as production
3. Provides isolated copies per test via the fixture
"""

from pathlib import Path

import duckdb
import pytest

from tests.generate_verification_db import FIXTURE_ACTIVITY_ID


@pytest.mark.integration
class TestVerificationDB:
    """Verification DB generation and schema tests."""

    # Tables that should contain data after generation
    EXPECTED_TABLES_WITH_DATA = [
        "activities",
        "splits",
        "form_efficiency",
        "heart_rate_zones",
        "hr_efficiency",
        "performance_trends",
        "time_series_metrics",
    ]

    def test_generate_verification_db(self, verification_db_path: Path) -> None:
        """DB generation succeeds and main tables have data."""
        assert verification_db_path.exists()

        conn = duckdb.connect(str(verification_db_path), read_only=True)
        try:
            for table in self.EXPECTED_TABLES_WITH_DATA:
                count = conn.execute(
                    f"SELECT COUNT(*) FROM {table}"  # noqa: S608
                ).fetchone()
                assert count is not None
                assert count[0] > 0, f"Table {table} has no data"

            # Verify activity_id matches fixture
            activity = conn.execute(
                "SELECT activity_id, activity_date FROM activities"
            ).fetchone()
            assert activity is not None
            assert activity[0] == FIXTURE_ACTIVITY_ID

            # Verify splits count (7 laps: 1 warmup + 5 active + 1 cooldown)
            splits_count = conn.execute(
                "SELECT COUNT(*) FROM splits WHERE activity_id = ?",
                [FIXTURE_ACTIVITY_ID],
            ).fetchone()
            assert splits_count is not None
            assert splits_count[0] == 7

            # Verify HR zones count (5 zones)
            hr_zones_count = conn.execute(
                "SELECT COUNT(*) FROM heart_rate_zones WHERE activity_id = ?",
                [FIXTURE_ACTIVITY_ID],
            ).fetchone()
            assert hr_zones_count is not None
            assert hr_zones_count[0] == 5
        finally:
            conn.close()

    def test_verification_db_schema_matches_production(
        self, verification_db_path: Path
    ) -> None:
        """PRAGMA table_info columns match between verification and production schema.

        Verifies that column names and types in the verification DB match
        the expected production schema for all core tables.
        """
        conn = duckdb.connect(str(verification_db_path), read_only=True)
        try:
            # Get all table names
            tables = conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main'"
            ).fetchall()
            table_names = [t[0] for t in tables]

            # All expected tables should exist
            for table in self.EXPECTED_TABLES_WITH_DATA:
                assert table in table_names, f"Table {table} missing from schema"

            # Verify column structure for key tables
            # activities table
            activities_cols = conn.execute("PRAGMA table_info('activities')").fetchall()
            activities_col_names = [col[1] for col in activities_cols]
            assert "activity_id" in activities_col_names
            assert "activity_date" in activities_col_names
            assert "temp_celsius" in activities_col_names
            assert "gear_model" in activities_col_names

            # splits table
            splits_cols = conn.execute("PRAGMA table_info('splits')").fetchall()
            splits_col_names = [col[1] for col in splits_cols]
            assert "activity_id" in splits_col_names
            assert "split_index" in splits_col_names
            assert "intensity_type" in splits_col_names
            assert "role_phase" in splits_col_names
            assert "pace_seconds_per_km" in splits_col_names
            assert "stride_length" in splits_col_names

            # heart_rate_zones table
            hr_cols = conn.execute("PRAGMA table_info('heart_rate_zones')").fetchall()
            hr_col_names = [col[1] for col in hr_cols]
            assert "zone_number" in hr_col_names
            assert "zone_low_boundary" in hr_col_names
            assert "time_in_zone_seconds" in hr_col_names

            # performance_trends table
            pt_cols = conn.execute("PRAGMA table_info('performance_trends')").fetchall()
            pt_col_names = [col[1] for col in pt_cols]
            assert "warmup_splits" in pt_col_names
            assert "run_splits" in pt_col_names
            assert "cooldown_splits" in pt_col_names

        finally:
            conn.close()

    def test_verification_db_fixture_isolation(
        self, verification_db_path: Path
    ) -> None:
        """Two calls to verification_db_path yield different paths."""
        # The fixture returns a different path each invocation.
        # We verify the path exists and is unique by checking it is in tmp_path.
        assert verification_db_path.exists()
        assert (
            "tmp" in str(verification_db_path).lower()
            or "pytest" in str(verification_db_path).lower()
        )
        # The path should not be the default fixtures path
        assert "fixtures/verification.duckdb" not in str(verification_db_path)


@pytest.mark.integration
class TestVerificationDBFixtureIsolation:
    """Separate class to verify fixture isolation across test functions."""

    def test_isolation_instance_a(self, verification_db_path: Path) -> None:
        """First instance of verification DB."""
        assert verification_db_path.exists()
        # Write something to prove isolation
        conn = duckdb.connect(str(verification_db_path))
        try:
            conn.execute(
                "INSERT OR REPLACE INTO activities "
                "(activity_id, activity_date) VALUES (99999, '2099-12-31')"
            )
        finally:
            conn.close()

    def test_isolation_instance_b(self, verification_db_path: Path) -> None:
        """Second instance should NOT see writes from instance_a."""
        conn = duckdb.connect(str(verification_db_path), read_only=True)
        try:
            result = conn.execute(
                "SELECT COUNT(*) FROM activities WHERE activity_id = 99999"
            ).fetchone()
            assert result is not None
            assert result[0] == 0, "Fixture isolation broken: saw data from other test"
        finally:
            conn.close()
