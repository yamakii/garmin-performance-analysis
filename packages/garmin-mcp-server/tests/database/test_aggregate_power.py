"""
Integration tests for power efficiency data in AggregateReader.get_form_evaluations().

Tests verify that power efficiency metrics are included in form_evaluations
for activities with power data (2025+) and properly handled for activities
without power data (2021).
"""

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.readers.aggregate import AggregateReader


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> str:
    """Create temporary DuckDB database with form_evaluations table."""
    db_path = str(tmp_path / "test_garmin.duckdb")

    conn = duckdb.connect(db_path)

    # Create activities table (referenced by form_evaluations FK)
    conn.execute("""
        CREATE TABLE activities (
            activity_id BIGINT PRIMARY KEY,
            date DATE NOT NULL
        )
        """)

    # Create form_evaluations table with power efficiency columns
    conn.execute("""
        CREATE TABLE form_evaluations (
            eval_id INTEGER PRIMARY KEY,
            activity_id BIGINT UNIQUE,

            gct_ms_expected FLOAT,
            vo_cm_expected FLOAT,
            vr_pct_expected FLOAT,

            gct_ms_actual FLOAT,
            vo_cm_actual FLOAT,
            vr_pct_actual FLOAT,

            gct_delta_pct FLOAT,
            vo_delta_cm FLOAT,
            vr_delta_pct FLOAT,

            gct_penalty FLOAT,
            gct_star_rating VARCHAR,
            gct_score FLOAT,
            gct_needs_improvement BOOLEAN,
            gct_evaluation_text TEXT,

            vo_penalty FLOAT,
            vo_star_rating VARCHAR,
            vo_score FLOAT,
            vo_needs_improvement BOOLEAN,
            vo_evaluation_text TEXT,

            vr_penalty FLOAT,
            vr_star_rating VARCHAR,
            vr_score FLOAT,
            vr_needs_improvement BOOLEAN,
            vr_evaluation_text TEXT,

            cadence_actual FLOAT,
            cadence_minimum INTEGER DEFAULT 180,
            cadence_achieved BOOLEAN,

            overall_score FLOAT,
            overall_star_rating VARCHAR,

            power_avg_w FLOAT,
            power_wkg FLOAT,
            speed_actual_mps FLOAT,
            speed_expected_mps FLOAT,
            power_efficiency_score FLOAT,
            power_efficiency_rating VARCHAR,
            power_efficiency_needs_improvement BOOLEAN,

            integrated_score DOUBLE,
            training_mode VARCHAR,

            evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
        )
        """)

    conn.close()

    return db_path


@pytest.mark.integration
def test_get_form_evaluations_includes_power_data(tmp_db_path: str):
    """form_evaluations includes power efficiency data for 2025 activity."""
    # Setup: Insert activity with power data (2025)
    conn = duckdb.connect(tmp_db_path)

    # Insert activity
    conn.execute("""
        INSERT INTO activities (activity_id, date)
        VALUES (20594901208, '2025-10-05')
        """)

    # Insert form_evaluations with power data
    conn.execute("""
        INSERT INTO form_evaluations (
            eval_id, activity_id,
            gct_ms_expected, gct_ms_actual, gct_delta_pct,
            gct_star_rating, gct_score, gct_needs_improvement,
            gct_evaluation_text,
            vo_cm_expected, vo_cm_actual, vo_delta_cm,
            vo_star_rating, vo_score, vo_needs_improvement,
            vo_evaluation_text,
            vr_pct_expected, vr_pct_actual, vr_delta_pct,
            vr_star_rating, vr_score, vr_needs_improvement,
            vr_evaluation_text,
            cadence_actual, cadence_minimum, cadence_achieved,
            overall_score, overall_star_rating,
            power_avg_w, power_wkg, speed_actual_mps, speed_expected_mps,
            power_efficiency_score, power_efficiency_rating,
            power_efficiency_needs_improvement
        ) VALUES (
            1, 20594901208,
            250.0, 248.5, -0.6,
            '★★★★★', 1.0, FALSE,
            'GCT is excellent',
            9.5, 9.2, -0.3,
            '★★★★★', 1.0, FALSE,
            'VO is excellent',
            7.8, 7.5, -3.8,
            '★★★★★', 1.0, FALSE,
            'VR is excellent',
            185.0, 180, TRUE,
            0.95, '★★★★★',
            280.0, 4.3, 3.5, 3.6,
            -0.027, '★★★★☆', TRUE
        )
        """)

    conn.close()

    # Test: Read form_evaluations with AggregateReader
    reader = AggregateReader(tmp_db_path)
    result = reader.get_form_evaluations(20594901208)

    # Assert: Result includes power section with all 7 fields
    assert result is not None
    assert "power" in result

    power = result["power"]
    assert power["avg_w"] == pytest.approx(280.0, rel=1e-3)
    assert power["wkg"] == pytest.approx(4.3, rel=1e-3)
    assert power["speed_actual_mps"] == pytest.approx(3.5, rel=1e-3)
    assert power["speed_expected_mps"] == pytest.approx(3.6, rel=1e-3)
    assert power["efficiency_score"] == pytest.approx(-0.027, rel=1e-3)
    assert power["star_rating"] == "★★★★☆"
    assert power["needs_improvement"] is True

    # Verify existing fields are not broken
    assert result["gct"]["actual"] == pytest.approx(248.5, rel=1e-3)
    assert result["overall_score"] == pytest.approx(0.95, rel=1e-3)


@pytest.mark.integration
def test_get_form_evaluations_no_power_data(tmp_db_path: str):
    """form_evaluations includes power key with None values for 2021 activity."""
    # Setup: Insert activity without power data (2021)
    conn = duckdb.connect(tmp_db_path)

    # Insert activity
    conn.execute("""
        INSERT INTO activities (activity_id, date)
        VALUES (12345678901, '2021-06-15')
        """)

    # Insert form_evaluations without power data (NULLs)
    conn.execute("""
        INSERT INTO form_evaluations (
            eval_id, activity_id,
            gct_ms_expected, gct_ms_actual, gct_delta_pct,
            gct_star_rating, gct_score, gct_needs_improvement,
            gct_evaluation_text,
            vo_cm_expected, vo_cm_actual, vo_delta_cm,
            vo_star_rating, vo_score, vo_needs_improvement,
            vo_evaluation_text,
            vr_pct_expected, vr_pct_actual, vr_delta_pct,
            vr_star_rating, vr_score, vr_needs_improvement,
            vr_evaluation_text,
            cadence_actual, cadence_minimum, cadence_achieved,
            overall_score, overall_star_rating,
            power_avg_w, power_wkg, speed_actual_mps, speed_expected_mps,
            power_efficiency_score, power_efficiency_rating,
            power_efficiency_needs_improvement
        ) VALUES (
            2, 12345678901,
            260.0, 255.0, -1.9,
            '★★★★★', 1.0, FALSE,
            'GCT is good',
            9.8, 9.5, -0.3,
            '★★★★★', 1.0, FALSE,
            'VO is good',
            8.0, 7.8, -2.5,
            '★★★★★', 1.0, FALSE,
            'VR is good',
            182.0, 180, TRUE,
            0.92, '★★★★★',
            NULL, NULL, NULL, NULL,
            NULL, NULL, NULL
        )
        """)

    conn.close()

    # Test: Read form_evaluations with AggregateReader
    reader = AggregateReader(tmp_db_path)
    result = reader.get_form_evaluations(12345678901)

    # Assert: Result includes power key but all values are None
    assert result is not None
    assert "power" in result

    power = result["power"]
    assert power["avg_w"] is None
    assert power["wkg"] is None
    assert power["speed_actual_mps"] is None
    assert power["speed_expected_mps"] is None
    assert power["efficiency_score"] is None
    assert power["star_rating"] is None
    assert power["needs_improvement"] is None

    # Verify existing fields are not broken
    assert result["gct"]["actual"] == pytest.approx(255.0, rel=1e-3)
    assert result["overall_score"] == pytest.approx(0.92, rel=1e-3)
