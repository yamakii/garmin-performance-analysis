"""Tests for power efficiency evaluation.

Tests evaluate_power_efficiency function and rating calculation.
"""

from datetime import datetime, timedelta

import duckdb
import pytest

from garmin_mcp.form_baseline.power_calculator import (
    calculate_power_efficiency_internal,
    calculate_power_efficiency_rating,
)


@pytest.fixture
def tmp_db_with_baseline(tmp_path):
    """Create database with baseline and activity data."""
    db_path = str(tmp_path / "test.duckdb")
    conn = duckdb.connect(db_path)

    # Create tables
    conn.execute("CREATE SEQUENCE seq_history_id START 1")
    conn.execute("CREATE SEQUENCE seq_eval_id START 1")

    conn.execute("""
        CREATE TABLE activities (
            activity_id INTEGER PRIMARY KEY,
            activity_date DATE,
            base_weight_kg FLOAT
        )
    """)

    conn.execute("""
        CREATE TABLE splits (
            split_id INTEGER PRIMARY KEY,
            activity_id INTEGER,
            average_speed FLOAT,
            grade_adjusted_speed FLOAT,
            power FLOAT,
            role_phase VARCHAR
        )
    """)

    conn.execute("""
        CREATE TABLE form_baseline_history (
            history_id INTEGER PRIMARY KEY DEFAULT nextval('seq_history_id'),
            user_id VARCHAR DEFAULT 'default',
            condition_group VARCHAR DEFAULT 'flat_road',
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
            power_rmse DOUBLE
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
            eval_id INTEGER PRIMARY KEY DEFAULT nextval('seq_eval_id'),
            activity_id INTEGER UNIQUE,
            gct_penalty DOUBLE,
            vo_penalty DOUBLE,
            vr_penalty DOUBLE,
            power_avg_w FLOAT,
            power_wkg FLOAT,
            speed_actual_mps FLOAT,
            speed_expected_mps FLOAT,
            power_efficiency_score FLOAT,
            power_efficiency_rating VARCHAR,
            power_efficiency_needs_improvement BOOLEAN,
            integrated_score DOUBLE,
            training_mode VARCHAR
        )
    """)

    # Insert baseline (speed = 1.0 + 0.7 * power_wkg)
    today = datetime.now().date()
    conn.execute(
        """
        INSERT INTO form_baseline_history (user_id, condition_group, metric, period_start, period_end, power_a, power_b, power_rmse, n_samples, speed_range_min, speed_range_max)
        VALUES ('default', 'flat_road', 'power', ?, ?, 1.0, 0.7, 0.1, 100, 3.0, 6.0)
        """,
        [today - timedelta(days=60), today],
    )

    # Insert activity
    conn.execute(
        "INSERT INTO activities VALUES (1001, ?, 75.0)", [today - timedelta(days=5)]
    )

    # Insert hr_efficiency (training type)
    conn.execute("INSERT INTO hr_efficiency VALUES (1001, 'low_moderate')")

    # Insert run splits with power. grade_adjusted_speed is the GAP input used
    # for evaluation; average_speed is set to a different value to ensure GAP
    # (not average_speed) drives speed_actual.
    # split_id, activity_id, average_speed, grade_adjusted_speed, power, role_phase
    conn.execute(
        "INSERT INTO splits VALUES (10001, 1001, 9.0, 3.5, 250.0, 'run')"
    )  # 3.33 W/kg
    conn.execute(
        "INSERT INTO splits VALUES (10002, 1001, 9.0, 3.6, 260.0, 'run')"
    )  # 3.47 W/kg

    conn.close()
    return db_path


@pytest.mark.integration
def test_evaluate_power_efficiency(tmp_db_with_baseline):
    """パワー効率の計算が正しく動作する."""
    import duckdb

    today = datetime.now().date()
    conn = duckdb.connect(tmp_db_with_baseline)

    form_penalties = {"gct": 10.0, "vo": 5.0, "vr": 8.0}
    result = calculate_power_efficiency_internal(
        conn,
        activity_id=1001,
        activity_date=str(today - timedelta(days=5)),
        user_id="default",
        condition_group="flat_road",
        form_penalties=form_penalties,
    )

    conn.close()

    assert result is not None
    assert "efficiency_score" in result
    assert "star_rating" in result
    assert "integrated_score" in result
    assert result["integrated_score"] is not None
    assert result["avg_w"] > 0
    assert result["wkg"] > 0
    assert result["speed_actual_mps"] > 0
    assert result["speed_expected_mps"] > 0


@pytest.mark.integration
def test_evaluate_power_efficiency_no_power(tmp_db_with_baseline):
    """パワーデータなしの場合、Noneを返す."""
    import duckdb

    # Add activity without power
    conn = duckdb.connect(tmp_db_with_baseline)
    today = datetime.now().date()
    conn.execute(
        "INSERT INTO activities VALUES (1002, ?, 75.0)", [today - timedelta(days=3)]
    )
    conn.execute("INSERT INTO splits VALUES (10003, 1002, 9.0, 3.5, NULL, 'run')")

    result = calculate_power_efficiency_internal(
        conn,
        activity_id=1002,
        activity_date=str(today - timedelta(days=3)),
        user_id="default",
        condition_group="flat_road",
        form_penalties=None,
    )

    conn.close()

    assert result is None  # No power data available


@pytest.mark.integration
def test_power_eval_uses_gap_and_run_only(tmp_db_with_baseline):
    """speed_actual は run スプリットの GAP 平均で算出される.

    既存の run スプリット (GAP 3.5, 3.6 → 平均 3.55) に加え、
    cooldown/warmup スプリットと GAP=NULL の run スプリットを投入しても、
    speed_actual は run かつ GAP 非null の平均 3.55 のまま（average_speed=9.0
    や非定常・null スプリットは無視）であることを検証する。
    """
    conn = duckdb.connect(tmp_db_with_baseline)
    # Non-run splits with off-model GAP that must be ignored.
    conn.execute("INSERT INTO splits VALUES (10004, 1001, 9.0, 6.0, 300.0, 'cooldown')")
    conn.execute("INSERT INTO splits VALUES (10005, 1001, 9.0, 6.0, 300.0, 'warmup')")
    # Run split with GAP=NULL must be ignored (power present).
    conn.execute("INSERT INTO splits VALUES (10006, 1001, 9.0, NULL, 300.0, 'run')")

    today = datetime.now().date()
    result = calculate_power_efficiency_internal(
        conn,
        activity_id=1001,
        activity_date=str(today - timedelta(days=5)),
        user_id="default",
        condition_group="flat_road",
        form_penalties=None,
    )

    conn.close()

    assert result is not None
    # GAP average of run splits = (3.5 + 3.6) / 2 = 3.55, not average_speed (9.0)
    # and not affected by the cooldown/warmup (GAP 6.0) or GAP-null splits.
    assert (
        abs(result["speed_actual_mps"] - 3.55) < 1e-3
    ), f"speed_actual should be GAP run-only avg 3.55, got {result['speed_actual_mps']}"


@pytest.mark.unit
def test_power_efficiency_rating_calculation():
    """スコアから星評価を計算 (fallback fixed bands, no rel_rmse)."""

    assert calculate_power_efficiency_rating(0.06) == "★★★★★"
    assert calculate_power_efficiency_rating(0.03) == "★★★★☆"
    assert calculate_power_efficiency_rating(0.0) == "★★★☆☆"
    assert calculate_power_efficiency_rating(-0.03) == "★★☆☆☆"
    assert calculate_power_efficiency_rating(-0.06) == "★☆☆☆☆"


def _build_gate_db(tmp_path, speed_actual: float, power_rmse: float) -> str:
    """Build an in-memory-ish DuckDB whose power model yields a controlled
    score and rel_rmse.

    Uses power_b=0 so speed_expected == power_a (independent of W/kg), giving
    a deterministic score = (speed_actual - power_a) / power_a and
    rel_rmse = power_rmse / power_a.
    """
    db_path = str(tmp_path / "gate.duckdb")
    conn = duckdb.connect(db_path)
    conn.execute("CREATE SEQUENCE seq_history_id START 1")
    conn.execute(
        "CREATE TABLE activities (activity_id INTEGER PRIMARY KEY, "
        "activity_date DATE, base_weight_kg FLOAT)"
    )
    conn.execute(
        "CREATE TABLE splits (split_id INTEGER PRIMARY KEY, activity_id INTEGER, "
        "average_speed FLOAT, grade_adjusted_speed FLOAT, power FLOAT, "
        "role_phase VARCHAR)"
    )
    conn.execute(
        "CREATE TABLE form_baseline_history ("
        "history_id INTEGER PRIMARY KEY DEFAULT nextval('seq_history_id'), "
        "user_id VARCHAR, condition_group VARCHAR, metric VARCHAR, "
        "period_start DATE, period_end DATE, power_a DOUBLE, power_b DOUBLE, "
        "power_rmse DOUBLE)"
    )
    conn.execute(
        "CREATE TABLE hr_efficiency (activity_id INTEGER PRIMARY KEY, "
        "training_type VARCHAR)"
    )
    today = datetime.now().date()
    # speed_expected = power_a = 2.5, power_b = 0 → rel_rmse = power_rmse / 2.5
    conn.execute(
        "INSERT INTO form_baseline_history (user_id, condition_group, metric, "
        "period_start, period_end, power_a, power_b, power_rmse) VALUES "
        "('default', 'flat_road', 'power', ?, ?, 2.5, 0.0, ?)",
        [today - timedelta(days=60), today, power_rmse],
    )
    conn.execute(
        "INSERT INTO activities VALUES (2001, ?, 75.0)", [today - timedelta(days=5)]
    )
    conn.execute("INSERT INTO hr_efficiency VALUES (2001, 'low_moderate')")
    conn.execute(
        "INSERT INTO splits VALUES (20001, 2001, 9.0, ?, 250.0, 'run')",
        [speed_actual],
    )
    conn.close()
    return db_path


@pytest.mark.unit
@pytest.mark.parametrize(
    ("speed_actual", "power_rmse", "expected_needs_improvement"),
    [
        # score = (2.4375 - 2.5) / 2.5 = -0.025, rel_rmse = 0.1 / 2.5 = 0.04
        # z = -0.625 (within noise) → -2*rel_rmse = -0.08; -0.025 <= -0.08 is False
        pytest.param(2.4375, 0.1, False, id="within-noise-not-flagged"),
        # score = (2.25 - 2.5) / 2.5 = -0.10, rel_rmse = 0.04, z = -2.5
        # -0.10 <= -0.08 is True
        pytest.param(2.25, 0.1, True, id="clearly-worse-flagged"),
    ],
)
def test_needs_improvement_gated(
    tmp_path, speed_actual, power_rmse, expected_needs_improvement
):
    """needs_improvement is gated at z <= -2 (score <= -2 * rel_rmse)."""
    db_path = _build_gate_db(tmp_path, speed_actual, power_rmse)
    conn = duckdb.connect(db_path)
    today = datetime.now().date()
    result = calculate_power_efficiency_internal(
        conn,
        activity_id=2001,
        activity_date=str(today - timedelta(days=5)),
        user_id="default",
        condition_group="flat_road",
        form_penalties=None,
    )
    conn.close()

    assert result is not None
    assert result["needs_improvement"] is expected_needs_improvement
