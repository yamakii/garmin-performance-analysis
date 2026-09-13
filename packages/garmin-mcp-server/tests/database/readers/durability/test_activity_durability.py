"""DurabilityReader.get_activity_durability(): decoupling, form fade, cadence / GCT fields."""

from __future__ import annotations

from pathlib import Path

import pytest

from garmin_mcp.database.readers.durability import (
    DurabilityReader,
)
from tests.database.readers.durability._helpers import (
    _form_series,
    _insert_activity,
    _insert_time_series,
    _insert_time_series_rows,
    _insert_time_series_with_cadence,
    _insert_time_series_with_form,
    _series,
)

# Walk breaks: low cadence, walking speed, and no running dynamics (the device
# stops emitting GCT while walking), matching what the fuel stops on the
# 2026-09-13 long run actually recorded (#1102).
_WALK_SAMPLE = (130.0, 1.2, 110.0, None)
_RUN_FRONT_SAMPLE = (150.0, 3.0, 180.0, 260.0)
_RUN_BACK_SAMPLE = (150.0, 3.0, 176.0, 264.0)


def _rows(
    *samples: tuple[range, tuple[float, float, float, float | None]],
) -> list[tuple[int, float | None, float | None, float | None, float | None]]:
    """Expand ``(timestamps, sample)`` pairs into time-series rows."""
    return [(ts, *sample) for timestamps, sample in samples for ts in timestamps]


@pytest.mark.integration
def test_activity_durability_basic(reader_db_path: Path) -> None:
    """Second-half HR rises at constant speed -> decoupling_pct > 0."""
    _insert_activity(
        reader_db_path,
        activity_id=5001,
        activity_date="2025-09-01",
        distance_km=18.0,
    )
    # Front: 150 bpm @ 3.0 m/s; back: 165 bpm @ 3.0 m/s (HR cost up 10%).
    _insert_time_series(
        reader_db_path,
        activity_id=5001,
        rows=_series(front_hr=150.0, front_speed=3.0, back_hr=165.0, back_speed=3.0),
    )

    result = DurabilityReader(db_path=str(reader_db_path)).get_activity_durability(5001)

    assert result is not None
    assert set(result) == {
        "activity_id",
        "activity_date",
        "distance_km",
        "decoupling_pct",
        "pace_fade_pct",
        "gct_fade_pct",
        "vo_fade_pct",
        "vr_fade_pct",
        "gct_fade_ms",
        "cadence_fade_spm",
        "temperature_c",
        "avg_hr",
        "avg_pace_s_per_km",
    }
    assert result["activity_id"] == 5001
    assert result["activity_date"] == "2025-09-01"
    assert result["distance_km"] == pytest.approx(18.0)
    # (165/3.0)/(150/3.0) - 1 = 0.10 -> 10%
    assert result["decoupling_pct"] == pytest.approx(10.0)
    # Speed constant -> no pace fade.
    assert result["pace_fade_pct"] == pytest.approx(0.0)
    # No form metrics seeded in this series -> form fades are None.
    assert result["gct_fade_pct"] is None
    assert result["vo_fade_pct"] is None
    assert result["vr_fade_pct"] is None


@pytest.mark.integration
def test_activity_durability_missing_hr_returns_none(reader_db_path: Path) -> None:
    """All heart_rate values NULL -> no decoupling, returns None."""
    _insert_activity(
        reader_db_path,
        activity_id=5002,
        activity_date="2025-09-02",
        distance_km=20.0,
    )
    _insert_time_series(
        reader_db_path,
        activity_id=5002,
        rows=[(ts, None, 3.0) for ts in range(10)],
    )

    result = DurabilityReader(db_path=str(reader_db_path)).get_activity_durability(5002)

    assert result is None


@pytest.mark.integration
def test_activity_durability_includes_form_fade(reader_db_path: Path) -> None:
    """Back-half GCT 250->270ms -> gct_fade_pct ~ +8.0 alongside decoupling."""
    _insert_activity(
        reader_db_path,
        activity_id=5101,
        activity_date="2025-09-03",
        distance_km=19.0,
    )
    _insert_time_series_with_form(
        reader_db_path,
        activity_id=5101,
        rows=_form_series(
            front_hr=150.0,
            front_speed=3.0,
            back_hr=159.0,
            back_speed=3.0,
            front_gct=250.0,
            back_gct=270.0,
            front_vo=8.0,
            back_vo=8.4,
            front_vr=8.0,
            back_vr=8.8,
        ),
    )

    result = DurabilityReader(db_path=str(reader_db_path)).get_activity_durability(5101)

    assert result is not None
    assert set(result) == {
        "activity_id",
        "activity_date",
        "distance_km",
        "decoupling_pct",
        "pace_fade_pct",
        "gct_fade_pct",
        "vo_fade_pct",
        "vr_fade_pct",
        "gct_fade_ms",
        "cadence_fade_spm",
        "temperature_c",
        "avg_hr",
        "avg_pace_s_per_km",
    }
    # (270/250 - 1) * 100 = 8.0
    assert result["gct_fade_pct"] == pytest.approx(8.0)
    # (8.4/8.0 - 1) * 100 = 5.0
    assert result["vo_fade_pct"] == pytest.approx(5.0)
    # (8.8/8.0 - 1) * 100 = 10.0
    assert result["vr_fade_pct"] == pytest.approx(10.0)
    # Decoupling still computed independently.
    assert result["decoupling_pct"] == pytest.approx(6.0)


@pytest.mark.integration
def test_activity_durability_form_fade_null_when_missing(
    reader_db_path: Path,
) -> None:
    """GCT null in the series -> gct_fade_pct is None; decoupling still computed."""
    _insert_activity(
        reader_db_path,
        activity_id=5102,
        activity_date="2025-09-04",
        distance_km=20.0,
    )
    # HR/speed present, all form metrics null (older device).
    _insert_time_series_with_form(
        reader_db_path,
        activity_id=5102,
        rows=_form_series(
            front_hr=150.0,
            front_speed=3.0,
            back_hr=165.0,
            back_speed=3.0,
            front_gct=None,
            back_gct=None,
            front_vo=None,
            back_vo=None,
            front_vr=None,
            back_vr=None,
        ),
    )

    result = DurabilityReader(db_path=str(reader_db_path)).get_activity_durability(5102)

    assert result is not None
    # Decoupling unaffected by absent form metrics.
    assert result["decoupling_pct"] == pytest.approx(10.0)
    assert result["gct_fade_pct"] is None
    assert result["vo_fade_pct"] is None
    assert result["vr_fade_pct"] is None


@pytest.mark.integration
def test_get_activity_durability_includes_cadence_and_gct_ms(
    reader_db_path: Path,
) -> None:
    """Absolute half-split deltas: cadence 172->168 spm, GCT 258->266 ms."""
    _insert_activity(
        reader_db_path,
        activity_id=5201,
        activity_date="2026-08-23",
        distance_km=19.0,
        temp_celsius=27.4,
    )
    _insert_time_series_with_cadence(
        reader_db_path,
        activity_id=5201,
        front_cadence=172.0,
        back_cadence=168.0,
        front_gct=258.0,
        back_gct=266.0,
    )

    result = DurabilityReader(db_path=str(reader_db_path)).get_activity_durability(5201)

    assert result is not None
    assert result["cadence_fade_spm"] == pytest.approx(-4.0)
    assert result["gct_fade_ms"] == pytest.approx(8.0)
    # Activity-level context ships alongside so the gate needs no extra query.
    assert result["temperature_c"] == pytest.approx(27.4)
    assert result["avg_hr"] == pytest.approx(150.0)
    assert result["avg_pace_s_per_km"] == pytest.approx(300.0)
    # The ratio-based fade is unchanged: (266/258 - 1) * 100 = 3.1%.
    assert result["gct_fade_pct"] == pytest.approx(3.1, abs=0.01)


@pytest.mark.integration
def test_cadence_fade_excludes_walk_breaks(reader_db_path: Path) -> None:
    """Walk breaks in the second half must not read as a cadence collapse (#1102).

    Front: 10 running samples at 180 spm. Back: 6 running at 176 spm plus 4
    walking at 110 spm. Averaging every sample gives a back cadence of 149.6
    (fade -30.4, far past the gate's -5 trigger); averaging only the running
    samples gives 176 (fade -4.0), which is what the athlete's form actually did.
    """
    _insert_activity(
        reader_db_path,
        activity_id=5301,
        activity_date="2026-09-13",
        distance_km=25.1,
    )
    _insert_time_series_rows(
        reader_db_path,
        activity_id=5301,
        rows=_rows(
            (range(0, 10), _RUN_FRONT_SAMPLE),
            (range(10, 16), _RUN_BACK_SAMPLE),
            (range(16, 20), _WALK_SAMPLE),
        ),
    )

    result = DurabilityReader(db_path=str(reader_db_path)).get_activity_durability(5301)

    assert result is not None
    assert result["cadence_fade_spm"] == pytest.approx(-4.0)


@pytest.mark.integration
def test_walk_breaks_still_counted_for_decoupling_and_pace(
    reader_db_path: Path,
) -> None:
    """The walk filter is scoped to cadence: HR/speed/GCT aggregate unchanged (#1102).

    Same series as the cadence test. Decoupling and pace fade keep averaging
    every sample -- walking biases them *against* the athlete, so leaving them
    alone can only understate durability, never wave a bad run through.
    """
    _insert_activity(
        reader_db_path,
        activity_id=5302,
        activity_date="2026-09-13",
        distance_km=25.1,
    )
    _insert_time_series_rows(
        reader_db_path,
        activity_id=5302,
        rows=_rows(
            (range(0, 10), _RUN_FRONT_SAMPLE),
            (range(10, 16), _RUN_BACK_SAMPLE),
            (range(16, 20), _WALK_SAMPLE),
        ),
    )

    result = DurabilityReader(db_path=str(reader_db_path)).get_activity_durability(5302)

    assert result is not None
    # back_hr = (6*150 + 4*130)/10 = 142; back_speed = (6*3.0 + 4*1.2)/10 = 2.28.
    # (142/2.28)/(150/3.0) - 1 = 24.56%
    assert result["decoupling_pct"] == pytest.approx(24.56, abs=0.01)
    # 3.0/2.28 - 1 = 31.58%
    assert result["pace_fade_pct"] == pytest.approx(31.58, abs=0.01)
    # GCT is null while walking, so its average was never contaminated: 264-260.
    assert result["gct_fade_ms"] == pytest.approx(4.0)


@pytest.mark.integration
def test_cadence_fade_unchanged_without_walk_breaks(reader_db_path: Path) -> None:
    """A run with no walking is unaffected by the filter (#1102 regression guard)."""
    _insert_activity(
        reader_db_path,
        activity_id=5303,
        activity_date="2026-08-30",
        distance_km=19.0,
    )
    _insert_time_series_rows(
        reader_db_path,
        activity_id=5303,
        rows=_rows(
            (range(0, 10), _RUN_FRONT_SAMPLE),
            (range(10, 20), _RUN_BACK_SAMPLE),
        ),
    )

    result = DurabilityReader(db_path=str(reader_db_path)).get_activity_durability(5303)

    assert result is not None
    assert result["cadence_fade_spm"] == pytest.approx(-4.0)
    assert result["decoupling_pct"] == pytest.approx(0.0)
    assert result["pace_fade_pct"] == pytest.approx(0.0)


@pytest.mark.integration
def test_cadence_fade_none_when_a_half_is_all_walking(reader_db_path: Path) -> None:
    """No running sample in a half -> cadence_fade_spm is None, not a bogus number."""
    _insert_activity(
        reader_db_path,
        activity_id=5304,
        activity_date="2026-09-20",
        distance_km=12.0,
    )
    _insert_time_series_rows(
        reader_db_path,
        activity_id=5304,
        rows=_rows(
            (range(0, 10), _WALK_SAMPLE),
            (range(10, 20), _RUN_BACK_SAMPLE),
        ),
    )

    result = DurabilityReader(db_path=str(reader_db_path)).get_activity_durability(5304)

    # HR/speed are present throughout, so the activity still reports durability.
    assert result is not None
    assert result["decoupling_pct"] is not None
    assert result["cadence_fade_spm"] is None
