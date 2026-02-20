"""Tests for power efficiency baseline training.

Tests train_power_efficiency_baseline function that trains
power-to-speed model and stores in form_baseline_history.

Performance: Module-scoped base_tmp_db avoids repeated DDL+INSERT (~0.35s → ~0.6ms).
"""

import shutil
from datetime import datetime, timedelta

import duckdb
import pytest


@pytest.fixture(scope="module")
def _base_tmp_db(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Module-scoped database with test data (read-only use).

    Creates tables + 20 activities × 5 splits once per module.
    """
    tmp_path = tmp_path_factory.mktemp("trainer_power")
    db_path = str(tmp_path / "test.duckdb")
    conn = duckdb.connect(db_path)

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
            power FLOAT
        )
    """)

    conn.execute("CREATE SEQUENCE seq_history_id START 1")
    conn.execute("CREATE SEQUENCE form_baseline_history_seq START 1")

    conn.execute("""
        CREATE TABLE form_baseline_history (
            history_id INTEGER PRIMARY KEY DEFAULT nextval('seq_history_id'),
            user_id VARCHAR DEFAULT 'default',
            condition_group VARCHAR DEFAULT 'flat_road',
            metric VARCHAR,
            model_type VARCHAR,
            coef_alpha FLOAT,
            coef_d FLOAT,
            coef_a FLOAT,
            coef_b FLOAT,
            period_start DATE,
            period_end DATE,
            trained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            n_samples INTEGER,
            rmse FLOAT,
            speed_range_min FLOAT,
            speed_range_max FLOAT,
            power_a FLOAT,
            power_b FLOAT,
            power_rmse FLOAT,
            UNIQUE (user_id, condition_group, metric, period_start, period_end)
        )
    """)

    end_date = datetime.now()
    start_date = end_date - timedelta(days=60)

    activity_rows = []
    split_rows = []
    for i in range(20):
        activity_date = start_date + timedelta(days=i * 3)
        activity_id = 1000 + i
        base_weight_kg = 75.0
        activity_rows.append((activity_id, activity_date.date(), base_weight_kg))

        for j in range(5):
            split_id = activity_id * 10 + j
            power = 200 + j * 20
            power_wkg = power / base_weight_kg
            speed = 1.0 + 0.7 * power_wkg
            split_rows.append((split_id, activity_id, speed, power))

    conn.executemany("INSERT INTO activities VALUES (?, ?, ?)", activity_rows)
    conn.executemany("INSERT INTO splits VALUES (?, ?, ?, ?)", split_rows)
    conn.close()
    return db_path


@pytest.fixture
def tmp_db_path(_base_tmp_db: str, tmp_path) -> str:
    """Function-scoped copy of base DB for tests that mutate data."""
    dest = tmp_path / "test.duckdb"
    shutil.copy2(_base_tmp_db, str(dest))
    return str(dest)


@pytest.mark.integration
def test_train_power_efficiency_baseline(tmp_db_path):
    """2ヶ月窓でパワー効率baselineを訓練."""
    from garmin_mcp.form_baseline.trainer import train_power_efficiency_baseline

    result = train_power_efficiency_baseline(
        user_id="default",
        condition_group="flat_road",
        end_date=datetime.now().strftime("%Y-%m-%d"),
        window_months=2,
        db_path=tmp_db_path,
    )

    assert result is not None
    assert "power_a" in result
    assert "power_b" in result
    assert "power_rmse" in result
    assert "n_samples" in result

    assert (
        0.5 < result["power_a"] < 1.5
    ), f"power_a should be ~1.0, got {result['power_a']}"
    assert (
        0.5 < result["power_b"] < 1.0
    ), f"power_b should be ~0.7, got {result['power_b']}"
    assert (
        result["power_rmse"] < 0.5
    ), f"RMSE should be small, got {result['power_rmse']}"
    assert (
        result["n_samples"] >= 50
    ), f"Should have 50+ samples, got {result['n_samples']}"

    conn = duckdb.connect(tmp_db_path, read_only=True)
    row = conn.execute("""
        SELECT power_a, power_b, power_rmse, n_samples, metric
        FROM form_baseline_history
        WHERE metric = 'power'
    """).fetchone()

    assert row is not None, "Should insert into form_baseline_history"
    assert (
        abs(row[0] - result["power_a"]) < 1e-6
    ), f"power_a mismatch: {row[0]} vs {result['power_a']}"
    assert (
        abs(row[1] - result["power_b"]) < 1e-6
    ), f"power_b mismatch: {row[1]} vs {result['power_b']}"
    assert (
        abs(row[2] - result["power_rmse"]) < 1e-6
    ), f"power_rmse mismatch: {row[2]} vs {result['power_rmse']}"
    assert row[3] == result["n_samples"]
    assert row[4] == "power"

    conn.close()


@pytest.mark.integration
def test_train_power_efficiency_baseline_no_power_data(tmp_db_path):
    """パワーデータなしの場合、Noneを返す."""
    from garmin_mcp.form_baseline.trainer import train_power_efficiency_baseline

    conn = duckdb.connect(tmp_db_path)
    conn.execute("UPDATE splits SET power = NULL")
    conn.close()

    result = train_power_efficiency_baseline(
        user_id="default",
        condition_group="flat_road",
        end_date=datetime.now().strftime("%Y-%m-%d"),
        window_months=2,
        db_path=tmp_db_path,
    )

    assert result is None


@pytest.mark.integration
def test_train_power_efficiency_baseline_insufficient_data(tmp_db_path):
    """データ不足の場合、Noneを返す."""
    from garmin_mcp.form_baseline.trainer import train_power_efficiency_baseline

    conn = duckdb.connect(tmp_db_path)
    conn.execute("DELETE FROM splits WHERE split_id % 10 != 0")
    conn.close()

    result = train_power_efficiency_baseline(
        user_id="default",
        condition_group="flat_road",
        end_date=datetime.now().strftime("%Y-%m-%d"),
        window_months=2,
        db_path=tmp_db_path,
    )

    assert result is None
