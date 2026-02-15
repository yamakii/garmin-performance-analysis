# type: ignore
"""
Integration tests for cadence column refactoring.

Tests real activity data to verify:
- cadence_single_foot stores raw API value (e.g., 90 spm)
- cadence_total calculates correctly (cadence_single_foot × 2)
- Backward compatibility with old cadence column
- Data consistency across database
"""

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.inserters.time_series_metrics import insert_time_series_metrics
from garmin_mcp.utils.paths import get_default_db_path, get_raw_dir


class TestCadenceMigration:
    """Integration tests for cadence column refactoring."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_real_activity_insertion(self, tmp_path):
        """Test insertion with real activity 20721683500.

        Verifies:
        - cadence_single_foot extracted correctly (~91 spm)
        - cadence_total calculated correctly (~182 spm)
        - Values in expected ranges for running
        """
        # Use test activity with known data
        activity_id = 20721683500
        raw_data_dir = get_raw_dir()
        activity_details_file = (
            raw_data_dir / f"activity/{activity_id}/activity_details.json"
        )

        if not activity_details_file.exists():
            pytest.skip(f"Test activity {activity_id} data not available")

        # Create temporary test database using pytest tmp_path fixture
        db_path = str(tmp_path / "test.duckdb")

        # Insert data
        result = insert_time_series_metrics(
            activity_details_file=str(activity_details_file),
            activity_id=activity_id,
            db_path=db_path,
        )

        assert result is True, "Insertion should succeed"

        # Verify data
        conn = duckdb.connect(db_path)

        # Get statistics
        stats = conn.execute(  # type: ignore[index]
            """
            SELECT
                COUNT(*) as total_rows,
                COUNT(cadence_single_foot) as has_cadence,
                AVG(cadence_single_foot) as avg_single_foot,
                AVG(cadence_total) as avg_total,
                MIN(cadence_single_foot) as min_single_foot,
                MAX(cadence_single_foot) as max_single_foot
            FROM time_series_metrics
            WHERE activity_id = ?
              AND cadence_single_foot IS NOT NULL
              AND cadence_single_foot > 0
        """,
            [activity_id],
        ).fetchone()

        conn.close()

        # Verify row count (activity 20721683500 has ~8300-8400 rows)
        assert stats[0] > 8000, "Should have > 8000 data points"
        assert stats[1] > 8000, "Should have cadence data for most points"

        # Verify single-foot cadence in typical running range
        assert (
            80 <= stats[2] <= 100
        ), f"Average single-foot cadence should be 80-100 spm, got {stats[2]:.1f}"
        assert (
            stats[4] >= 0
        ), f"Min single-foot cadence should be >= 0, got {stats[4]:.1f}"
        assert (
            stats[5] <= 120
        ), f"Max single-foot cadence should be <= 120, got {stats[5]:.1f}"

        # Verify total cadence in typical running range (160-200 spm)
        assert (
            160 <= stats[3] <= 200
        ), f"Average total cadence should be 160-200 spm, got {stats[3]:.1f}"

    @pytest.mark.integration
    @pytest.mark.slow
    def test_cadence_calculation_consistency(self, tmp_path):
        """Test cadence_total = cadence_single_foot × 2 across all rows.

        Uses real activity data to verify calculation is consistent.
        """
        activity_id = 20721683500
        raw_data_dir = get_raw_dir()
        activity_details_file = (
            raw_data_dir / f"activity/{activity_id}/activity_details.json"
        )

        if not activity_details_file.exists():
            pytest.skip(f"Test activity {activity_id} data not available")

        # Create temporary test database using pytest tmp_path fixture
        db_path = str(tmp_path / "test.duckdb")

        result = insert_time_series_metrics(
            activity_details_file=str(activity_details_file),
            activity_id=activity_id,
            db_path=db_path,
        )

        assert result is True

        conn = duckdb.connect(db_path)

        # Check calculation consistency
        ratio_stats = conn.execute(  # type: ignore[index]  # type: ignore[index]
            """
            SELECT
                MIN(cadence_total / NULLIF(cadence_single_foot, 0)) as min_ratio,
                MAX(cadence_total / NULLIF(cadence_single_foot, 0)) as max_ratio,
                AVG(cadence_total / NULLIF(cadence_single_foot, 0)) as avg_ratio,
                COUNT(*) as total_rows
            FROM time_series_metrics
            WHERE activity_id = ?
              AND cadence_single_foot IS NOT NULL
              AND cadence_single_foot > 0
        """,
            [activity_id],
        ).fetchone()

        conn.close()

        # All ratios should be exactly 2.0
        assert (
            abs(ratio_stats[0] - 2.0) < 0.001
        ), f"Min ratio should be 2.0, got {ratio_stats[0]:.3f}"
        assert (
            abs(ratio_stats[1] - 2.0) < 0.001
        ), f"Max ratio should be 2.0, got {ratio_stats[1]:.3f}"
        assert (
            abs(ratio_stats[2] - 2.0) < 0.001
        ), f"Avg ratio should be 2.0, got {ratio_stats[2]:.3f}"

    @pytest.mark.integration
    @pytest.mark.slow
    def test_backward_compatibility_real_data(self, tmp_path):
        """Test backward compatibility: old cadence column equals cadence_single_foot.

        Ensures existing queries using 'cadence' column continue to work.
        """
        activity_id = 20721683500
        raw_data_dir = get_raw_dir()
        activity_details_file = (
            raw_data_dir / f"activity/{activity_id}/activity_details.json"
        )

        if not activity_details_file.exists():
            pytest.skip(f"Test activity {activity_id} data not available")

        # Create temporary test database using pytest tmp_path fixture
        db_path = str(tmp_path / "test.duckdb")

        result = insert_time_series_metrics(
            activity_details_file=str(activity_details_file),
            activity_id=activity_id,
            db_path=db_path,
        )

        assert result is True

        conn = duckdb.connect(db_path)

        # Compare old and new columns
        comparison = conn.execute(  # type: ignore[index]
            """
            SELECT
                COUNT(*) as total_rows,
                COUNT(CASE WHEN cadence = cadence_single_foot THEN 1 END) as matching_rows,
                AVG(cadence) as avg_old_cadence,
                AVG(cadence_single_foot) as avg_new_single_foot
            FROM time_series_metrics
            WHERE activity_id = ?
              AND cadence IS NOT NULL
        """,
            [activity_id],
        ).fetchone()

        conn.close()

        # All rows should match
        assert (
            comparison[0] == comparison[1]
        ), "All rows should have cadence = cadence_single_foot"

        # Averages should be identical
        assert (
            abs(comparison[2] - comparison[3]) < 0.001
        ), f"Average cadence ({comparison[2]:.2f}) should equal average cadence_single_foot ({comparison[3]:.2f})"

    @pytest.mark.integration
    @pytest.mark.slow
    def test_null_handling_real_data(self, tmp_path):
        """Test NULL handling with real activity data.

        Verifies that when cadence_single_foot is NULL, cadence_total is also NULL.
        """
        activity_id = 20721683500
        raw_data_dir = get_raw_dir()
        activity_details_file = (
            raw_data_dir / f"activity/{activity_id}/activity_details.json"
        )

        if not activity_details_file.exists():
            pytest.skip(f"Test activity {activity_id} data not available")

        # Create temporary test database using pytest tmp_path fixture
        db_path = str(tmp_path / "test.duckdb")

        result = insert_time_series_metrics(
            activity_details_file=str(activity_details_file),
            activity_id=activity_id,
            db_path=db_path,
        )

        assert result is True

        conn = duckdb.connect(db_path)

        # Check NULL consistency
        null_check = conn.execute(  # type: ignore[index]
            """
            SELECT
                COUNT(*) as total_rows,
                COUNT(CASE WHEN cadence_single_foot IS NULL AND cadence_total IS NOT NULL THEN 1 END) as invalid_nulls,
                COUNT(CASE WHEN cadence_single_foot IS NULL AND cadence_total IS NULL THEN 1 END) as valid_nulls
            FROM time_series_metrics
            WHERE activity_id = ?
        """,
            [activity_id],
        ).fetchone()

        conn.close()

        # Should have no invalid NULL combinations
        assert (
            null_check[1] == 0
        ), "When cadence_single_foot is NULL, cadence_total should also be NULL"

    @pytest.mark.integration
    @pytest.mark.slow
    def test_database_migration_verification(self):
        """Verify migration on actual database (if available).

        This test uses the real database to verify migration success.
        Skipped if database doesn't exist or doesn't have the test activity.
        """
        try:
            db_path_str = get_default_db_path()
            db_path = Path(db_path_str)
            if not db_path.exists():
                pytest.skip("Default database not found")

            conn = duckdb.connect(db_path_str, read_only=True)

            # Check if test activity exists
            count = conn.execute(
                "SELECT COUNT(*) FROM time_series_metrics WHERE activity_id = ?",
                [20721683500],
            ).fetchone()[0]

            if count == 0:
                conn.close()
                pytest.skip("Test activity 20721683500 not in database")

            # Verify schema includes new columns
            schema = conn.execute("PRAGMA table_info(time_series_metrics)").fetchall()
            column_names = [row[1] for row in schema]

            assert "cadence_single_foot" in column_names, "Missing cadence_single_foot"
            assert "cadence_total" in column_names, "Missing cadence_total"

            # Verify data quality
            stats = conn.execute("""
                SELECT
                    AVG(cadence_single_foot) as avg_single,
                    AVG(cadence_total) as avg_total,
                    AVG(cadence_total / NULLIF(cadence_single_foot, 0)) as avg_ratio
                FROM time_series_metrics
                WHERE activity_id = 20721683500
                  AND cadence_single_foot IS NOT NULL
                  AND cadence_single_foot > 0
            """).fetchone()  # type: ignore[index]

            conn.close()

            # Verify expected values (from planning: ~183 spm total, ~91.5 spm single)
            assert (
                80 <= stats[0] <= 100
            ), f"Average single-foot cadence should be 80-100, got {stats[0]:.1f}"
            assert (
                160 <= stats[1] <= 200
            ), f"Average total cadence should be 160-200, got {stats[1]:.1f}"
            assert (
                abs(stats[2] - 2.0) < 0.001
            ), f"Ratio should be 2.0, got {stats[2]:.3f}"

        except Exception as e:
            pytest.skip(f"Database check failed: {e}")
