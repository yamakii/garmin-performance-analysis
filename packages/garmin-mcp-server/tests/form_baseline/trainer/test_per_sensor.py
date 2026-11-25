"""Form baselines are trained and applied per dynamics sensor (#1631)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.form_baseline.power_calculator import (
    calculate_power_efficiency_internal,
)
from garmin_mcp.form_baseline.trainer import (
    ensure_form_baselines_for_date,
    train_form_baselines,
    train_power_efficiency_baseline,
)
from tests.form_baseline.trainer._helpers import _create_baseline_schema

END_DATE = "2026-03-31"  # 2-month window 2026-02-01 .. 2026-03-31


def _split_rows(
    activity_id: int, gct_offset: float = 0.0, power_offset: float = 0.0
) -> list[tuple]:
    """Five full 1 km splits whose GCT / power sit ``offset`` above the base curve."""
    rows = []
    for j in range(5):
        pace = 330.0 - (activity_id * 5 + j * 12) % 60
        speed = 1000.0 / pace
        rows.append(
            (
                activity_id * 10 + j,
                activity_id,
                pace,
                300.0 - 20.0 * speed + gct_offset,
                12.0 - 1.0 * speed,
                11.0 - 1.0 * speed,
                1.0 + 0.1 * speed,
                160.0 + 5.0 * speed,
                speed,
                speed,
                180.0 + 30.0 * speed + power_offset,
                "run",
                1.0,
            )
        )
    return rows


_NEXT_ID = {"value": 10_000}


def _seed(
    db_path: str,
    source: str | None,
    dates: list[date],
    *,
    gct_offset: float = 0.0,
    power_offset: float = 0.0,
    create: bool = False,
) -> list[int]:
    """One 5-split activity per date for ``source``; returns the activity ids."""
    conn = duckdb.connect(db_path)
    try:
        if create:
            _create_baseline_schema(conn)
        ids = []
        for day in dates:
            _NEXT_ID["value"] += 1
            activity_id = _NEXT_ID["value"]
            ids.append(activity_id)
            conn.execute(
                "INSERT INTO activities "
                "(activity_id, activity_date, base_weight_kg, dynamics_source) "
                "VALUES (?, ?, 70.0, ?)",
                [activity_id, day, source],
            )
            conn.executemany(
                "INSERT INTO splits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                _split_rows(activity_id, gct_offset, power_offset),
            )
        return ids
    finally:
        conn.close()


def _days(start: date, count: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(count)]


def _rows(db_path: str, sql: str) -> list[tuple]:
    conn = duckdb.connect(db_path, read_only=True)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


@pytest.mark.integration
def test_train_filters_by_dynamics_source(tmp_path: Path) -> None:
    """60 pod + 60 wrist splits: the wrist model is a wrist-only fit."""
    mixed = str(tmp_path / "mixed.duckdb")
    _seed(mixed, "pod", _days(date(2026, 3, 1), 12), gct_offset=30.0, create=True)
    _seed(mixed, "wrist", _days(date(2026, 3, 10), 12))

    wrist_only = str(tmp_path / "wrist_only.duckdb")
    _seed(wrist_only, "wrist", _days(date(2026, 3, 10), 12), create=True)

    result = train_form_baselines(
        end_date=END_DATE, db_path=mixed, dynamics_source="wrist"
    )
    reference = train_form_baselines(
        end_date=END_DATE, db_path=wrist_only, dynamics_source="wrist"
    )

    assert result is not None and reference is not None
    assert result["gct"]["n_samples"] == 60
    assert result["gct"]["alpha"] == pytest.approx(reference["gct"]["alpha"])
    assert result["gct"]["d"] == pytest.approx(reference["gct"]["d"])
    assert result["vo"]["a"] == pytest.approx(reference["vo"]["a"])

    sources = _rows(mixed, "SELECT DISTINCT dynamics_source FROM form_baseline_history")
    assert sources == [("wrist",)]


@pytest.mark.integration
def test_train_widens_window_for_thin_sensor(tmp_path: Path) -> None:
    """30 wrist splits in the last 2 months + 30 in month 4: window grows to 4."""
    db_path = str(tmp_path / "widen.duckdb")
    _seed(db_path, "wrist", _days(date(2026, 3, 5), 6), create=True)
    _seed(db_path, "wrist", _days(date(2025, 12, 10), 6))

    result = train_form_baselines(
        end_date=END_DATE, db_path=db_path, dynamics_source="wrist"
    )

    assert result is not None
    assert result["period_start"] == "2025-12-01"
    assert result["gct"]["n_samples"] == 60
    stored = _rows(
        db_path,
        "SELECT DISTINCT CAST(period_start AS VARCHAR) FROM form_baseline_history "
        "WHERE metric = 'gct'",
    )
    assert stored == [("2025-12-01",)]


@pytest.mark.integration
def test_train_gives_up_past_max_window(tmp_path: Path) -> None:
    """40 wrist splits over 6 months stay short; pod splits are never borrowed."""
    db_path = str(tmp_path / "giveup.duckdb")
    wrist_days = [date(2025, 10, 5) + timedelta(days=22 * i) for i in range(8)]
    _seed(db_path, "wrist", wrist_days, create=True)
    _seed(db_path, "pod", _days(date(2026, 3, 1), 12))

    result = train_form_baselines(
        end_date=END_DATE, db_path=db_path, dynamics_source="wrist"
    )

    assert result is None
    assert _rows(db_path, "SELECT COUNT(*) FROM form_baseline_history") == [(0,)]


@pytest.mark.integration
def test_ensure_trains_only_activity_sensor(tmp_path: Path) -> None:
    """Self-heal for a pod run adds 'pod' rows and nothing for the wrist."""
    db_path = str(tmp_path / "ensure.duckdb")
    pod_days = _days(date(2026, 2, 3), 12) + _days(date(2026, 3, 3), 12)
    wrist_days = _days(date(2026, 2, 5), 12) + _days(date(2026, 3, 5), 12)
    _seed(db_path, "pod", pod_days, create=True)
    _seed(db_path, "wrist", wrist_days, gct_offset=25.0)

    result = ensure_form_baselines_for_date(
        "2026-03-15", db_path, dynamics_source="pod"
    )

    assert set(result["generated"]) == {"2026-03-31", "2026-02-28"}
    sources = _rows(
        db_path, "SELECT DISTINCT dynamics_source FROM form_baseline_history"
    )
    assert sources == [("pod",)]

    # The wrist baseline is still missing, so it is generated on its own.
    again = ensure_form_baselines_for_date("2026-03-15", db_path, dynamics_source="pod")
    assert again["generated"] == []
    assert set(again["skipped"]) == {"2026-03-31", "2026-02-28"}


@pytest.mark.integration
def test_power_efficiency_per_sensor(tmp_path: Path) -> None:
    """Power rows are written per sensor and the calculator reads its own."""
    db_path = str(tmp_path / "power.duckdb")
    pod_ids = _seed(
        db_path, "pod", _days(date(2026, 3, 1), 10), power_offset=40.0, create=True
    )
    wrist_ids = _seed(db_path, "wrist", _days(date(2026, 3, 12), 10))
    conn = duckdb.connect(db_path)
    conn.execute(
        "CREATE TABLE hr_efficiency (activity_id INTEGER PRIMARY KEY, "
        "training_type VARCHAR)"
    )
    conn.close()

    pod = train_power_efficiency_baseline(
        end_date=END_DATE, db_path=db_path, dynamics_source="pod"
    )
    wrist = train_power_efficiency_baseline(
        end_date=END_DATE, db_path=db_path, dynamics_source="wrist"
    )

    assert pod is not None and wrist is not None
    assert pod["n_samples"] == 50 and wrist["n_samples"] == 50
    stored = _rows(
        db_path,
        "SELECT dynamics_source, power_a, power_b FROM form_baseline_history "
        "WHERE metric = 'power' ORDER BY dynamics_source",
    )
    assert [row[0] for row in stored] == ["pod", "wrist"]
    assert stored[0][1] != pytest.approx(stored[1][1], abs=1e-3)

    conn = duckdb.connect(db_path)
    try:
        by_sensor = {}
        for sensor, activity_id in (("pod", pod_ids[0]), ("wrist", wrist_ids[0])):
            by_sensor[sensor] = calculate_power_efficiency_internal(
                conn,
                activity_id,
                "2026-03-20",
                dynamics_source=sensor,
            )
        # The wrist run read against the pod row would see a different baseline.
        crossed = calculate_power_efficiency_internal(
            conn, wrist_ids[0], "2026-03-20", dynamics_source="pod"
        )
        missing = calculate_power_efficiency_internal(
            conn, wrist_ids[0], "2026-03-20", dynamics_source="strap"
        )
    finally:
        conn.close()

    assert by_sensor["pod"] is not None and by_sensor["wrist"] is not None
    assert crossed is not None
    assert by_sensor["wrist"]["speed_expected_mps"] != pytest.approx(
        crossed["speed_expected_mps"], abs=1e-3
    )
    assert missing is None
