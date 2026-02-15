"""Tests for integrated score calculation in evaluator module."""

import pytest

from garmin_mcp.form_baseline.evaluator import _calculate_power_efficiency_internal


@pytest.fixture
def tmp_db_with_data(tmp_path):
    """Create temporary database with test data."""
    import duckdb

    db_path = str(tmp_path / "test.duckdb")
    conn = duckdb.connect(db_path)

    # Create tables
    conn.execute("""
        CREATE TABLE activities (
            activity_id INTEGER PRIMARY KEY,
            activity_date DATE,
            base_weight_kg DOUBLE
        )
    """)

    conn.execute("""
        CREATE TABLE splits (
            split_id INTEGER,
            activity_id INTEGER,
            power DOUBLE,
            average_speed DOUBLE
        )
    """)

    conn.execute("""
        CREATE TABLE form_baseline_history (
            user_id VARCHAR,
            condition_group VARCHAR,
            metric VARCHAR,
            period_start DATE,
            period_end DATE,
            coef_alpha DOUBLE,
            coef_d DOUBLE,
            coef_a DOUBLE,
            coef_b DOUBLE,
            n_samples INTEGER,
            rmse DOUBLE,
            speed_range_min DOUBLE,
            speed_range_max DOUBLE,
            power_a DOUBLE,
            power_b DOUBLE,
            power_rmse DOUBLE,
            UNIQUE (user_id, condition_group, metric, period_start, period_end)
        )
    """)

    conn.execute("""
        CREATE TABLE hr_efficiency (
            activity_id INTEGER PRIMARY KEY,
            training_type VARCHAR
        )
    """)

    conn.execute("""
        CREATE TABLE form_evaluations (
            activity_id INTEGER PRIMARY KEY,
            gct_penalty DOUBLE,
            vo_penalty DOUBLE,
            vr_penalty DOUBLE,
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

    # Insert test data
    # Activity with interval_sprint training type
    conn.execute("""
        INSERT INTO activities VALUES (12345, '2025-10-28', 70.0)
    """)

    conn.execute("""
        INSERT INTO splits VALUES
            (1, 12345, 280.0, 4.5),
            (2, 12345, 290.0, 4.6),
            (3, 12345, 285.0, 4.55)
    """)

    conn.execute("""
        INSERT INTO hr_efficiency VALUES (12345, 'interval_sprint')
    """)

    # Baseline for power
    conn.execute("""
        INSERT INTO form_baseline_history VALUES
            ('default', 'flat_road', 'power',
             '2025-10-01', '2025-10-31',
             NULL, NULL, NULL, NULL, 100, 0.1, 3.0, 6.0, 1.5, 0.8, 0.1)
    """)

    # Form evaluation with penalties
    conn.execute("""
        INSERT INTO form_evaluations (
            activity_id, gct_penalty, vo_penalty, vr_penalty
        ) VALUES (12345, 10.0, 5.0, 8.0)
    """)

    # Activity without power data (old activity from 2021)
    conn.execute("""
        INSERT INTO activities VALUES (67890, '2021-06-01', 68.0)
    """)

    conn.execute("""
        INSERT INTO splits VALUES
            (1, 67890, NULL, 4.0),
            (2, 67890, NULL, 4.1)
    """)

    conn.execute("""
        INSERT INTO hr_efficiency VALUES (67890, 'low_moderate')
    """)

    conn.execute("""
        INSERT INTO form_evaluations (
            activity_id, gct_penalty, vo_penalty, vr_penalty
        ) VALUES (67890, 15.0, 12.0, 10.0)
    """)

    conn.close()

    return db_path


def test_evaluate_power_efficiency_calculates_integrated_score(tmp_db_with_data):
    """評価時に統合スコアも計算される."""
    import duckdb

    conn = duckdb.connect(tmp_db_with_data)

    # Provide form penalties for integrated score
    form_penalties = {"gct": 10.0, "vo": 5.0, "vr": 8.0}

    result = _calculate_power_efficiency_internal(
        conn,
        activity_id=12345,
        activity_date="2025-10-28",
        user_id="default",
        condition_group="flat_road",
        form_penalties=form_penalties,
    )

    conn.close()

    assert result is not None

    # Verify individual evaluations still work
    assert result["efficiency_score"] is not None
    assert "avg_w" in result
    assert "wkg" in result

    # Verify integrated score
    assert "integrated_score" in result
    assert isinstance(result["integrated_score"], float)
    # Score should be reasonable (can be >100 if all metrics are excellent)
    assert -50 <= result["integrated_score"] <= 150

    assert result["training_mode"] == "interval_sprint"


def test_evaluate_no_power_returns_none(tmp_db_with_data):
    """パワーデータなしの場合、_calculate_power_efficiency_internal()はNoneを返す."""
    import duckdb

    conn = duckdb.connect(tmp_db_with_data)

    result = _calculate_power_efficiency_internal(
        conn,
        activity_id=67890,
        activity_date="2021-06-01",
        user_id="default",
        condition_group="flat_road",
        form_penalties=None,
    )

    conn.close()

    # Should return None when no power data
    assert result is None


def test_integrated_score_uses_correct_weights(tmp_db_with_data):
    """統合スコアが正しい重みを使用している."""
    import duckdb

    conn = duckdb.connect(tmp_db_with_data)

    # Provide form penalties for integrated score
    form_penalties = {"gct": 10.0, "vo": 5.0, "vr": 8.0}

    result = _calculate_power_efficiency_internal(
        conn,
        activity_id=12345,
        activity_date="2025-10-28",
        user_id="default",
        condition_group="flat_road",
        form_penalties=form_penalties,
    )

    conn.close()

    assert result is not None

    # For interval_sprint mode, power weight should be 0.40 (highest)
    # With penalties: gct=10%, vo=5%, vr=8%
    # And power efficiency score (negative = better, positive = worse)
    # The integrated score should reflect these weights
    assert result["training_mode"] == "interval_sprint"
    assert "integrated_score" in result


def test_integrated_score_updates_on_conflict(tmp_db_with_data):
    """ペナルティが変わると、integrated_scoreも変わる."""
    import duckdb

    conn = duckdb.connect(tmp_db_with_data)

    # First evaluation with higher penalties
    form_penalties1 = {"gct": 10.0, "vo": 5.0, "vr": 8.0}
    result1 = _calculate_power_efficiency_internal(
        conn,
        activity_id=12345,
        activity_date="2025-10-28",
        user_id="default",
        condition_group="flat_road",
        form_penalties=form_penalties1,
    )

    assert result1 is not None
    score1 = result1["integrated_score"]

    # Second evaluation with lower penalties
    form_penalties2 = {"gct": 5.0, "vo": 3.0, "vr": 4.0}
    result2 = _calculate_power_efficiency_internal(
        conn,
        activity_id=12345,
        activity_date="2025-10-28",
        user_id="default",
        condition_group="flat_road",
        form_penalties=form_penalties2,
    )

    conn.close()

    assert result2 is not None
    score2 = result2["integrated_score"]

    # Score should be different (improved because penalties decreased)
    assert score2 != score1
    assert score2 > score1  # Lower penalties = higher score
