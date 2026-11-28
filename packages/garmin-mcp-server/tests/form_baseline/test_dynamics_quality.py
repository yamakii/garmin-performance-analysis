"""Collapsed pod dynamics are flagged at ingest and dropped from form paths (#1635)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pytest

from garmin_mcp.form_baseline.dynamics_quality import (
    MIN_BIN_SAMPLES,
    BinReference,
    flag_suspect_dynamics,
    suspect_score,
)
from garmin_mcp.form_baseline.evaluator import evaluate_and_store
from garmin_mcp.form_baseline.split_filter import form_split_params, form_split_sql
from garmin_mcp.form_baseline.trainer import train_form_baselines
from tests.form_baseline.test_evaluator_sensor import (
    ACTIVITY_DATE,
    PACE,
    _seed_baselines,
)

PRIOR_START = date(2026, 2, 1)
TODAY_ID = 99_000
TODAY = "2026-03-20"
BIN_PACE = 330.0  # inside one 30 s/km bin


def _insert_activity(conn: duckdb.DuckDBPyConnection, activity_id: int, day, source):
    conn.execute(
        "INSERT INTO activities (activity_id, activity_date, total_distance_km, "
        "dynamics_source) VALUES (?, ?, 5.0, ?)",
        [activity_id, day, source],
    )


def _insert_split(
    conn: duckdb.DuckDBPyConnection,
    activity_id: int,
    index: int,
    gct: float,
    vo: float,
    *,
    pace: float = BIN_PACE,
    suspect: bool = False,
) -> None:
    conn.execute(
        """
        INSERT INTO splits (
            activity_id, split_index, distance, duration_seconds,
            pace_seconds_per_km, cadence, ground_contact_time,
            vertical_oscillation, vertical_ratio, role_phase, dynamics_suspect
        ) VALUES (?, ?, 1.0, ?, ?, 176.0, ?, ?, 8.0, 'run', ?)
        """,
        [activity_id, index, pace, pace, gct, vo, suspect],
    )


def _seed_reference(
    db_path: Path, source: str = "pod", n_splits: int = 60, start_id: int = 1000
) -> None:
    """``n_splits`` normal splits (GCT 255 +-5 / VO 8.0 +-0.3) over prior runs."""
    rng = np.random.default_rng(7)
    conn = duckdb.connect(str(db_path))
    try:
        for run in range(n_splits // 5):
            activity_id = start_id + run
            _insert_activity(
                conn, activity_id, PRIOR_START + timedelta(days=run), source
            )
            for index in range(1, 6):
                _insert_split(
                    conn,
                    activity_id,
                    index,
                    float(rng.normal(255.0, 5.0)),
                    float(rng.normal(8.0, 0.3)),
                )
    finally:
        conn.close()


def _seed_today(
    db_path: Path,
    splits: list[tuple[float, float]],
    source: str = "pod",
    day: str = TODAY,
    activity_id: int = TODAY_ID,
) -> None:
    conn = duckdb.connect(str(db_path))
    try:
        _insert_activity(conn, activity_id, day, source)
        for index, (gct, vo) in enumerate(splits, start=1):
            _insert_split(conn, activity_id, index, gct, vo)
    finally:
        conn.close()


def _flag(db_path: Path, activity_id: int = TODAY_ID) -> tuple[int, list[bool]]:
    conn = duckdb.connect(str(db_path))
    try:
        count = flag_suspect_dynamics(conn, activity_id)
        flags = [
            bool(row[0])
            for row in conn.execute(
                "SELECT dynamics_suspect FROM splits WHERE activity_id = ? "
                "ORDER BY split_index",
                [activity_id],
            ).fetchall()
        ]
    finally:
        conn.close()
    return count, flags


@pytest.mark.unit
def test_suspect_score_counts_only_bad_directions() -> None:
    ref = BinReference(gct_median=0.0, gct_mad=1.0, vo_median=0.0, vo_mad=1.0)

    # GCT longer than usual (gz=+3) and VO smaller (vz=-3): both benign.
    assert suspect_score(3.0, -3.0, ref) == 0.0
    # GCT shorter (gz=-4) and VO larger (vz=+1.5): both add.
    assert suspect_score(-4.0, 1.5, ref) == pytest.approx(5.5)


@pytest.mark.integration
def test_flag_marks_collapsed_pod_splits(initialized_db_path: Path) -> None:
    _seed_reference(initialized_db_path)
    _seed_today(initialized_db_path, [(205.0, 11.2), (252.0, 8.1)])

    count, flags = _flag(initialized_db_path)

    assert count == 1
    assert flags == [True, False]


@pytest.mark.integration
def test_flag_catches_single_axis_collapse(initialized_db_path: Path) -> None:
    _seed_reference(initialized_db_path)
    _seed_today(initialized_db_path, [(205.0, 8.5), (250.0, 13.5)])

    count, flags = _flag(initialized_db_path)

    assert count == 2
    assert flags == [True, True]


@pytest.mark.integration
def test_flag_skips_wrist_and_thin_bins(
    initialized_db_path: Path, tmp_path: Path
) -> None:
    # A wrist run is never flagged, however collapsed it looks.
    _seed_reference(initialized_db_path, source="wrist")
    _seed_today(initialized_db_path, [(205.0, 11.2)], source="wrist")
    assert _flag(initialized_db_path) == (0, [False])

    # A pod bin with fewer than MIN_BIN_SAMPLES reference splits is not scored.
    thin = tmp_path / "thin.duckdb"
    thin.write_bytes(initialized_db_path.read_bytes())
    conn = duckdb.connect(str(thin))
    try:
        conn.execute("DELETE FROM splits")
        conn.execute("DELETE FROM activities")
    finally:
        conn.close()
    _seed_reference(thin, n_splits=MIN_BIN_SAMPLES - 5)
    _seed_today(thin, [(205.0, 11.2)])
    assert _flag(thin) == (0, [False])


@pytest.mark.integration
def test_flag_uses_only_prior_runs(initialized_db_path: Path) -> None:
    # Too few prior splits to score; plenty of later ones that would.
    _seed_reference(initialized_db_path, n_splits=20)
    later = date(2026, 4, 1)
    conn = duckdb.connect(str(initialized_db_path))
    try:
        rng = np.random.default_rng(3)
        for run in range(12):
            activity_id = 5000 + run
            _insert_activity(conn, activity_id, later + timedelta(days=run), "pod")
            for index in range(1, 6):
                _insert_split(
                    conn,
                    activity_id,
                    index,
                    float(rng.normal(255.0, 5.0)),
                    float(rng.normal(8.0, 0.3)),
                )
    finally:
        conn.close()
    _seed_today(initialized_db_path, [(205.0, 11.2)])

    assert _flag(initialized_db_path) == (0, [False])


@pytest.mark.integration
def test_form_split_sql_excludes_suspect(initialized_db_path: Path) -> None:
    conn = duckdb.connect(str(initialized_db_path))
    try:
        _insert_activity(conn, 1, date(2026, 3, 1), "pod")
        for index in range(1, 6):
            _insert_split(conn, 1, index, 250.0, 8.0, suspect=index in (2, 4))
        row = conn.execute(
            f"SELECT COUNT(*) FROM splits WHERE {form_split_sql()}",
            form_split_params(),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None and row[0] == 3


@pytest.mark.integration
def test_trainer_ignores_suspect_splits(initialized_db_path: Path) -> None:
    conn = duckdb.connect(str(initialized_db_path))
    try:
        for run in range(12):
            activity_id = 7000 + run
            _insert_activity(
                conn, activity_id, date(2026, 3, 1) + timedelta(days=run), "pod"
            )
            for index in range(1, 6):
                pace = 330.0 - (run * 5 + index * 12) % 60
                speed = 1000.0 / pace
                conn.execute(
                    """
                    INSERT INTO splits (
                        activity_id, split_index, distance, duration_seconds,
                        pace_seconds_per_km, cadence, ground_contact_time,
                        vertical_oscillation, vertical_ratio, stride_length,
                        average_speed, grade_adjusted_speed, power, role_phase,
                        dynamics_suspect
                    ) VALUES (?, ?, 1.0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'run', ?)
                    """,
                    [
                        activity_id,
                        index,
                        pace,
                        pace,
                        160.0 + 5.0 * speed,
                        300.0 - 20.0 * speed,
                        12.0 - speed,
                        11.0 - speed,
                        1.0 + 0.1 * speed,
                        speed,
                        speed,
                        180.0 + 30.0 * speed,
                        run < 2,  # the first two runs (10 splits) are flagged
                    ],
                )
    finally:
        conn.close()

    result = train_form_baselines(
        end_date="2026-03-31",
        db_path=str(initialized_db_path),
        dynamics_source="pod",
        min_samples=10,
    )

    assert result is not None
    assert result["gct"]["n_samples"] == 50


@pytest.mark.integration
def test_evaluation_uses_clean_splits_only(initialized_db_path: Path) -> None:
    # The model is irrelevant to which splits are averaged; the legacy one will do.
    _seed_baselines(initialized_db_path, ("all",))
    clean = [250.0, 252.0, 254.0, 256.0]
    conn = duckdb.connect(str(initialized_db_path))
    try:
        _insert_activity(conn, 9100, ACTIVITY_DATE, None)
        for index, gct in enumerate([200.0] * 3 + clean, start=1):
            _insert_split(conn, 9100, index, gct, 8.0, pace=PACE, suspect=index <= 3)
    finally:
        conn.close()

    evaluate_and_store(9100, ACTIVITY_DATE, str(initialized_db_path))

    conn = duckdb.connect(str(initialized_db_path), read_only=True)
    try:
        row = conn.execute(
            "SELECT gct_ms_actual FROM form_evaluations WHERE activity_id = 9100"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == pytest.approx(sum(clean) / len(clean))
