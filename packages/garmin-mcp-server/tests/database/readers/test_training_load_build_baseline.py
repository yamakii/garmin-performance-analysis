"""Integration test: ``get_acwr`` adds the build baseline beside the raw ACWR.

Issue #1567. The build baseline and the window composition are new keys; the
existing ACWR keys (``acwr``, ``status``, ...) must stay exactly as before.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.inserters.plan import insert_training_blocks
from garmin_mcp.database.readers.training_load import TrainingLoadReader

# Tuesday; the default week starts on Monday, so 2025-10-27 is the current
# (partial) week and 2025-09-29 .. 2025-10-20 are completed weeks.
END_DATE = "2025-10-28"


@pytest.mark.integration
def test_get_acwr_adds_build_baseline_keeps_raw(reader_db_path: Path) -> None:
    end = date.fromisoformat(END_DATE)
    rows = [
        [
            15670000 + i,
            (end - timedelta(days=i)).isoformat(),
            10.0,
            3000,
            300.0,
            150,
        ]
        for i in range(28)  # 10 km a day, 2025-10-01 .. 2025-10-28
    ]
    conn = duckdb.connect(str(reader_db_path))
    try:
        conn.executemany(
            "INSERT INTO activities (activity_id, activity_date, total_distance_km, "
            "total_time_seconds, avg_pace_seconds_per_km, avg_heart_rate) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
    finally:
        conn.close()
    insert_training_blocks(
        [
            {
                "phase": "build",
                "title": "build block",
                "start_date": "2025-09-29",
                "end_date": "2025-11-09",
                "long_run_ladder": [
                    {"week_start": "2025-10-13", "target_km": 20.0, "kind": "cutback"}
                ],
            }
        ],
        db_path=str(reader_db_path),
    )

    result = TrainingLoadReader(db_path=str(reader_db_path)).get_acwr(end_date=END_DATE)

    # Raw ACWR unchanged: acute 70 km, chronic weekly 280 / 4 = 70 -> 1.0.
    assert result["acute_load_7d"] == 70.0
    assert result["chronic_load_28d_weekly"] == 70.0
    assert result["acwr"] == pytest.approx(1.0)
    assert result["status"] == "optimal"
    assert result["reason_ja"] is None

    baseline = result["build_baseline"]
    assert baseline["status"] == "ok"
    # Build weeks: 09-29 (10-01..10-05 = 50 km), 10-06 (70), 10-20 (70);
    # 10-13 is a registered cutback and the current week 10-27 is excluded.
    assert baseline["weeks_used"] == ["2025-09-29", "2025-10-06", "2025-10-20"]
    assert baseline["weekly_km"] == pytest.approx(63.33, abs=0.01)
    assert baseline["ratio"] == pytest.approx(1.11, abs=0.01)

    composition = result["window_composition"]
    assert [row["week_start"] for row in composition] == [
        "2025-10-06",
        "2025-10-13",
        "2025-10-20",
        "2025-10-27",
    ]
    assert [row["kind"] for row in composition] == [
        "build",
        "cutback",
        "build",
        "build",
    ]
    assert composition[-1]["load_km"] == 20.0  # partial week: Mon + Tue
