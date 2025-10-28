"""Tests for Phase 1 database schema migration.

Tests verify that power efficiency columns are added to:
- form_baseline_history (power_a, power_b, power_rmse)
- form_evaluations (power efficiency evaluation columns)
"""

import os

import duckdb
import pytest


@pytest.fixture
def db_path():
    """Get database path from environment."""
    data_dir = os.getenv("GARMIN_DATA_DIR", "data")
    return f"{data_dir}/database/garmin_performance.duckdb"


@pytest.mark.integration
def test_form_baseline_history_has_power_columns(db_path):
    """form_baseline_historyにpower_a, power_b, power_rmse列が存在する."""
    conn = duckdb.connect(db_path, read_only=True)

    # Get column names
    columns = conn.execute("DESCRIBE form_baseline_history").fetchall()
    column_names = [col[0] for col in columns]

    # Assert power columns exist
    assert "power_a" in column_names, "power_a column should exist"
    assert "power_b" in column_names, "power_b column should exist"
    assert "power_rmse" in column_names, "power_rmse column should exist"

    conn.close()


@pytest.mark.integration
def test_form_evaluations_has_power_columns(db_path):
    """form_evaluationsにパワー効率列が存在する."""
    conn = duckdb.connect(db_path, read_only=True)

    # Get column names
    columns = conn.execute("DESCRIBE form_evaluations").fetchall()
    column_names = [col[0] for col in columns]

    # Assert power efficiency columns exist
    expected_columns = [
        "power_avg_w",
        "power_wkg",
        "speed_actual_mps",
        "speed_expected_mps",
        "power_efficiency_score",
        "power_efficiency_rating",
        "power_efficiency_needs_improvement",
    ]

    for col in expected_columns:
        assert col in column_names, f"{col} column should exist"

    conn.close()


@pytest.mark.integration
def test_form_baseline_history_power_columns_types(db_path):
    """Power columns have correct data types."""
    conn = duckdb.connect(db_path, read_only=True)

    columns = conn.execute("DESCRIBE form_baseline_history").fetchall()
    column_dict = {col[0]: col[1] for col in columns}

    assert column_dict["power_a"] == "FLOAT", "power_a should be FLOAT"
    assert column_dict["power_b"] == "FLOAT", "power_b should be FLOAT"
    assert column_dict["power_rmse"] == "FLOAT", "power_rmse should be FLOAT"

    conn.close()


@pytest.mark.integration
def test_form_evaluations_power_columns_types(db_path):
    """Power efficiency columns have correct data types."""
    conn = duckdb.connect(db_path, read_only=True)

    columns = conn.execute("DESCRIBE form_evaluations").fetchall()
    column_dict = {col[0]: col[1] for col in columns}

    assert column_dict["power_avg_w"] == "FLOAT", "power_avg_w should be FLOAT"
    assert column_dict["power_wkg"] == "FLOAT", "power_wkg should be FLOAT"
    assert (
        column_dict["speed_actual_mps"] == "FLOAT"
    ), "speed_actual_mps should be FLOAT"
    assert (
        column_dict["speed_expected_mps"] == "FLOAT"
    ), "speed_expected_mps should be FLOAT"
    assert (
        column_dict["power_efficiency_score"] == "FLOAT"
    ), "power_efficiency_score should be FLOAT"
    assert (
        column_dict["power_efficiency_rating"] == "VARCHAR"
    ), "power_efficiency_rating should be VARCHAR"
    assert (
        column_dict["power_efficiency_needs_improvement"] == "BOOLEAN"
    ), "power_efficiency_needs_improvement should be BOOLEAN"

    conn.close()
