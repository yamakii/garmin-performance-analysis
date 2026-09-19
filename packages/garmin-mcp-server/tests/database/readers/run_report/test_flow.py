"""The series the run-flow chart draws (#1268).

The report ships what is drawn: one fragment rule for pace and heart rate, a rep
recorded as two splits drawn as one segment, and the main set drawn split by
split while the bookends stay whole.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.database.readers.run_report._helpers import (
    ACTIVITY_ID,
    TODAY,
    _report,
    _seed_run,
    _seed_splits,
)


@pytest.mark.integration
def test_flow_series_share_one_fragment_rule(reader_db_path: Path) -> None:
    """Pace and heart rate are drawn from one series, so one fragment rule.

    The shipped page dropped the sub-0.4 km splits from the pace line while
    still plotting them on the HR line; now the report ships what is drawn.
    """
    _seed_run(reader_db_path, activity_id=ACTIVITY_ID, activity_date=TODAY)
    _seed_splits(
        reader_db_path,
        ACTIVITY_ID,
        [
            *[(1.0, 360.0, "run") for _ in range(5)],
            (0.014, 5.0, "run"),
            (0.010, 4.0, "run"),
        ],
    )

    report = _report(reader_db_path)

    assert report is not None
    flow = report["flow"]
    assert flow["axis"] == "distance"
    assert len(flow["segments"]) == 5
    assert flow["segments"][-1]["end_km"] == 5.0
    assert flow["fragments"]["count"] == 2
    assert flow["fragments"]["distance_km"] == pytest.approx(0.02, abs=0.01)


@pytest.mark.integration
def test_flow_short_steps_are_one_segment(reader_db_path: Path) -> None:
    """4/20: a rep recorded as two splits is drawn as one segment."""
    _seed_run(reader_db_path, activity_id=ACTIVITY_ID, activity_date=TODAY)
    _seed_splits(
        reader_db_path,
        ACTIVITY_ID,
        [
            (1.0, 393.0, "warmup"),
            (0.51, 207.0, "warmup"),
            (1.0, 324.0, "run"),
            (0.11, 36.0, "run"),
            (0.18, 120.0, "recovery"),
            (1.0, 320.0, "run"),
            (0.13, 40.0, "run"),
            (0.91, 600.0, "cooldown"),
            (0.16, 75.0, "cooldown"),
        ],
    )

    report = _report(reader_db_path)

    assert report is not None
    flow = report["flow"]
    assert flow["axis"] == "time"
    assert len(flow["segments"]) == 5
    first_rep = flow["segments"][1]
    assert (first_rep["split_from"], first_rep["split_to"]) == (3, 4)
    assert (first_rep["start_s"], first_rep["end_s"]) == (600, 960)


@pytest.mark.integration
def test_flow_long_step_draws_inner_splits(reader_db_path: Path) -> None:
    """9/9: the 5 km main set is drawn split by split, the bookends whole."""
    _seed_run(reader_db_path, activity_id=ACTIVITY_ID, activity_date=TODAY)
    _seed_splits(
        reader_db_path,
        ACTIVITY_ID,
        [
            (0.93, 400.0, "warmup"),
            *[(1.0, 300.0, "run") for _ in range(5)],
            (0.13, 60.0, "cooldown"),
            (1.0, 420.0, "cooldown"),
            (0.05, 20.0, "cooldown"),
            (0.03, 12.0, "cooldown"),
        ],
    )

    report = _report(reader_db_path)

    assert report is not None
    assert len(report["flow"]["segments"]) == 7
    assert [step["label_ja"] for step in report["flow"]["steps"]] == [
        "ウォームアップ",
        "本編",
        "クールダウン",
    ]


@pytest.mark.integration
def test_run_report_json_serialisable_with_flow(reader_db_path: Path) -> None:
    """The flow block goes over the MCP boundary with no custom encoder."""
    _seed_run(reader_db_path, activity_id=ACTIVITY_ID, activity_date=TODAY)
    _seed_splits(
        reader_db_path,
        ACTIVITY_ID,
        [
            (1.2, 480.0, "warmup"),
            (1.0, 300.0, "run"),
            (0.4, 180.0, "recovery"),
            (1.0, 298.0, "run"),
            (1.0, 420.0, "cooldown"),
        ],
    )

    report = _report(reader_db_path)

    assert report is not None
    assert json.loads(json.dumps(report))["flow"] == report["flow"]
