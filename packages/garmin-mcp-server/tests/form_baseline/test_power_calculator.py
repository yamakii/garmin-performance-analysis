"""Tests for power_calculator (label bands + running-split averaging)."""

from datetime import datetime, timedelta

import duckdb
import pytest

from garmin_mcp.form_baseline.power_calculator import (
    calculate_power_efficiency_internal,
    calculate_power_efficiency_label,
)


@pytest.mark.unit
class TestCalculatePowerEfficiencyLabel:
    """Test the 3-level self-baseline descriptor for power efficiency score."""

    @pytest.mark.parametrize(
        ("z", "expected_label"),
        [
            # z-score bands when rel_rmse is supplied: z>=1 上回る, |z|<1 同等,
            # z<=-1 下回る.
            pytest.param(1.2, "上回る", id="z-pos1.2-above"),
            pytest.param(1.0, "上回る", id="z-1-above-boundary"),
            pytest.param(0.0, "同等", id="z-0-at"),
            pytest.param(-0.9, "同等", id="z-neg0.9-at"),
            pytest.param(-1.2, "下回る", id="z-neg1.2-below"),
            pytest.param(-1.0, "下回る", id="z-neg1-below-boundary"),
        ],
    )
    def test_label_z_bands(self, z: float, expected_label: str) -> None:
        rel_rmse = 0.04
        score = z * rel_rmse
        assert (
            calculate_power_efficiency_label(score, rel_rmse=rel_rmse) == expected_label
        )

    @pytest.mark.parametrize(
        ("score", "expected_label"),
        [
            # Fixed absolute bands used when rel_rmse is not supplied.
            pytest.param(0.04, "上回る", id="fallback-above"),
            pytest.param(0.03, "上回る", id="fallback-above-boundary"),
            pytest.param(-0.01, "同等", id="fallback-at"),
            pytest.param(0.0, "同等", id="fallback-at-zero"),
            pytest.param(-0.05, "下回る", id="fallback-below"),
            pytest.param(-0.03, "下回る", id="fallback-below-boundary"),
        ],
    )
    def test_label_fallback_no_rmse(self, score: float, expected_label: str) -> None:
        assert calculate_power_efficiency_label(score, rel_rmse=None) == expected_label

    def test_today_run_is_doukaku(self) -> None:
        """|z| < 1 (within ±1 RMSE) reads as "同等" (at baseline = good).

        Regression: 2026-07-07 run — a single-run -2.5% residual with a 4% RMSE
        baseline (z=-0.625) must read as "同等", not a weakness.
        """
        assert calculate_power_efficiency_label(-0.025, rel_rmse=0.04) == "同等"


# The five real 1 km laps of activity 24394775433 (2026-09-17).
_REAL_KM_SPLITS = [
    (1, 1.0, 350.0, 259.0),
    (2, 1.0, 348.0, 267.0),
    (3, 1.0, 352.0, 270.0),
    (4, 1.0, 349.0, 274.0),
    (5, 1.0, 347.0, 279.0),
]

_ACTIVITY_ID = 24394775433


def _conn_with_splits(splits: list[tuple[int, float, float, float]]):
    """Build an in-memory DuckDB holding one activity with the given splits.

    Each split is ``(split_id, distance_km, pace_seconds_per_km, power_w)`` and
    is inserted as ``role_phase = 'run'``; ``grade_adjusted_speed`` is derived
    from the pace so speed and pace stay consistent.
    """
    conn = duckdb.connect(":memory:")
    conn.execute(
        "CREATE TABLE activities (activity_id BIGINT PRIMARY KEY, "
        "activity_date DATE, base_weight_kg FLOAT)"
    )
    conn.execute(
        "CREATE TABLE splits (split_id INTEGER PRIMARY KEY, activity_id BIGINT, "
        "grade_adjusted_speed FLOAT, power FLOAT, role_phase VARCHAR, "
        "distance FLOAT, pace_seconds_per_km FLOAT)"
    )
    conn.execute(
        "CREATE TABLE hr_efficiency (activity_id BIGINT PRIMARY KEY, "
        "training_type VARCHAR)"
    )
    conn.execute(
        "CREATE TABLE form_baseline_history (user_id VARCHAR, "
        "condition_group VARCHAR, metric VARCHAR, period_start DATE, "
        "period_end DATE, power_a DOUBLE, power_b DOUBLE, power_rmse DOUBLE)"
    )

    today = datetime.now().date()
    activity_date = today - timedelta(days=1)
    conn.execute(
        "INSERT INTO activities VALUES (?, ?, 75.0)", [_ACTIVITY_ID, activity_date]
    )
    conn.execute("INSERT INTO hr_efficiency VALUES (?, 'low_moderate')", [_ACTIVITY_ID])
    conn.execute(
        "INSERT INTO form_baseline_history VALUES ('default', 'flat_road', 'power', "
        "?, ?, 1.0, 0.7, 0.1)",
        [today - timedelta(days=60), today],
    )
    for split_id, distance_km, pace, power_w in splits:
        conn.execute(
            "INSERT INTO splits VALUES (?, ?, ?, ?, 'run', ?, ?)",
            [split_id, _ACTIVITY_ID, 1000.0 / pace, power_w, distance_km, pace],
        )
    return conn


def _evaluate(conn) -> dict | None:
    return calculate_power_efficiency_internal(
        conn,
        activity_id=_ACTIVITY_ID,
        activity_date=str(datetime.now().date() - timedelta(days=1)),
        user_id="default",
        condition_group="flat_road",
        form_penalties=None,
    )


@pytest.mark.unit
class TestPowerAverageRunningSplitsOnly:
    """The activity average must cover running splits only (#1231)."""

    def test_power_average_excludes_fragment_splits(self) -> None:
        """10-14 m manual-lap fragments must not enter the unweighted mean.

        Regression: activity 24394775433 — two fragments at 364 W / 377 W
        pulled the average from 269.8 W to 298.57 W and flipped the label.
        """
        conn = _conn_with_splits(
            [
                *_REAL_KM_SPLITS,
                (6, 0.014, 244.0, 364.0),
                (7, 0.010, 250.0, 377.0),
            ]
        )
        result = _evaluate(conn)
        conn.close()

        assert result is not None
        assert result["avg_w"] == pytest.approx(269.8)

    def test_power_average_excludes_walk_splits(self) -> None:
        """A deliberate walk lap (700 s/km) leaves the average untouched."""
        conn = _conn_with_splits([*_REAL_KM_SPLITS, (6, 0.5, 700.0, 150.0)])
        result = _evaluate(conn)
        conn.close()

        assert result is not None
        assert result["avg_w"] == pytest.approx(269.8)

    def test_power_returns_none_when_only_fragments(self) -> None:
        """Every split filtered out → None (same path as "no power data")."""
        conn = _conn_with_splits(
            [
                (1, 0.014, 244.0, 364.0),
                (2, 0.010, 250.0, 377.0),
            ]
        )
        result = _evaluate(conn)
        conn.close()

        assert result is None
