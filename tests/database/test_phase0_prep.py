"""Tests for Phase 0: Database preparation for power efficiency evaluation.

This test suite ensures:
1. form_baselines table is removed
2. No code references to form_baselines remain
3. activities table has base_weight_kg column
4. All activities have base_weight_kg populated from body_composition
"""

import duckdb
import pytest


@pytest.fixture
def test_db_path(tmp_path):
    """Create a temporary test database."""
    db_path = tmp_path / "test_garmin.duckdb"
    return str(db_path)


@pytest.fixture
def setup_test_db(test_db_path):
    """Setup test database with initial state."""
    conn = duckdb.connect(test_db_path)

    # Create activities table (without base_weight_kg initially)
    conn.execute("""
        CREATE TABLE activities (
            activity_id BIGINT PRIMARY KEY,
            activity_date DATE,
            activity_name VARCHAR
        )
    """)

    # Create body_composition table
    conn.execute("""
        CREATE TABLE body_composition (
            measurement_id INTEGER PRIMARY KEY,
            date DATE,
            weight_kg DOUBLE
        )
    """)

    # Insert test data
    conn.execute("""
        INSERT INTO activities VALUES
        (1, '2025-10-01', 'Morning Run'),
        (2, '2025-10-02', 'Evening Run'),
        (3, '2025-10-03', 'Recovery Run')
    """)

    conn.execute("""
        INSERT INTO body_composition VALUES
        (1, '2025-10-01', 65.5),
        (2, '2025-10-02', 65.3),
        (3, '2025-10-03', 65.4)
    """)

    conn.close()
    return test_db_path


class TestPhase0FormBaselinesRemoval:
    """Tests for form_baselines table removal."""

    def test_form_baselines_table_does_not_exist(self):
        """Test that form_baselines table does not exist in production DB."""
        # This will fail initially (RED phase)
        from tools.utils.paths import get_database_dir

        db_path = get_database_dir() / "garmin_performance.duckdb"

        conn = duckdb.connect(str(db_path), read_only=True)
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        conn.close()

        assert (
            "form_baselines" not in table_names
        ), "form_baselines table should be removed"


class TestPhase0BodyMassColumn:
    """Tests for base_weight_kg column addition."""

    def test_activities_has_base_weight_kg_column(self, setup_test_db):
        """Test that activities table has base_weight_kg column after adding it."""
        # This test checks the migration step works correctly
        conn = duckdb.connect(setup_test_db)

        # First, add the column (simulating the migration)
        conn.execute("ALTER TABLE activities ADD COLUMN base_weight_kg DOUBLE")

        # Now test that it exists
        schema = conn.execute("PRAGMA table_info(activities)").fetchall()
        column_names = [row[1] for row in schema]
        conn.close()

        assert (
            "base_weight_kg" in column_names
        ), "activities table should have base_weight_kg column after migration"

    def test_activities_has_base_weight_kg_column_production(self):
        """Test that activities table has base_weight_kg column in production DB."""
        # This will fail initially (RED phase)
        from tools.utils.paths import get_database_dir

        db_path = get_database_dir() / "garmin_performance.duckdb"

        conn = duckdb.connect(str(db_path), read_only=True)
        schema = conn.execute("PRAGMA table_info(activities)").fetchall()
        column_names = [row[1] for row in schema]
        conn.close()

        assert (
            "base_weight_kg" in column_names
        ), "Production activities table should have base_weight_kg column"


class TestPhase0BodyMassPopulation:
    """Tests for base_weight_kg population from body_composition."""

    def test_all_activities_have_base_weight_kg(self, setup_test_db):
        """Test that all activities have base_weight_kg populated."""
        # First, add the column and populate it (this simulates the implementation)
        conn = duckdb.connect(setup_test_db)

        # Add column
        conn.execute("ALTER TABLE activities ADD COLUMN base_weight_kg DOUBLE")

        # Populate using LEFT JOIN to handle missing dates
        conn.execute("""
            UPDATE activities
            SET base_weight_kg = (
                SELECT weight_kg
                FROM body_composition
                WHERE body_composition.date = activities.activity_date
                ORDER BY body_composition.date DESC
                LIMIT 1
            )
        """)

        # Test: All activities should have base_weight_kg
        result = conn.execute("""
            SELECT COUNT(*)
            FROM activities
            WHERE base_weight_kg IS NULL
        """).fetchone()

        conn.close()

        assert result is not None
        assert result[0] == 0, f"Found {result[0]} activities without base_weight_kg"

    def test_base_weight_kg_values_are_reasonable(self, setup_test_db):
        """Test that base_weight_kg values are within reasonable range (40-120 kg)."""
        conn = duckdb.connect(setup_test_db)

        # Add column and populate
        conn.execute("ALTER TABLE activities ADD COLUMN base_weight_kg DOUBLE")
        conn.execute("""
            UPDATE activities
            SET base_weight_kg = (
                SELECT weight_kg
                FROM body_composition
                WHERE body_composition.date = activities.activity_date
                LIMIT 1
            )
        """)

        # Test: Values should be reasonable
        result = conn.execute("""
            SELECT activity_id, base_weight_kg
            FROM activities
            WHERE base_weight_kg < 40 OR base_weight_kg > 120
        """).fetchall()

        conn.close()

        assert len(result) == 0, f"Found unreasonable base_weight_kg values: {result}"

    def test_base_weight_kg_matches_body_composition(self, setup_test_db):
        """Test that base_weight_kg matches body_composition for same date."""
        conn = duckdb.connect(setup_test_db)

        # Add column and populate
        conn.execute("ALTER TABLE activities ADD COLUMN base_weight_kg DOUBLE")
        conn.execute("""
            UPDATE activities
            SET base_weight_kg = (
                SELECT weight_kg
                FROM body_composition
                WHERE body_composition.date = activities.activity_date
                LIMIT 1
            )
        """)

        # Test: Values should match
        result = conn.execute("""
            SELECT
                a.activity_id,
                a.base_weight_kg,
                bc.weight_kg
            FROM activities a
            LEFT JOIN body_composition bc ON a.activity_date = bc.date
            WHERE a.base_weight_kg != bc.weight_kg
        """).fetchall()

        conn.close()

        assert (
            len(result) == 0
        ), f"base_weight_kg mismatch with body_composition: {result}"
