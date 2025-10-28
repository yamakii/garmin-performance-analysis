"""Test Phase 2 schema extensions for integrated score and training mode."""

import duckdb
import pytest


@pytest.fixture
def tmp_db_path(tmp_path):
    """Create a temporary DuckDB database with base schema."""
    db_path = tmp_path / "test_phase2.duckdb"
    conn = duckdb.connect(str(db_path))

    # Create form_evaluations table with Phase 1 columns
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS form_evaluations (
            activity_id INTEGER PRIMARY KEY,
            activity_date VARCHAR,
            gct_actual DOUBLE,
            gct_expected DOUBLE,
            power_avg_w DOUBLE,
            power_wkg DOUBLE,
            speed_actual_mps DOUBLE,
            speed_expected_mps DOUBLE,
            power_efficiency_score DOUBLE,
            power_efficiency_rating VARCHAR,
            power_efficiency_needs_improvement BOOLEAN
        )
    """
    )

    conn.close()

    # Run Phase 2 migration
    from tools.database.migrations.phase2_integrated_score import migrate_phase2_schema

    migrate_phase2_schema(str(db_path))

    return str(db_path)


@pytest.mark.unit
def test_form_evaluations_has_integrated_score_columns(tmp_db_path):
    """integrated_score, training_mode columns should exist in form_evaluations."""
    conn = duckdb.connect(tmp_db_path, read_only=True)

    # Get schema information
    schema = conn.execute("PRAGMA table_info(form_evaluations)").fetchall()
    column_names = [row[1] for row in schema]

    # Assert integrated_score and training_mode columns exist
    assert "integrated_score" in column_names, "integrated_score column should exist"
    assert "training_mode" in column_names, "training_mode column should exist"

    conn.close()


@pytest.mark.unit
def test_integrated_score_column_type(tmp_db_path):
    """integrated_score should be DOUBLE type."""
    conn = duckdb.connect(tmp_db_path, read_only=True)

    schema = conn.execute("PRAGMA table_info(form_evaluations)").fetchall()

    # Find integrated_score column
    integrated_score_col = [row for row in schema if row[1] == "integrated_score"]
    assert len(integrated_score_col) == 1, "integrated_score column should exist"

    # Check type (row[2] is type)
    col_type = integrated_score_col[0][2]
    assert (
        col_type.upper() == "DOUBLE"
    ), f"integrated_score should be DOUBLE, got {col_type}"

    conn.close()


@pytest.mark.unit
def test_training_mode_column_type(tmp_db_path):
    """training_mode should be VARCHAR type."""
    conn = duckdb.connect(tmp_db_path, read_only=True)

    schema = conn.execute("PRAGMA table_info(form_evaluations)").fetchall()

    # Find training_mode column
    training_mode_col = [row for row in schema if row[1] == "training_mode"]
    assert len(training_mode_col) == 1, "training_mode column should exist"

    # Check type (row[2] is type)
    col_type = training_mode_col[0][2]
    assert (
        col_type.upper() == "VARCHAR"
    ), f"training_mode should be VARCHAR, got {col_type}"

    conn.close()
