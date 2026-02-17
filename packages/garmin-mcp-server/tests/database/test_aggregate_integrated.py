"""Tests for integrated score in aggregate reader."""

import pytest

from garmin_mcp.database.readers.form import FormReader


@pytest.fixture
def tmp_db_with_integrated_score(tmp_path):
    """Create temporary database with integrated score data."""
    import duckdb

    db_path = str(tmp_path / "test.duckdb")
    conn = duckdb.connect(db_path)

    # Create form_evaluations table with integrated_score
    conn.execute("""
        CREATE TABLE form_evaluations (
            activity_id INTEGER PRIMARY KEY,
            gct_ms_expected DOUBLE,
            gct_ms_actual DOUBLE,
            gct_delta_pct DOUBLE,
            gct_star_rating VARCHAR,
            gct_score DOUBLE,
            gct_needs_improvement BOOLEAN,
            gct_evaluation_text VARCHAR,
            vo_cm_expected DOUBLE,
            vo_cm_actual DOUBLE,
            vo_delta_cm DOUBLE,
            vo_star_rating VARCHAR,
            vo_score DOUBLE,
            vo_needs_improvement BOOLEAN,
            vo_evaluation_text VARCHAR,
            vr_pct_expected DOUBLE,
            vr_pct_actual DOUBLE,
            vr_delta_pct DOUBLE,
            vr_star_rating VARCHAR,
            vr_score DOUBLE,
            vr_needs_improvement BOOLEAN,
            vr_evaluation_text VARCHAR,
            cadence_actual DOUBLE,
            cadence_minimum INTEGER,
            cadence_achieved BOOLEAN,
            overall_score DOUBLE,
            overall_star_rating VARCHAR,
            power_avg_w DOUBLE,
            power_wkg DOUBLE,
            speed_actual_mps DOUBLE,
            speed_expected_mps DOUBLE,
            power_efficiency_score DOUBLE,
            power_efficiency_rating VARCHAR,
            power_efficiency_needs_improvement BOOLEAN,
            integrated_score DOUBLE,
            training_mode VARCHAR
        )
    """)

    # Insert test data with interval_sprint mode
    conn.execute("""
        INSERT INTO form_evaluations VALUES (
            12345,
            220.0, 225.0, 2.27,
            '★★★★☆', 4.2, FALSE, 'GCT evaluation text',
            8.5, 8.7, 0.2,
            '★★★★☆', 4.1, FALSE, 'VO evaluation text',
            7.0, 7.2, 2.86,
            '★★★★☆', 4.3, FALSE, 'VR evaluation text',
            185.0, 180, TRUE,
            4.5, '★★★★★',
            280.0, 4.0, 4.5, 4.3, 0.05, '★★★★☆', FALSE,
            92.5, 'interval_sprint'
        )
    """)

    # Insert test data with low_moderate mode
    conn.execute("""
        INSERT INTO form_evaluations VALUES (
            67890,
            215.0, 220.0, 2.33,
            '★★★★☆', 4.1, FALSE, 'GCT evaluation text 2',
            8.2, 8.5, 0.3,
            '★★★★☆', 4.0, FALSE, 'VO evaluation text 2',
            6.8, 7.0, 2.94,
            '★★★★☆', 4.2, FALSE, 'VR evaluation text 2',
            182.0, 180, TRUE,
            4.3, '★★★★☆',
            NULL, NULL, NULL, NULL, NULL, NULL, NULL,
            88.0, 'low_moderate'
        )
    """)

    # Insert test data without integrated_score (old format)
    conn.execute("""
        INSERT INTO form_evaluations VALUES (
            11111,
            210.0, 215.0, 2.38,
            '★★★★☆', 4.0, FALSE, 'GCT evaluation text 3',
            8.0, 8.3, 0.3,
            '★★★★☆', 3.9, FALSE, 'VO evaluation text 3',
            6.5, 6.7, 3.08,
            '★★★★☆', 4.1, FALSE, 'VR evaluation text 3',
            180.0, 180, TRUE,
            4.2, '★★★★☆',
            NULL, NULL, NULL, NULL, NULL, NULL, NULL,
            NULL, NULL
        )
    """)

    conn.close()
    return db_path


def test_get_form_evaluations_includes_integrated_score(tmp_db_with_integrated_score):
    """get_form_evaluations()が統合スコアとトレーニングモードを返す."""
    reader = FormReader(tmp_db_with_integrated_score)

    result = reader.get_form_evaluations(12345)

    assert result is not None
    assert "integrated_score" in result
    assert result["integrated_score"] == 92.5
    assert "training_mode" in result
    assert result["training_mode"] == "interval_sprint"

    # Verify other fields still exist
    assert "gct" in result
    assert "vo" in result
    assert "vr" in result
    assert "cadence" in result
    assert "power" in result
    assert "overall_score" in result
    assert result["overall_score"] == 4.5


def test_get_form_evaluations_without_power(tmp_db_with_integrated_score):
    """パワーデータなしでも統合スコアを返す."""
    reader = FormReader(tmp_db_with_integrated_score)

    result = reader.get_form_evaluations(67890)

    assert result is not None
    assert result["integrated_score"] == 88.0
    assert result["training_mode"] == "low_moderate"

    # Power fields should be None
    assert result["power"]["avg_w"] is None
    assert result["power"]["wkg"] is None
    assert result["power"]["efficiency_score"] is None


def test_get_form_evaluations_old_format_without_integrated_score(
    tmp_db_with_integrated_score,
):
    """統合スコアがない古いデータでもNoneを返して他のフィールドは正常."""
    reader = FormReader(tmp_db_with_integrated_score)

    result = reader.get_form_evaluations(11111)

    assert result is not None
    assert result["integrated_score"] is None
    assert result["training_mode"] is None

    # Other fields should still work
    assert result["gct"]["actual"] == 215.0
    assert result["overall_score"] == 4.2
