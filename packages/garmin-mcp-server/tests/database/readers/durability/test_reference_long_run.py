"""DurabilityReader.find_reference_long_run(): temperature band, race / short-run exclusion, lookback."""

from __future__ import annotations

from pathlib import Path

import pytest

from garmin_mcp.database.readers.durability import (
    DurabilityReader,
)
from tests.database.readers.durability._helpers import (
    _insert_activity,
    _insert_time_series_with_cadence,
)


@pytest.mark.integration
def test_find_reference_long_run_prefers_temperature_band(
    reader_db_path: Path,
) -> None:
    """A cooler 21-day-old peer beats a hotter 14-day-old one (34 C is +7)."""
    _insert_activity(
        reader_db_path,
        activity_id=6001,
        activity_date="2026-08-30",
        distance_km=19.0,
        temp_celsius=27.0,
    )
    # 14 days earlier, 18 km but 34 C -> outside the +/-5 C band.
    _insert_activity(
        reader_db_path,
        activity_id=6002,
        activity_date="2026-08-16",
        distance_km=18.0,
        temp_celsius=34.0,
    )
    # 21 days earlier, 17 km at 26 C -> same conditions.
    _insert_activity(
        reader_db_path,
        activity_id=6003,
        activity_date="2026-08-09",
        distance_km=17.0,
        temp_celsius=26.0,
    )
    for activity_id in (6002, 6003):
        _insert_time_series_with_cadence(
            reader_db_path,
            activity_id=activity_id,
            front_cadence=172.0,
            back_cadence=170.0,
            front_gct=255.0,
            back_gct=259.0,
        )

    reference = DurabilityReader(db_path=str(reader_db_path)).find_reference_long_run(
        6001
    )

    assert reference is not None
    assert reference["activity_id"] == 6003
    assert reference["temp_diff_c"] == pytest.approx(-1.0)
    assert reference["gct_fade_ms"] == pytest.approx(4.0)


@pytest.mark.integration
def test_find_reference_long_run_excludes_races_and_short_runs(
    reader_db_path: Path,
) -> None:
    """Races (by name) and sub-10 km jogs are never the reference."""
    _insert_activity(
        reader_db_path,
        activity_id=6101,
        activity_date="2026-10-25",
        distance_km=19.0,
        temp_celsius=15.0,
    )
    # A race at a comparable distance: excluded by name, not by distance.
    _insert_activity(
        reader_db_path,
        activity_id=6102,
        activity_date="2026-10-11",
        distance_km=20.0,
        temp_celsius=16.0,
        activity_name="新潟シティマラソン 30k走",
    )
    _insert_activity(
        reader_db_path,
        activity_id=6103,
        activity_date="2026-10-04",
        distance_km=42.2,
        temp_celsius=15.5,
        activity_name="新潟シティマラソン",
    )
    _insert_activity(
        reader_db_path,
        activity_id=6104,
        activity_date="2026-10-18",
        distance_km=6.0,
        temp_celsius=15.0,
        activity_name="朝ジョグ",
    )
    for activity_id in (6102, 6103, 6104):
        _insert_time_series_with_cadence(
            reader_db_path,
            activity_id=activity_id,
            front_cadence=172.0,
            back_cadence=170.0,
            front_gct=255.0,
            back_gct=259.0,
        )

    reference = DurabilityReader(db_path=str(reader_db_path)).find_reference_long_run(
        6101
    )

    assert reference is None


@pytest.mark.integration
def test_find_reference_long_run_respects_lookback(reader_db_path: Path) -> None:
    """A comparable run 70 days back is outside the 56-day window."""
    _insert_activity(
        reader_db_path,
        activity_id=6201,
        activity_date="2026-09-01",
        distance_km=19.0,
        temp_celsius=25.0,
    )
    _insert_activity(
        reader_db_path,
        activity_id=6202,
        activity_date="2026-06-23",  # 70 days earlier
        distance_km=19.0,
        temp_celsius=25.0,
    )
    _insert_time_series_with_cadence(
        reader_db_path,
        activity_id=6202,
        front_cadence=172.0,
        back_cadence=170.0,
        front_gct=255.0,
        back_gct=259.0,
    )

    reader = DurabilityReader(db_path=str(reader_db_path))

    assert reader.find_reference_long_run(6201) is None
    # Widening the window past 70 days finds it again.
    assert (reader.find_reference_long_run(6201, lookback_days=90) or {}).get(
        "activity_id"
    ) == 6202
