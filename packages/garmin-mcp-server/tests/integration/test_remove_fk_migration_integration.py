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


class TestEndToEndMigration:
    """Test complete migration workflow."""

    def test_migrate_production_like_db(self, production_like_db):
        """Test migration on production-like database."""
        # Execute migration
        result = migrate_remove_fk_constraints(str(production_like_db), dry_run=False)

        # Verify migration success
        assert result["status"] == "success"
        assert len(result["tables"]) == 9
        assert "verification" in result

        # Verify all tables migrated
        expected_tables = [
            "splits",
            "form_efficiency",
            "heart_rate_zones",
            "hr_efficiency",
            "performance_trends",
            "vo2_max",
            "lactate_threshold",
            "form_evaluations",
            "section_analyses",
        ]
        for table in expected_tables:
            assert table in result["tables"]

    def test_data_integrity_after_migration(self, production_like_db):
        """Test that all data is preserved after migration."""
        conn = duckdb.connect(str(production_like_db))

        # Get counts before migration
        counts_before = {}
        for table in [
            "activities",
            "splits",
            "form_efficiency",
            "heart_rate_zones",
        ]:
            counts_before[table] = conn.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]

        conn.close()

        # Execute migration
        migrate_remove_fk_constraints(str(production_like_db), dry_run=False)

        # Verify counts after migration
        conn = duckdb.connect(str(production_like_db))
        for table, count_before in counts_before.items():
            count_after = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            assert (
                count_after == count_before
            ), f"{table}: {count_after} != {count_before}"

        # Verify specific data
        splits_data = conn.execute(
            "SELECT activity_id, split_index, pace_seconds_per_km FROM splits ORDER BY activity_id, split_index"
        ).fetchall()
        assert len(splits_data) == 3
        assert splits_data[0] == (12345, 1, 300.0)
        assert splits_data[1] == (12345, 2, 295.0)
        assert splits_data[2] == (67890, 1, 310.0)

        conn.close()

    def test_queries_work_after_migration(self, production_like_db):
        """Test that LEFT JOIN queries work after migration."""
        # Execute migration
        migrate_remove_fk_constraints(str(production_like_db), dry_run=False)

        conn = duckdb.connect(str(production_like_db))

        # Test LEFT JOIN (should work with or without FK)
        result = conn.execute("""
            SELECT a.activity_id, a.activity_name, COUNT(s.split_index) as split_count
            FROM activities a
            LEFT JOIN splits s ON a.activity_id = s.activity_id
            GROUP BY a.activity_id, a.activity_name
            ORDER BY a.activity_id
        """).fetchall()

        assert len(result) == 2
        assert result[0] == (12345, "Morning Run", 2)
        assert result[1] == (67890, "Evening Run", 1)

        conn.close()

    def test_no_fk_constraints_after_migration(self, production_like_db):
        """Test that no FK constraints exist after migration."""
        # Execute migration
        migrate_remove_fk_constraints(str(production_like_db), dry_run=False)

        conn = duckdb.connect(str(production_like_db))

        # Test orphaned record insertion (should succeed with no FK)
        # Insert record with non-existent activity_id
        conn.execute(
            "INSERT INTO splits (activity_id, split_index, distance, pace_seconds_per_km) VALUES (99999, 1, 1.0, 300.0)"
        )

        # Verify insertion succeeded
        count = conn.execute(
            "SELECT COUNT(*) FROM splits WHERE activity_id = 99999"
        ).fetchone()[0]
        assert count == 1  # Orphaned record exists (no FK constraint)

        conn.close()


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
            counts_before[table] = conn.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]

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
            count_after = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            assert count_after == count_before

        # Verify FK constraints still exist (dry run didn't remove them)
        # Try to insert orphaned record - should fail with FK constraint
        with pytest.raises(duckdb.ConstraintException):
            conn.execute(
                "INSERT INTO splits (activity_id, split_index, distance, pace_seconds_per_km) VALUES (99999, 1, 1.0, 300.0)"
            )

        conn.close()


class TestRegenerateCompatibility:
    """Test compatibility with regenerate_duckdb.py logic."""

    def test_regenerate_works_after_migration(self, production_like_db):
        """Test that deletion logic works after FK removal."""
        # Execute migration
        migrate_remove_fk_constraints(str(production_like_db), dry_run=False)

        conn = duckdb.connect(str(production_like_db))

        # Simulate regenerate_duckdb.py deletion (any order, no FK constraints)
        activity_ids_to_delete = [12345]

        # Delete from tables in arbitrary order (no FK ordering required)
        for table in ["splits", "form_efficiency", "heart_rate_zones"]:
            if table == "heart_rate_zones":
                conn.execute(
                    f"DELETE FROM {table} WHERE activity_id IN ({','.join(map(str, activity_ids_to_delete))})"
                )
            elif table in ["form_evaluations", "section_analyses"]:
                # These tables might not have data, so skip if they don't exist
                try:
                    conn.execute(
                        f"DELETE FROM {table} WHERE activity_id IN ({','.join(map(str, activity_ids_to_delete))})"
                    )
                except Exception:
                    pass
            else:
                conn.execute(
                    f"DELETE FROM {table} WHERE activity_id IN ({','.join(map(str, activity_ids_to_delete))})"
                )

        # Verify deletions
        splits_count = conn.execute(
            "SELECT COUNT(*) FROM splits WHERE activity_id = 12345"
        ).fetchone()[0]
        assert splits_count == 0

        # Verify other activity still exists
        splits_count_other = conn.execute(
            "SELECT COUNT(*) FROM splits WHERE activity_id = 67890"
        ).fetchone()[0]
        assert splits_count_other == 1

        conn.close()

    def test_no_orphaned_records(self, production_like_db):
        """Test that LEFT JOIN detects no orphaned records after migration."""
        # Execute migration
        migrate_remove_fk_constraints(str(production_like_db), dry_run=False)

        conn = duckdb.connect(str(production_like_db))

        # Check for orphaned splits (splits without matching activity)
        orphaned_splits = conn.execute("""
            SELECT s.activity_id
            FROM splits s
            LEFT JOIN activities a ON s.activity_id = a.activity_id
            WHERE a.activity_id IS NULL
        """).fetchall()

        assert len(orphaned_splits) == 0

        conn.close()
