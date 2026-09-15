"""Reader tests for the per-split form-anomaly map (#1132).

``GarminDBReader.get_split_form_anomalies`` runs the real form-anomaly detector
over synthetic raw ``activity_details.json`` and maps each anomaly's elapsed-second
timestamp onto the ``splits`` table's time ranges, so the Web splits table can
highlight exactly the kilometres whose form moved. These tests drive the whole
path end to end (raw JSON -> detector -> split map) for both 1 Hz and 2 s-sampled
raw data (#1137), plus the two "nothing to highlight" degradations (no raw file,
no split rows).
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.db_reader import GarminDBReader

_CREATE_SPLITS = """
    CREATE TABLE splits (
        activity_id BIGINT,
        split_index INTEGER,
        distance DOUBLE,
        duration_seconds DOUBLE,
        start_time_s INTEGER,
        end_time_s INTEGER
    )
"""

# Raw Garmin metric descriptors the detector parses: HR, speed (factor 0.1 ->
# m/s), GCT (ms), VO (factor 10 -> cm) and elevation (m). Elevation is included
# so a GCT spike on a climb classifies as ``elevation_change`` (material) rather
# than isolated noise.
_METRIC_DESCRIPTORS = [
    {
        "metricsIndex": 0,
        "key": "directHeartRate",
        "unit": {"id": 100, "key": "bpm", "factor": 1.0},
    },
    {
        "metricsIndex": 1,
        "key": "directSpeed",
        "unit": {"id": 20, "key": "mps", "factor": 0.1},
    },
    {
        "metricsIndex": 2,
        "key": "directGroundContactTime",
        "unit": {"id": 40, "key": "ms", "factor": 1.0},
    },
    {
        "metricsIndex": 3,
        "key": "directVerticalOscillation",
        "unit": {"id": 200, "key": "cm", "factor": 10.0},
    },
    {
        "metricsIndex": 4,
        "key": "directElevation",
        "unit": {"id": 300, "key": "m", "factor": 1.0},
    },
]

# Per-sample elapsed seconds, present only in the downsampled fixture (#1137).
_DURATION_DESCRIPTOR = {
    "metricsIndex": 5,
    "key": "sumDuration",
    "unit": {"id": 40, "key": "second", "factor": 1000.0},
}

_SERIES_LEN = 600

# Seconds carrying the GCT spike. Three flagged seconds two apart span 5 s, so
# the detector's sustained-run filter (>= 5 s, adjacency tolerance 2 s) keeps
# them, while only 3 of the 60 samples in the rolling window are elevated -- a
# genuinely *sustained* 60 s block would fill the ±30 s window, collapse its
# std to ~0 and produce no z-score at all.
_SPIKE_SECONDS = (400, 402, 404)

# Same spike for the 2 s-sampled fixture: three consecutive samples cover 6 s of
# running (>= the 5 s sustained gate) and sit at elapsed 400/402/404 s (#1137).
_SPIKE_INDICES = (200, 201, 202)


def _elevation(index: int, climb_start: int = 396) -> float:
    """Flat 10 m with a 2 m/sample climb over 14 samples from ``climb_start``.

    The climb is positioned to span the GCT spike (which sits 4 samples after
    ``climb_start``) so the spike classifies as ``elevation_change``.
    """
    climb_end = climb_start + 14
    if index < climb_start:
        return 10.0
    if index > climb_end:
        return 38.0
    return 10.0 + 2.0 * (index - climb_start)


def _write_activity_details(
    base_path: Path, activity_id: int, sample_interval: int | None = None
) -> None:
    """Write raw details: flat form metrics plus a GCT spike on a climb.

    ``sample_interval`` writes a ``sumDuration`` descriptor with that many
    seconds per sample (Garmin downsamples long activities to 2 s, #1137); the
    spike then sits at ``_SPIKE_INDICES`` and lands on twice their second.
    Without it the file carries no duration at all, the legacy 1 Hz case where
    index and elapsed second coincide.
    """
    descriptors = list(_METRIC_DESCRIPTORS)
    spike_samples: tuple[int, ...] = _SPIKE_SECONDS
    if sample_interval is not None:
        descriptors = [*descriptors, _DURATION_DESCRIPTOR]
        spike_samples = _SPIKE_INDICES
    climb_start = spike_samples[0] - 4

    rows = []
    for index in range(_SERIES_LEN):
        gct = 290.0 if index in spike_samples else 240.0
        values: list[float] = [140, 28, gct, 80, _elevation(index, climb_start)]
        if sample_interval is not None:
            values.append(float(index * sample_interval))
        rows.append({"metrics": values})
    payload = {
        "activityId": activity_id,
        "measurementCount": len(rows),
        "metricDescriptors": descriptors,
        "activityDetailMetrics": rows,
    }
    activity_dir = base_path / "raw" / "activity" / str(activity_id)
    activity_dir.mkdir(parents=True, exist_ok=True)
    (activity_dir / "activity_details.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _build_db(
    base_path: Path,
    activity_id: int,
    splits: list[tuple[int, int, int]],
) -> Path:
    """Create <base>/database/garmin.duckdb with the given split time ranges.

    ``splits`` are ``(split_index, start_time_s, end_time_s)``. The DB sits one
    level under ``base_path`` so the reader derives ``base_path`` as the
    detector's raw-data root.
    """
    db_dir = base_path / "database"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / "garmin.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(_CREATE_SPLITS)
        if not splits:
            return db_path
        conn.executemany(
            "INSERT INTO splits (activity_id, split_index, distance, "
            "duration_seconds, start_time_s, end_time_s) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (activity_id, index, 1.0, float(end - start + 1), start, end)
                for index, start, end in splits
            ],
        )
    finally:
        conn.close()
    return db_path


@pytest.mark.integration
def test_get_split_form_anomalies_counts(tmp_path: Path) -> None:
    """A GCT spike at 400-404 s lands in split 2 (301-600 s) and nowhere else.

    End-to-end through the real detector: the spike sits on a climb, so it is
    material (``elevation_change``) and severe (|z| > 3.5). Split 1 stays clean
    and is therefore absent from the list entirely.
    """
    activity_id = 9500000001
    db_path = _build_db(tmp_path, activity_id, [(1, 0, 300), (2, 301, 600)])
    _write_activity_details(tmp_path, activity_id)

    result = GarminDBReader(db_path=str(db_path)).get_split_form_anomalies(activity_id)

    assert result["activity_id"] == activity_id
    assert [row["split_index"] for row in result["splits"]] == [2]
    flagged = result["splits"][0]
    assert flagged["anomalies"] >= 1
    assert flagged["material"] >= 1
    assert flagged["metrics"] == ["gct"]
    assert flagged["max_z"] >= 3.5
    assert result["total"] == sum(row["anomalies"] for row in result["splits"])
    assert result["material"] == sum(row["material"] for row in result["splits"])


@pytest.mark.integration
def test_split_anomalies_with_2s_sampling(tmp_path: Path) -> None:
    """A 2 s-sampled spike at samples 200-202 maps to split 2, not split 1.

    The raw file carries ``sumDuration`` (0, 2, 4, ...), so the spike's elapsed
    seconds are 400-404 and fall in split 2 (301-600 s). Before #1137 the sample
    index was reported as the timestamp and the same spike was mis-mapped onto
    split 1.
    """
    activity_id = 9500000004
    db_path = _build_db(tmp_path, activity_id, [(1, 0, 300), (2, 301, 600)])
    _write_activity_details(tmp_path, activity_id, sample_interval=2)

    result = GarminDBReader(db_path=str(db_path)).get_split_form_anomalies(activity_id)

    assert [row["split_index"] for row in result["splits"]] == [2]
    flagged = result["splits"][0]
    assert flagged["anomalies"] >= 1
    assert flagged["material"] >= 1
    assert flagged["metrics"] == ["gct"]


@pytest.mark.unit
def test_get_split_form_anomalies_no_raw(tmp_path: Path) -> None:
    """An activity whose raw details were never fetched maps to nothing."""
    activity_id = 9500000002
    db_path = _build_db(tmp_path, activity_id, [(1, 0, 300), (2, 301, 600)])

    result = GarminDBReader(db_path=str(db_path)).get_split_form_anomalies(activity_id)

    assert result == {
        "activity_id": activity_id,
        "total": 0,
        "material": 0,
        "splits": [],
    }


@pytest.mark.unit
def test_get_split_form_anomalies_no_splits(tmp_path: Path) -> None:
    """Without split rows there is nothing to map onto, even with raw details."""
    activity_id = 9500000003
    db_path = _build_db(tmp_path, activity_id, [])
    _write_activity_details(tmp_path, activity_id)

    result = GarminDBReader(db_path=str(db_path)).get_split_form_anomalies(activity_id)

    assert result == {
        "activity_id": activity_id,
        "total": 0,
        "material": 0,
        "splits": [],
    }
