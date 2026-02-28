"""Integration tests for FK constraint removal migration.

Test coverage:
- End-to-end migration with all 9 tables
- Dry run mode
- Data preservation across migration
- No FK constraints after migration
- Regenerate script compatibility
"""

import duckdb
import pytest

from garmin_mcp.database.migrations.remove_fk_constraints import (
    migrate_remove_fk_constraints,
)


@pytest.fixture
def production_like_db(tmp_path):
    """Create production-like database with FK constraints."""
    db_path = tmp_path / "production_like.duckdb"
    conn = duckdb.connect(str(db_path))

    # Create activities table (parent)
    conn.execute("""
        CREATE TABLE activities (
            activity_id BIGINT PRIMARY KEY,
            activity_date DATE NOT NULL,
            activity_name VARCHAR,
            total_distance_km DOUBLE,
            avg_pace_seconds_per_km DOUBLE,
            avg_heart_rate INTEGER,
            temp_celsius DOUBLE,
            relative_humidity_percent DOUBLE,
            wind_speed_kmh DOUBLE,
            wind_direction VARCHAR,
            gear_type VARCHAR,
            gear_model VARCHAR,
            base_weight_kg DOUBLE,
            start_time_local TIMESTAMP,
            start_time_gmt TIMESTAMP,
            location_name VARCHAR,
            total_time_seconds INTEGER,
            avg_speed_ms DOUBLE,
            max_heart_rate INTEGER
        )
    """)

    # Create splits table with FK
    conn.execute("""
        CREATE TABLE splits (
            activity_id BIGINT,
            split_index INTEGER,
            distance DOUBLE,
            duration_seconds DOUBLE,
            pace_seconds_per_km DOUBLE,
            heart_rate INTEGER,
            cadence DOUBLE,
            power DOUBLE,
            ground_contact_time DOUBLE,
            vertical_oscillation DOUBLE,
            vertical_ratio DOUBLE,
            elevation_gain DOUBLE,
            elevation_loss DOUBLE,
            start_time_gmt VARCHAR,
            start_time_s INTEGER,
            end_time_s INTEGER,
            intensity_type VARCHAR,
            role_phase VARCHAR,
            pace_str VARCHAR,
            hr_zone VARCHAR,
            cadence_rating VARCHAR,
            power_efficiency VARCHAR,
            stride_length DOUBLE,
            terrain_type VARCHAR,
            environmental_conditions VARCHAR,
            wind_impact VARCHAR,
            temp_impact VARCHAR,
            environmental_impact VARCHAR,
            PRIMARY KEY (activity_id, split_index),
            FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
        )
    """)

    # Create other tables with FK constraints (simplified for testing)
    for table in [
        "form_efficiency",
        "heart_rate_zones",
        "hr_efficiency",
        "performance_trends",
        "vo2_max",
        "lactate_threshold",
        "form_evaluations",
        "section_analyses",
    ]:
        if table == "heart_rate_zones":
            conn.execute(f"""
                CREATE TABLE {table} (
                    activity_id BIGINT,
                    zone_number INTEGER,
                    time_in_zone_seconds DOUBLE,
                    PRIMARY KEY (activity_id, zone_number),
                    FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
                )
            """)
        elif table in ["form_evaluations", "section_analyses"]:
            conn.execute(f"""
                CREATE TABLE {table} (
                    {"eval_id" if table == "form_evaluations" else "analysis_id"} INTEGER PRIMARY KEY,
                    activity_id BIGINT UNIQUE,
                    data VARCHAR,
                    FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
                )
            """)
        else:
            conn.execute(f"""
                CREATE TABLE {table} (
                    activity_id BIGINT PRIMARY KEY,
                    data VARCHAR,
                    FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
                )
            """)

    # Insert sample data
    conn.execute(
        "INSERT INTO activities (activity_id, activity_date, activity_name) VALUES (12345, '2025-10-15', 'Morning Run')"
    )
    conn.execute(
        "INSERT INTO activities (activity_id, activity_date, activity_name) VALUES (67890, '2025-10-16', 'Evening Run')"
    )

    conn.execute(
        "INSERT INTO splits (activity_id, split_index, distance, pace_seconds_per_km) VALUES (12345, 1, 1.0, 300.0)"
    )
    conn.execute(
        "INSERT INTO splits (activity_id, split_index, distance, pace_seconds_per_km) VALUES (12345, 2, 1.0, 295.0)"
    )
    conn.execute(
        "INSERT INTO splits (activity_id, split_index, distance, pace_seconds_per_km) VALUES (67890, 1, 1.0, 310.0)"
    )

    conn.execute("INSERT INTO form_efficiency VALUES (12345, 'test_data')")
    conn.execute("INSERT INTO heart_rate_zones VALUES (12345, 1, 100.0)")
    conn.execute("INSERT INTO heart_rate_zones VALUES (12345, 2, 200.0)")

    conn.close()
    return db_path


@pytest.mark.integration
class TestEndToEndMigration:
    """Test complete migration workflow.

    Note: migrate_remove_fk_constraints(dry_run=False) is deprecated (#100).
    The migration runner uses _wrap_remove_fk (no-op) instead.
    These tests verify the deprecated function raises NotImplementedError.
    """

    def test_migrate_raises_not_implemented(self, production_like_db):
        """Test that non-dry-run migration raises NotImplementedError (deprecated)."""
        with pytest.raises(NotImplementedError, match="deprecated"):
            migrate_remove_fk_constraints(str(production_like_db), dry_run=False)


@pytest.mark.integration
class TestDryRunMode:
    """Test dry run mode."""

    def test_migration_dry_run_no_changes(self, production_like_db):
        """Test that dry run doesn't modify database."""
        conn = duckdb.connect(str(production_like_db))

        # Get table list before dry run
        tables_before = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' ORDER BY table_name"
        ).fetchall()

        # Get row counts before dry run
        counts_before = {}
        for table in ["activities", "splits", "form_efficiency"]:
            _row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            assert _row is not None
            counts_before[table] = _row[0]

        conn.close()

        # Execute dry run
        result = migrate_remove_fk_constraints(str(production_like_db), dry_run=True)

        # Verify dry run result
        assert result["status"] == "dry_run"
        assert len(result["tables"]) == 9

        # Verify no changes to database
        conn = duckdb.connect(str(production_like_db))

        tables_after = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' ORDER BY table_name"
        ).fetchall()
        assert tables_before == tables_after

        for table, count_before in counts_before.items():
            _row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            assert _row is not None
            count_after = _row[0]
            assert count_after == count_before

        # Verify FK constraints still exist (dry run didn't remove them)
        # Try to insert orphaned record - should fail with FK constraint
        with pytest.raises(duckdb.ConstraintException):
            conn.execute(
                "INSERT INTO splits (activity_id, split_index, distance, pace_seconds_per_km) VALUES (99999, 1, 1.0, 300.0)"
            )

        conn.close()


@pytest.mark.integration
class TestRegenerateCompatibility:
    """Test compatibility with regenerate_duckdb.py logic.

    Note: FK-free tables are now created by db_writer._ensure_tables().
    These tests verify deletion works on FK-free tables created by GarminDBWriter.
    """

    def test_regenerate_works_with_fk_free_tables(self, tmp_path):
        """Test that deletion logic works on FK-free tables from _ensure_tables."""
        from garmin_mcp.database.db_writer import GarminDBWriter

        db_path = tmp_path / "test_regenerate.duckdb"
        GarminDBWriter(db_path=str(db_path))

        conn = duckdb.connect(str(db_path))

        # Insert sample data
        conn.execute(
            "INSERT INTO activities (activity_id, activity_date, activity_name) "
            "VALUES (12345, '2025-10-15', 'Morning Run')"
        )
        conn.execute(
            "INSERT INTO activities (activity_id, activity_date, activity_name) "
            "VALUES (67890, '2025-10-16', 'Evening Run')"
        )
        conn.execute("INSERT INTO splits (activity_id, split_index) VALUES (12345, 1)")
        conn.execute("INSERT INTO splits (activity_id, split_index) VALUES (12345, 2)")
        conn.execute("INSERT INTO splits (activity_id, split_index) VALUES (67890, 1)")

        # Delete in arbitrary order (no FK ordering required)
        conn.execute("DELETE FROM splits WHERE activity_id = 12345")

        _row = conn.execute(
            "SELECT COUNT(*) FROM splits WHERE activity_id = 12345"
        ).fetchone()
        assert _row is not None
        assert _row[0] == 0

        _row = conn.execute(
            "SELECT COUNT(*) FROM splits WHERE activity_id = 67890"
        ).fetchone()
        assert _row is not None
        assert _row[0] == 1

        conn.close()
