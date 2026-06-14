"""Tests for form_baseline.trainer module."""

from datetime import date, datetime, timedelta

import duckdb
import numpy as np
import pandas as pd
import pytest

from garmin_mcp.form_baseline.trainer import (
    GCTPowerModel,
    LinearModel,
    _month_end,
    _target_month_ends,
    ensure_form_baselines_for_date,
    fit_gct_power,
    fit_linear,
    train_form_baselines,
)


@pytest.mark.unit
class TestGCTPowerModel:
    """Test GCT power model dataclass."""

    def test_predict_inverse(self):
        """Test inverse prediction: speed -> GCT."""
        # Example: log(v) = 2.0 + (-0.5) * log(GCT)
        # For v=3.0 m/s: GCT = exp((log(3.0) - 2.0) / -0.5)
        model = GCTPowerModel(
            alpha=2.0, d=-0.5, rmse=0.1, n_samples=100, speed_range=(2.0, 5.0)
        )

        gct = model.predict_inverse(3.0)
        # Expected: exp((ln(3.0) - 2.0) / -0.5) ≈ exp((-0.901) / -0.5) ≈ exp(1.802) ≈ 6.06
        assert abs(gct - 6.06) < 0.1

    def test_predict_forward(self):
        """Test forward prediction: GCT -> speed."""
        model = GCTPowerModel(
            alpha=2.0, d=-0.5, rmse=0.1, n_samples=100, speed_range=(2.0, 5.0)
        )

        # For GCT=250: v = exp(2.0 + (-0.5) * log(250))
        speed = model.predict(250.0)
        expected = np.exp(2.0 + (-0.5) * np.log(250.0))
        assert abs(speed - expected) < 0.01


@pytest.mark.unit
class TestLinearModel:
    """Test linear model dataclass."""

    def test_predict(self):
        """Test linear prediction: speed -> VO/VR."""
        # y = 10.0 + (-1.0) * v
        model = LinearModel(
            a=10.0, b=-1.0, rmse=0.5, n_samples=100, speed_range=(2.0, 5.0)
        )

        # For v=3.0: y = 10.0 - 3.0 = 7.0
        result = model.predict(3.0)
        assert abs(result - 7.0) < 0.01


@pytest.mark.unit
class TestFitGCTPower:
    """Test GCT power model fitting."""

    def test_fit_gct_power_basic(self):
        """Test basic GCT power model fitting."""
        # Generate synthetic data with realistic running speeds (3-4 m/s)
        # Using formula: v = c * GCT^d, where c = exp(alpha)
        # For realistic data: alpha ~ 4.6, d ~ -0.6 gives speeds 3.1-4.0 m/s
        gct_values = np.array([200, 220, 240, 260, 280, 300])
        alpha_true = 4.6
        d_true = -0.6
        speed_values = np.exp(alpha_true + d_true * np.log(gct_values))

        df = pd.DataFrame({"gct_ms": gct_values, "speed_mps": speed_values})

        model = fit_gct_power(df, fallback_ransac=False)

        # Check monotonicity (d < 0)
        assert model.d < 0

        # Check approximate coefficient recovery
        assert abs(model.alpha - alpha_true) < 0.2
        assert abs(model.d - d_true) < 0.2

        # Check metadata
        assert model.n_samples == 6
        assert model.speed_range[0] > 0
        assert model.speed_range[1] > model.speed_range[0]

    def test_fit_gct_power_with_noise(self):
        """Test GCT power model with noisy data."""
        np.random.seed(42)
        gct_values = np.linspace(200, 300, 20)
        alpha_true = 4.6
        d_true = -0.6
        speed_values = np.exp(alpha_true + d_true * np.log(gct_values))
        # Add noise
        speed_values += np.random.normal(0, 0.1, size=len(speed_values))

        df = pd.DataFrame({"gct_ms": gct_values, "speed_mps": speed_values})

        model = fit_gct_power(df, fallback_ransac=False)

        # Should still be monotonic
        assert model.d < 0
        # Should be reasonably close to true values (relaxed tolerance for noisy data)
        assert abs(model.alpha - alpha_true) < 0.8
        assert abs(model.d - d_true) < 0.3

    def test_fit_gct_power_ransac_fallback(self):
        """Test RANSAC fallback when Huber fails monotonicity."""
        # Create data that might cause Huber to fail (with outliers)
        np.random.seed(42)
        gct_values = np.array([200, 220, 240, 260, 280, 300, 180, 320])
        alpha_true = 4.6
        d_true = -0.6
        speed_values = np.exp(alpha_true + d_true * np.log(gct_values))
        # Add outliers
        speed_values[6] = 6.5  # High outlier
        speed_values[7] = 2.0  # Low outlier

        df = pd.DataFrame({"gct_ms": gct_values, "speed_mps": speed_values})

        # Should use RANSAC fallback if needed
        model = fit_gct_power(df, fallback_ransac=True)

        # Should still be monotonic
        assert model.d < 0

    def test_fit_gct_power_insufficient_data(self):
        """Test error with insufficient data."""
        df = pd.DataFrame({"gct_ms": [200, 250], "speed_mps": [3.0, 2.8]})

        # Should raise ValueError (need more samples)
        with pytest.raises((ValueError, Exception)):
            fit_gct_power(df, fallback_ransac=False)


@pytest.mark.unit
class TestFitLinear:
    """Test linear model fitting."""

    def test_fit_linear_vo(self):
        """Test VO linear model fitting."""
        # Generate synthetic data: VO = 12.0 + (-1.5) * speed
        speed_values = np.array([2.5, 3.0, 3.5, 4.0, 4.5, 5.0])
        a_true = 12.0
        b_true = -1.5
        vo_values = a_true + b_true * speed_values

        df = pd.DataFrame({"vo_value": vo_values, "speed_mps": speed_values})

        model = fit_linear(df, metric="vo")

        # Check coefficient recovery
        assert abs(model.a - a_true) < 0.1
        assert abs(model.b - b_true) < 0.1

        # Check metadata
        assert model.n_samples == 6
        assert model.speed_range[0] == 2.5
        assert model.speed_range[1] == 5.0

    def test_fit_linear_vr(self):
        """Test VR linear model fitting."""
        # Generate synthetic data: VR = 15.0 + (-2.0) * speed
        speed_values = np.array([2.5, 3.0, 3.5, 4.0, 4.5])
        a_true = 15.0
        b_true = -2.0
        vr_values = a_true + b_true * speed_values

        df = pd.DataFrame({"vr_value": vr_values, "speed_mps": speed_values})

        model = fit_linear(df, metric="vr")

        # Check coefficient recovery
        assert abs(model.a - a_true) < 0.1
        assert abs(model.b - b_true) < 0.1

    def test_fit_linear_with_noise(self):
        """Test linear model with noisy data."""
        np.random.seed(42)
        speed_values = np.linspace(2.0, 5.0, 30)
        a_true = 10.0
        b_true = -1.0
        vo_values = a_true + b_true * speed_values
        # Add noise
        vo_values += np.random.normal(0, 0.2, size=len(vo_values))

        df = pd.DataFrame({"vo_value": vo_values, "speed_mps": speed_values})

        model = fit_linear(df, metric="vo")

        # Should be close to true values
        assert abs(model.a - a_true) < 0.3
        assert abs(model.b - b_true) < 0.1

        # RMSE should be reasonable
        assert model.rmse < 0.5

    def test_fit_linear_insufficient_data(self):
        """Test error with insufficient data."""
        df = pd.DataFrame({"vo_value": [8.0], "speed_mps": [3.0]})

        # Should raise ValueError or have issues
        with pytest.raises((ValueError, Exception)):
            fit_linear(df, metric="vo")

    def test_fit_linear_cadence_positive_slope(self):
        """Cadence increases with speed -> b > 0."""
        # Synthetic data: cadence = 160.0 + 5.0 * speed (positive slope)
        speed_values = np.array([2.5, 3.0, 3.5, 4.0, 4.5, 5.0])
        a_true = 160.0
        b_true = 5.0
        cadence_values = a_true + b_true * speed_values

        df = pd.DataFrame({"cadence_value": cadence_values, "speed_mps": speed_values})

        model = fit_linear(df, metric="cadence")

        # Faster speed -> higher cadence: positive slope
        assert model.b > 0
        assert abs(model.a - a_true) < 0.5
        assert abs(model.b - b_true) < 0.5
        assert model.n_samples == 6

    def test_fit_linear_cadence_outlier_removal(self):
        """Cadence values below 140spm / above 210spm are removed."""
        # 6 valid points plus 2 outliers (one < 140, one > 210)
        speed_values = np.array([2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 3.2, 3.8])
        cadence_values = np.array(
            [172.0, 175.0, 178.0, 181.0, 184.0, 187.0, 130.0, 215.0]
        )

        df = pd.DataFrame({"cadence_value": cadence_values, "speed_mps": speed_values})

        model = fit_linear(df, metric="cadence")

        # Two outliers removed -> 6 valid samples remain
        assert model.n_samples == 6
        # Speed range should reflect only valid rows (3.2 and 3.8 kept, but
        # their cadence outliers removed them) -> min 2.5, max 5.0
        assert model.speed_range[0] == 2.5
        assert model.speed_range[1] == 5.0


def _seed_baseline_db(db_path: str) -> None:
    """Seed a real DuckDB with splits/activities for train_form_baselines.

    Creates 20 activities x 5 splits = 100 rows within a 60-day window.
    Each split carries GCT/VO/VR/cadence that vary with speed (so the
    linear/power fits are well-conditioned) and stay inside the trainer's
    outlier bounds. Power + base_weight_kg are included so the trailing
    power-efficiency training also has data.
    """
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
            pace_seconds_per_km FLOAT,
            ground_contact_time FLOAT,
            vertical_oscillation FLOAT,
            vertical_ratio FLOAT,
            stride_length FLOAT,
            cadence FLOAT,
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
    start_date = end_date - timedelta(days=55)

    activity_rows = []
    split_rows = []
    for i in range(20):
        activity_date = start_date + timedelta(days=i * 2)
        activity_id = 2000 + i
        base_weight_kg = 70.0
        activity_rows.append((activity_id, activity_date.date(), base_weight_kg))

        for j in range(5):
            split_id = activity_id * 10 + j
            # Pace 330 -> 270 sec/km => speed ~3.03 -> 3.70 m/s
            pace = 330.0 - (i * 5 + j * 12) % 60
            speed = 1000.0 / pace
            # Form metrics vary with speed, within outlier bounds:
            # GCT 150-350, VO 5-20, VR 4-15, cadence 140-210
            gct = 300.0 - 20.0 * speed
            vo = 12.0 - 1.0 * speed
            vr = 11.0 - 1.0 * speed
            cadence = 160.0 + 5.0 * speed  # positive slope with speed
            stride_length = 1.0 + 0.1 * speed
            power = 180.0 + 30.0 * speed
            split_rows.append(
                (
                    split_id,
                    activity_id,
                    pace,
                    gct,
                    vo,
                    vr,
                    stride_length,
                    cadence,
                    speed,
                    power,
                )
            )

    conn.executemany("INSERT INTO activities VALUES (?, ?, ?)", activity_rows)
    conn.executemany(
        "INSERT INTO splits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", split_rows
    )
    conn.close()


@pytest.mark.integration
def test_train_form_baselines_inserts_cadence_row(tmp_path):
    """Regression for #219: cadence baseline INSERT must succeed.

    The cadence INSERT previously had an off-by-one placeholder (15 ? for
    14 values), causing DuckDB to fail and the cadence baseline to never
    persist. train_form_baselines swallows the error and returns None, so
    we assert directly against form_baseline_history.
    """
    db_path = str(tmp_path / "baseline.duckdb")
    _seed_baseline_db(db_path)

    result = train_form_baselines(
        user_id="default",
        condition_group="flat_road",
        end_date=datetime.now().strftime("%Y-%m-%d"),
        window_months=2,
        db_path=db_path,
    )

    assert result is not None, "train_form_baselines should not fail on valid data"

    conn = duckdb.connect(db_path, read_only=True)
    try:
        count_row = conn.execute(
            "SELECT COUNT(*) FROM form_baseline_history WHERE metric = 'cadence'"
        ).fetchone()
        assert count_row is not None
        assert count_row[0] == 1, "Exactly one cadence baseline row expected"

        coef_row = conn.execute(
            "SELECT coef_a, coef_b FROM form_baseline_history WHERE metric = 'cadence'"
        ).fetchone()
        assert coef_row is not None
        assert coef_row[0] is not None, "cadence coef_a must be non-null"
        assert coef_row[1] is not None, "cadence coef_b must be non-null"

        # VO/VR baselines should be created alongside cadence.
        vo_vr_row = conn.execute(
            "SELECT COUNT(*) FROM form_baseline_history " "WHERE metric IN ('vo', 'vr')"
        ).fetchone()
        assert vo_vr_row is not None
        assert vo_vr_row[0] == 2, "VO and VR baselines should also be inserted"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Issue #266: self-healing baseline generation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_target_month_ends_current_and_prev():
    """_target_month_ends returns [current_month_end, prior_month_end]."""
    assert _target_month_ends("2026-06-14") == ["2026-06-30", "2026-05-31"]


@pytest.mark.unit
def test_month_end_december():
    """_month_end handles the year boundary (December)."""
    assert _month_end(date(2026, 12, 5)) == date(2026, 12, 31)


def _create_baseline_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the activities/splits/form_baseline_history schema for ensure tests."""
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
            pace_seconds_per_km FLOAT,
            ground_contact_time FLOAT,
            vertical_oscillation FLOAT,
            vertical_ratio FLOAT,
            stride_length FLOAT,
            cadence FLOAT,
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


def _make_splits(activity_id: int) -> list[tuple]:
    """Return 5 well-conditioned splits (within outlier bounds) for an activity."""
    rows = []
    for j in range(5):
        split_id = activity_id * 10 + j
        # Pace 330 -> 270 sec/km => speed ~3.03 -> 3.70 m/s
        pace = 330.0 - (activity_id * 5 + j * 12) % 60
        speed = 1000.0 / pace
        gct = 300.0 - 20.0 * speed  # 150-350
        vo = 12.0 - 1.0 * speed  # 5-20
        vr = 11.0 - 1.0 * speed  # 4-15
        cadence = 160.0 + 5.0 * speed  # 140-210
        stride_length = 1.0 + 0.1 * speed
        power = 180.0 + 30.0 * speed
        rows.append(
            (
                split_id,
                activity_id,
                pace,
                gct,
                vo,
                vr,
                stride_length,
                cadence,
                speed,
                power,
            )
        )
    return rows


def _seed_two_month_window(db_path: str, activity_date: str, splits_per_month: int):
    """Seed activities/splits across the activity month and prior month.

    ``splits_per_month`` controls how many 5-split activities go into EACH of the
    two months. With 12 activities/month -> 60 splits/month (>=50) so both the
    current and prior baseline periods (each a 2-month window) have enough data.
    Use a small value (e.g. 1 -> 5 splits) to exercise the insufficient path.
    """
    conn = duckdb.connect(db_path)
    _create_baseline_schema(conn)

    d = datetime.strptime(activity_date, "%Y-%m-%d").date()
    # Mid-points of the activity month and the prior month.
    current_mid = date(d.year, d.month, 15)
    prior_first = date(d.year, d.month, 1) - timedelta(days=1)
    prior_mid = date(prior_first.year, prior_first.month, 15)

    activity_rows = []
    split_rows = []
    next_id = 3000
    for month_anchor in (current_mid, prior_mid):
        for k in range(splits_per_month):
            activity_id = next_id
            next_id += 1
            act_date = month_anchor + timedelta(days=k % 10)
            activity_rows.append((activity_id, act_date, 70.0))
            split_rows.extend(_make_splits(activity_id))

    if activity_rows:
        conn.executemany("INSERT INTO activities VALUES (?, ?, ?)", activity_rows)
    if split_rows:
        conn.executemany(
            "INSERT INTO splits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", split_rows
        )
    conn.close()


def _count_baseline_rows(db_path: str) -> int:
    """Return the total number of rows in form_baseline_history."""
    conn = duckdb.connect(db_path, read_only=True)
    try:
        row = conn.execute("SELECT COUNT(*) FROM form_baseline_history").fetchone()
        return int(row[0]) if row is not None else 0
    finally:
        conn.close()


@pytest.mark.integration
def test_ensure_generates_when_missing(tmp_path):
    """ensure generates baselines for the activity month + prior month."""
    db_path = str(tmp_path / "ensure_gen.duckdb")
    activity_date = "2026-03-15"
    _seed_two_month_window(db_path, activity_date, splits_per_month=12)

    result = ensure_form_baselines_for_date(activity_date, db_path)

    assert len(result["generated"]) == 2, result
    assert result["skipped"] == []
    assert result["insufficient"] == []
    assert set(result["generated"]) == {"2026-03-31", "2026-02-28"}

    conn = duckdb.connect(db_path, read_only=True)
    try:
        for period_end in ("2026-03-31", "2026-02-28"):
            row = conn.execute(
                """
                SELECT COUNT(*) FROM form_baseline_history
                WHERE period_end = ? AND metric IN ('gct', 'vo', 'vr')
                """,
                [period_end],
            ).fetchone()
            assert row is not None
            assert row[0] == 3, f"gct/vo/vr expected for {period_end}, got {row[0]}"
    finally:
        conn.close()


@pytest.mark.integration
def test_ensure_skips_when_exists(tmp_path):
    """ensure is idempotent: a second call skips both periods, rows unchanged."""
    db_path = str(tmp_path / "ensure_skip.duckdb")
    activity_date = "2026-03-15"
    _seed_two_month_window(db_path, activity_date, splits_per_month=12)

    first = ensure_form_baselines_for_date(activity_date, db_path)
    assert len(first["generated"]) == 2

    count_after_first = _count_baseline_rows(db_path)

    second = ensure_form_baselines_for_date(activity_date, db_path)
    assert len(second["skipped"]) == 2, second
    assert second["generated"] == []
    assert second["insufficient"] == []
    assert set(second["skipped"]) == {"2026-03-31", "2026-02-28"}

    count_after_second = _count_baseline_rows(db_path)

    assert count_after_second == count_after_first, "row count must be unchanged"


@pytest.mark.integration
def test_ensure_insufficient_data(tmp_path):
    """ensure records insufficient periods when splits < 50, no rows, no raise."""
    db_path = str(tmp_path / "ensure_insufficient.duckdb")
    activity_date = "2026-03-15"
    # 1 activity/month -> 5 splits/month -> < 50 in each 2-month window.
    _seed_two_month_window(db_path, activity_date, splits_per_month=1)

    result = ensure_form_baselines_for_date(activity_date, db_path)

    assert result["generated"] == [], result
    assert result["skipped"] == []
    assert len(result["insufficient"]) == 2
    assert set(result["insufficient"]) == {"2026-03-31", "2026-02-28"}

    assert (
        _count_baseline_rows(db_path) == 0
    ), "no baseline rows should be created on insufficient data"
