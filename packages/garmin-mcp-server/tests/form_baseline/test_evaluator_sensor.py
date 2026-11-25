"""evaluate_and_store grades a run by the model of its own sensor (#1631)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.form_baseline.evaluator import evaluate_and_store
from garmin_mcp.form_baseline.trainer import GCTPowerModel

ACTIVITY_DATE = "2026-03-20"
PACE = 303.0  # 3.30 m/s
SPEED = 1000.0 / PACE

# (alpha, vo_a, vr_a) per sensor; the slopes are flat so the expectation is exact.
_MODELS = {
    "all": (6.67, 8.0, 8.5),
    "wrist": (6.77, 7.0, 9.5),
}


def _seed_baselines(db_path: Path, sources: tuple[str, ...]) -> None:
    conn = duckdb.connect(str(db_path))
    try:
        history_id = 1
        for source in sources:
            alpha, vo_a, vr_a = _MODELS[source]
            for metric, coefs in (
                ("gct", (alpha, -1.0, None, None)),
                ("vo", (None, None, vo_a, 0.0)),
                ("vr", (None, None, vr_a, 0.0)),
                ("cadence", (None, None, 176.0, 0.0)),
            ):
                conn.execute(
                    """
                    INSERT INTO form_baseline_history (
                        history_id, dynamics_source, metric, model_type,
                        coef_alpha, coef_d, coef_a, coef_b,
                        period_start, period_end, n_samples, rmse,
                        speed_range_min, speed_range_max
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '2026-02-01', '2026-03-31',
                              120, 0.05, 2.5, 4.0)
                    """,
                    [
                        history_id,
                        source,
                        metric,
                        "power_gct" if metric == "gct" else "linear",
                        *coefs,
                    ],
                )
                history_id += 1
    finally:
        conn.close()


def _seed_run(db_path: Path, activity_id: int, source: str | None) -> None:
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO activities (
                activity_id, activity_date, total_distance_km, dynamics_source
            ) VALUES (?, ?, 5.0, ?)
            """,
            [activity_id, ACTIVITY_DATE, source],
        )
        for index in range(1, 6):
            conn.execute(
                """
                INSERT INTO splits (
                    activity_id, split_index, distance, duration_seconds,
                    pace_seconds_per_km, heart_rate, max_heart_rate, cadence,
                    elevation_gain, elevation_loss,
                    ground_contact_time, vertical_oscillation, vertical_ratio
                ) VALUES (?, ?, 1.0, ?, ?, 140, 150, 176.0, 1.0, 1.0,
                          250.0, 7.8, 8.0)
                """,
                [activity_id, index, PACE, PACE],
            )
    finally:
        conn.close()


def _expected(db_path: Path, activity_id: int) -> tuple[float, float, float]:
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        row = conn.execute(
            "SELECT gct_ms_expected, vo_cm_expected, vr_pct_expected "
            "FROM form_evaluations WHERE activity_id = ?",
            [activity_id],
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    return row[0], row[1], row[2]


@pytest.mark.integration
def test_evaluate_uses_activity_sensor_model(initialized_db_path: Path) -> None:
    """A wrist run's expectations come from the wrist rows, not the legacy ones."""
    _seed_baselines(initialized_db_path, ("all", "wrist"))
    _seed_run(initialized_db_path, 9001, "wrist")

    evaluate_and_store(9001, ACTIVITY_DATE, str(initialized_db_path))

    gct, vo, vr = _expected(initialized_db_path, 9001)
    wrist_gct = GCTPowerModel(
        alpha=6.77, d=-1.0, rmse=0.05, n_samples=120, speed_range=(2.5, 4.0)
    ).predict_inverse(SPEED)
    assert gct == pytest.approx(wrist_gct, rel=1e-3)
    assert vo == pytest.approx(7.0, rel=1e-3)
    assert vr == pytest.approx(9.5, rel=1e-3)


@pytest.mark.integration
def test_evaluate_null_sensor_uses_all(initialized_db_path: Path) -> None:
    """A run with no recorded sensor is graded by the legacy 'all' model."""
    _seed_baselines(initialized_db_path, ("all", "wrist"))
    _seed_run(initialized_db_path, 9002, None)

    evaluate_and_store(9002, ACTIVITY_DATE, str(initialized_db_path))

    gct, vo, vr = _expected(initialized_db_path, 9002)
    legacy_gct = GCTPowerModel(
        alpha=6.67, d=-1.0, rmse=0.05, n_samples=120, speed_range=(2.5, 4.0)
    ).predict_inverse(SPEED)
    assert gct == pytest.approx(legacy_gct, rel=1e-3)
    assert vo == pytest.approx(8.0, rel=1e-3)
    assert vr == pytest.approx(8.5, rel=1e-3)


@pytest.mark.integration
def test_evaluate_known_sensor_without_model_is_not_graded(
    initialized_db_path: Path,
) -> None:
    """A pod run with only legacy rows gets no form evaluation (no fallback)."""
    _seed_baselines(initialized_db_path, ("all",))
    _seed_run(initialized_db_path, 9003, "pod")

    with pytest.raises(ValueError, match="dynamics_source=pod"):
        evaluate_and_store(9003, ACTIVITY_DATE, str(initialized_db_path))

    conn = duckdb.connect(str(initialized_db_path), read_only=True)
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM form_evaluations WHERE activity_id = 9003"
        ).fetchone()
    finally:
        conn.close()
    assert count == (0,)
