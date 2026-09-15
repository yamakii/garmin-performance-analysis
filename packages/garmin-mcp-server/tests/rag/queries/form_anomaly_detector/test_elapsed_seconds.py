"""FormAnomalyDetector: anomaly timestamps are elapsed seconds, not indices (#1137).

Garmin stores long activities at one sample every 2 seconds, so the index of a
sample in ``activityDetailMetrics`` is half its elapsed second. These tests pin
the reported ``timestamp``, the sustained-run gate and the ``time_range`` filter
to seconds for both 1 Hz and 2 s-sampled raw data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from garmin_mcp.rag.queries.form_anomaly_detector import FormAnomalyDetector

_SERIES_LEN = 300
_SPIKE_INDICES = (200, 201, 202, 203, 204)
_BASELINE_GCT = 240.0
_SPIKE_GCT = 290.0

_BASE_DESCRIPTORS: list[dict[str, Any]] = [
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
        "key": "directElevation",
        "unit": {"id": 300, "key": "m", "factor": 1.0},
    },
]

_DURATION_DESCRIPTOR: dict[str, Any] = {
    "metricsIndex": 4,
    "key": "sumDuration",
    "unit": {"id": 40, "key": "second", "factor": 1000.0},
}


def _write_details(
    base_path: Path, activity_id: int, sample_interval: int | None
) -> None:
    """Write raw details with a GCT spike at ``_SPIKE_INDICES``.

    Args:
        base_path: Detector base path (raw files live under ``raw/activity``).
        activity_id: Activity ID the file is written for.
        sample_interval: Seconds per sample recorded in ``sumDuration``; None
            writes no duration descriptor at all (legacy 1 Hz assumption).
    """
    descriptors = list(_BASE_DESCRIPTORS)
    if sample_interval is not None:
        descriptors = [*descriptors, _DURATION_DESCRIPTOR]

    rows = []
    for index in range(_SERIES_LEN):
        gct = _SPIKE_GCT if index in _SPIKE_INDICES else _BASELINE_GCT
        values: list[float] = [140.0, 28.0, gct, 10.0]
        if sample_interval is not None:
            values.append(float(index * sample_interval))
        rows.append({"metrics": values})

    activity_dir = base_path / "raw" / "activity" / str(activity_id)
    activity_dir.mkdir(parents=True, exist_ok=True)
    (activity_dir / "activity_details.json").write_text(
        json.dumps(
            {
                "activityId": activity_id,
                "measurementCount": len(rows),
                "metricDescriptors": descriptors,
                "activityDetailMetrics": rows,
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.unit
def test_anomaly_timestamp_uses_elapsed_seconds(tmp_path: Path) -> None:
    """A spike at sample 200 reports 400 s at 2 s sampling, 200 s at 1 Hz."""
    detector = FormAnomalyDetector(base_path=tmp_path)

    _write_details(tmp_path, 9600000001, sample_interval=2)
    downsampled = detector.get_form_anomaly_details(9600000001)
    timestamps = sorted(a["timestamp"] for a in downsampled["anomalies"])

    assert timestamps, "the GCT spike must still be detected at 2 s sampling"
    assert 398 <= timestamps[0] <= 406
    assert timestamps[0] == 400
    assert timestamps == [400, 402, 404, 406, 408]

    _write_details(tmp_path, 9600000002, sample_interval=None)
    one_hz = detector.get_form_anomaly_details(9600000002)
    one_hz_timestamps = sorted(a["timestamp"] for a in one_hz["anomalies"])

    assert one_hz_timestamps == [200, 201, 202, 203, 204]


@pytest.mark.unit
def test_sustained_filter_uses_seconds() -> None:
    """The >= 5 s gate counts seconds covered, not flagged samples (#1137)."""
    detector = FormAnomalyDetector(base_path=Path("/nonexistent"))

    def _run(timestamps: tuple[int, ...]) -> list[dict[str, Any]]:
        return [
            {
                "timestamp": ts,
                "index": ts // 2,
                "metric": "directGroundContactTime",
                "value": 300.0,
                "baseline": 260.0,
                "z_score": 4.0,
            }
            for ts in timestamps
        ]

    # Two 2 s-sampled flags cover 4 s: below the 5 s gate.
    assert detector._filter_sustained(_run((400, 402)), sample_interval=2.0) == []

    # Three cover 6 s and survive -- index arithmetic would have counted 3 s.
    kept = detector._filter_sustained(_run((400, 402, 404)), sample_interval=2.0)
    assert [a["timestamp"] for a in kept] == [400, 402, 404]

    # 1 Hz behaviour is unchanged: 5 flagged seconds pass, 4 do not.
    one_hz = [dict(a, index=a["timestamp"]) for a in _run((400, 401, 402, 403, 404))]
    assert len(detector._filter_sustained(one_hz)) == 5
    assert detector._filter_sustained(one_hz[:4]) == []


@pytest.mark.unit
def test_time_range_filter_in_seconds(tmp_path: Path) -> None:
    """``time_range`` selects by elapsed seconds on a 2 s-sampled activity."""
    detector = FormAnomalyDetector(base_path=tmp_path)
    _write_details(tmp_path, 9600000003, sample_interval=2)

    in_seconds = detector.get_form_anomaly_details(
        9600000003, filters={"time_range": (390, 410)}
    )
    assert in_seconds["returned_anomalies"] >= 1
    assert 400 in [a["timestamp"] for a in in_seconds["anomalies"]]

    # The sample indices (200-204) are no longer what the filter compares.
    by_index = detector.get_form_anomaly_details(
        9600000003, filters={"time_range": (190, 210)}
    )
    assert by_index["returned_anomalies"] == 0
