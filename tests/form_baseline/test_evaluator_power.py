"""Tests for power efficiency evaluation.

Tests evaluate_power_efficiency function and rating calculation.
"""

from datetime import datetime, timedelta

import duckdb
import pytest


@pytest.fixture
def tmp_db_with_baseline(tmp_path):
    """Create database with baseline and activity data."""
    db_path = str(tmp_path / "test.duckdb")
    conn = duckdb.connect(db_path)

    # Create tables
    conn.execute("CREATE SEQUENCE seq_history_id START 1")
    conn.execute("CREATE SEQUENCE seq_eval_id START 1")

    conn.execute(
        """
        CREATE TABLE activities (
            activity_id INTEGER PRIMARY KEY,
            activity_date DATE,
            body_mass_kg FLOAT
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE splits (
            split_id INTEGER PRIMARY KEY,
            activity_id INTEGER,
            average_speed FLOAT,
            power FLOAT
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE form_baseline_history (
            history_id INTEGER PRIMARY KEY DEFAULT nextval('seq_history_id'),
            user_id VARCHAR DEFAULT 'default',
            condition_group VARCHAR DEFAULT 'flat_road',
            metric VARCHAR,
            period_start DATE,
            period_end DATE,
            power_a FLOAT,
            power_b FLOAT,
            power_rmse FLOAT
        )
    """
    )

    conn.execute(
        """
        CREATE TABLE form_evaluations (
            eval_id INTEGER PRIMARY KEY DEFAULT nextval('seq_eval_id'),
            activity_id INTEGER,
            power_avg_w FLOAT,
            power_wkg FLOAT,
            speed_actual_mps FLOAT,
            speed_expected_mps FLOAT,
            power_efficiency_score FLOAT,
            power_efficiency_rating VARCHAR,
            power_efficiency_needs_improvement BOOLEAN
        )
    """
    )

    # Insert baseline (speed = 1.0 + 0.7 * power_wkg)
    today = datetime.now().date()
    conn.execute(
        """
        INSERT INTO form_baseline_history (user_id, condition_group, metric, period_start, period_end, power_a, power_b, power_rmse)
        VALUES ('default', 'flat_road', 'power', ?, ?, 1.0, 0.7, 0.1)
        """,
        [today - timedelta(days=60), today],
    )

    # Insert activity
    conn.execute(
        "INSERT INTO activities VALUES (1001, ?, 75.0)", [today - timedelta(days=5)]
    )

    # Insert splits with power
    conn.execute("INSERT INTO splits VALUES (10001, 1001, 3.5, 250.0)")  # 3.33 W/kg
    conn.execute("INSERT INTO splits VALUES (10002, 1001, 3.6, 260.0)")  # 3.47 W/kg

    conn.close()
    return db_path


@pytest.mark.integration
def test_evaluate_power_efficiency(tmp_db_with_baseline):
    """パワー効率を評価し、form_evaluationsに挿入."""
    from tools.form_baseline.evaluator import evaluate_power_efficiency

    today = datetime.now().date()
    result = evaluate_power_efficiency(
        activity_id=1001,
        activity_date=str(today - timedelta(days=5)),
        user_id="default",
        condition_group="flat_road",
        db_path=tmp_db_with_baseline,
    )

    assert result is not None
    assert "power_efficiency_score" in result
    assert "power_efficiency_rating" in result

    # Check database insertion
    conn = duckdb.connect(tmp_db_with_baseline, read_only=True)
    row = conn.execute(
        "SELECT power_avg_w, power_wkg, speed_actual_mps, speed_expected_mps, power_efficiency_score, power_efficiency_rating FROM form_evaluations WHERE activity_id = 1001"
    ).fetchone()

    assert row is not None
    assert row[0] > 0  # power_avg_w
    assert row[1] > 0  # power_wkg
    assert row[2] > 0  # speed_actual
    assert row[3] > 0  # speed_expected

    conn.close()


@pytest.mark.integration
def test_evaluate_power_efficiency_no_power(tmp_db_with_baseline):
    """パワーデータなしの場合、Noneを返す."""
    from tools.form_baseline.evaluator import evaluate_power_efficiency

    # Add activity without power
    conn = duckdb.connect(tmp_db_with_baseline)
    today = datetime.now().date()
    conn.execute(
        "INSERT INTO activities VALUES (1002, ?, 75.0)", [today - timedelta(days=3)]
    )
    conn.execute("INSERT INTO splits VALUES (10003, 1002, 3.5, NULL)")
    conn.close()

    result = evaluate_power_efficiency(
        activity_id=1002,
        activity_date=str(today - timedelta(days=3)),
        user_id="default",
        condition_group="flat_road",
        db_path=tmp_db_with_baseline,
    )

    assert result is None


@pytest.mark.unit
def test_power_efficiency_rating_calculation():
    """スコアから星評価を計算."""
    from tools.form_baseline.evaluator import _calculate_power_efficiency_rating

    assert _calculate_power_efficiency_rating(0.06) == "★★★★★"
    assert _calculate_power_efficiency_rating(0.03) == "★★★★☆"
    assert _calculate_power_efficiency_rating(0.0) == "★★★☆☆"
    assert _calculate_power_efficiency_rating(-0.03) == "★★☆☆☆"
    assert _calculate_power_efficiency_rating(-0.06) == "★☆☆☆☆"
