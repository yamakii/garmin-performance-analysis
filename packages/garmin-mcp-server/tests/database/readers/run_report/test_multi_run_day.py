"""A day's prescription belongs to the run that answers it (#1601).

A long run plus a short cooldown on the same day: only the long run is judged
against the long-run prescription; the cooldown reads as unprescribed instead
of a 3 % long run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.database.readers.run_report._helpers import (
    TODAY,
    _report,
    _seed_history,
    _seed_prescription,
    _seed_run,
)

_LONG = 9100001601
_COOLDOWN = 9100001602


@pytest.mark.integration
def test_run_report_second_run_is_unprescribed(reader_db_path: Path) -> None:
    _seed_history(reader_db_path)
    _seed_run(
        reader_db_path,
        activity_id=_LONG,
        activity_date=TODAY,
        distance_km=28.0,
        duration_s=11300,
        pace=403.0,
    )
    _seed_run(
        reader_db_path,
        activity_id=_COOLDOWN,
        activity_date=TODAY,
        distance_km=0.8,
        duration_s=390,
        pace=487.0,
        n_splits=1,
    )
    _seed_prescription(
        reader_db_path,
        on_date=TODAY,
        session_type="long",
        title="ロング 28km",
        target_km=28.0,
    )

    long_report = _report(reader_db_path, _LONG)
    cooldown_report = _report(reader_db_path, _COOLDOWN)

    assert long_report is not None
    assert long_report["plan"] is not None
    assert long_report["plan"]["title"] == "ロング 28km"
    assert cooldown_report is not None
    assert cooldown_report["plan"] is None
