"""Integration test for ``GarminDBReader.get_energy_balance`` (issue #1434).

Seeds the observed 2026-09-17..09-26 ``daily_energy`` values and a 維持 block
into a tmp DuckDB and checks the window mean, the verdict and the statuses.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.db_reader import GarminDBReader

# date -> (intake, total, bmr, active); coverage is a full day except 09-26.
_OBSERVED: dict[str, tuple[int, int, int, int]] = {
    "2026-09-17": (1581, 2392, 1971, 421),
    "2026-09-18": (1405, 2365, 1969, 396),
    "2026-09-19": (1866, 3039, 1966, 1073),
    "2026-09-20": (2009, 2090, 1971, 119),
    "2026-09-21": (1777, 1984, 1981, 3),
    "2026-09-22": (1505, 2316, 1969, 347),
    "2026-09-23": (1915, 2519, 1973, 546),
    "2026-09-24": (2516, 2265, 1973, 292),
    "2026-09-25": (1574, 2235, 1973, 262),
    "2026-09-26": (909, 851, 850, 1),
}


def _seed(db_path: Path) -> None:
    conn = duckdb.connect(str(db_path))
    try:
        for day_str, (intake, total, bmr, active) in _OBSERVED.items():
            day = date.fromisoformat(day_str)
            partial = day_str == "2026-09-26"
            coverage = 37_260 if partial else 86_400
            # Fetched the following morning (a nightly sync); today mid-morning.
            fetched = (
                datetime(2026, 9, 26, 10, 21)
                if partial
                else datetime.combine(day + timedelta(days=1), datetime.min.time())
                + timedelta(hours=6)
            )
            conn.execute(
                "INSERT INTO daily_energy (date, consumed_kcal, includes_consumed, "
                "total_kcal, active_kcal, bmr_kcal, coverage_seconds, "
                "awake_seconds, asleep_seconds, fetched_at, first_fetched_at, "
                "post_close_revisions) VALUES (?, ?, TRUE, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
                [
                    day_str,
                    intake,
                    total,
                    active,
                    bmr,
                    coverage,
                    coverage - 25_000,
                    25_000,
                    fetched,
                    fetched,
                ],
            )
        conn.execute(
            "INSERT INTO training_blocks "
            "(block_id, sequence, phase, title, start_date, end_date, weight_mode) "
            "VALUES (1, 1, 'build', 'block', '2026-09-01', '2026-10-31', '維持')"
        )
    finally:
        conn.close()


@pytest.mark.integration
def test_get_energy_balance_reader_real_week(initialized_db_path: Path) -> None:
    _seed(initialized_db_path)

    result = GarminDBReader(db_path=str(initialized_db_path)).get_energy_balance(
        end_date="2026-09-25", as_of="2026-09-26"
    )

    json.dumps(result)
    window = result["window"]
    assert window["status"] == "ok"
    assert window["paired_days"] == 7
    assert window["mean_balance_kcal"] == -469
    assert window["provisional_days"] == 7

    target = result["target"]
    assert target["weight_mode"] == "維持"
    assert target["block_id"] == 1
    assert target["crosses_block_boundary"] is False
    assert target["verdict"] == "deeper_than_target"
    assert target["basis"] == "logged"

    by_date = {d["date"]: d for d in result["days"]}
    for day in range(19, 26):
        row = by_date[f"2026-09-{day}"]
        assert row["intake_status"] == "provisional"
        assert row["used"] is True
    today = by_date["2026-09-26"]
    assert today["intake_status"] == "in_progress"
    assert today["in_window"] is False
    assert today["used"] is False

    assert result["calibration"]["status"] == "insufficient"
    assert result["logging"]["last_logged_date"] == "2026-09-25"
    assert result["logging"]["lapsed"] is False
