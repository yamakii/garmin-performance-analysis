"""The run report counts the splits dropped as collapsed pod dynamics (#1635)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from tests.database.readers.run_report._helpers import (
    ACTIVITY_ID,
    TODAY,
    _report,
    _seed_history,
    _seed_run,
    _signal,
)


def _flag_first(db_path: Path, count: int) -> None:
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            "UPDATE splits SET dynamics_suspect = TRUE "
            "WHERE activity_id = ? AND split_index <= ?",
            [ACTIVITY_ID, count],
        )
    finally:
        conn.close()


@pytest.mark.integration
def test_run_report_exposes_suspect_count(reader_db_path: Path) -> None:
    _seed_history(reader_db_path)
    _seed_run(reader_db_path, activity_id=ACTIVITY_ID, activity_date=TODAY)
    _flag_first(reader_db_path, 2)

    report = _report(reader_db_path)

    assert report is not None
    assert report["sensors"]["dynamics_suspect_splits"] == 2


@pytest.mark.integration
def test_run_report_without_suspect_splits_reports_zero(
    reader_db_path: Path,
) -> None:
    _seed_history(reader_db_path)
    _seed_run(reader_db_path, activity_id=ACTIVITY_ID, activity_date=TODAY)

    report = _report(reader_db_path)

    assert report is not None
    assert report["sensors"]["dynamics_suspect_splits"] == 0


@pytest.mark.integration
def test_too_few_clean_splits_is_reported_as_dynamics_suspect(
    reader_db_path: Path,
) -> None:
    """Dropping the suspect splits is why the run cannot be judged."""
    _seed_history(reader_db_path)
    _seed_run(reader_db_path, activity_id=ACTIVITY_ID, activity_date=TODAY)
    _flag_first(reader_db_path, 4)

    report = _report(reader_db_path)

    assert report is not None
    gct = _signal(report, "gct")
    assert gct["status"] == "insufficient"
    assert gct["reason_code"] == "dynamics_suspect"
