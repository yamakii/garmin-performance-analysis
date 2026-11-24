"""``build_flow`` segments carry their elevation (#1627).

The run note walks the attribution order intensity -> terrain -> ...; without
per-segment elevation the terrain step could only use the whole-run total, so
on 11/7 the writer never saw that km 1 climbed 14 m at the fastest pace.
"""

from __future__ import annotations

from typing import Any

import pytest

from garmin_mcp.analysis.run_moments import build_flow


def _split(
    index: int,
    *,
    gain: float | None,
    loss: float | None,
    role: str | None = None,
    distance: float = 1.0,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "split_index": index,
        "distance_km": distance,
        "duration_s": 500.0 * distance,
        "pace_s_per_km": 500.0,
        "avg_hr": 135.0,
        "max_hr": 140.0,
        "role_phase": role,
    }
    if gain is not None:
        row["elevation_gain_m"] = gain
    if loss is not None:
        row["elevation_loss_m"] = loss
    return row


@pytest.mark.unit
def test_flow_long_step_per_split_elevation() -> None:
    flow = build_flow([_split(1, gain=14.0, loss=4.0), _split(2, gain=5.0, loss=6.0)])

    assert [s["elevation_gain_m"] for s in flow["segments"]] == [14.0, 5.0]
    assert [s["elevation_loss_m"] for s in flow["segments"]] == [4.0, 6.0]


@pytest.mark.unit
def test_flow_segment_sums_elevation() -> None:
    """A whole short step is one segment: its elevation is the sum of its laps."""
    flow = build_flow(
        [
            _split(1, gain=14.0, loss=4.0, role="warmup", distance=0.2),
            _split(2, gain=5.0, loss=6.0, role="warmup", distance=0.2),
            _split(3, gain=1.0, loss=1.0, role="run", distance=5.0),
        ]
    )

    warmup = flow["segments"][0]
    assert warmup["split_from"] == 1 and warmup["split_to"] == 2
    assert warmup["elevation_gain_m"] == 19.0
    assert warmup["elevation_loss_m"] == 10.0


@pytest.mark.unit
def test_flow_segment_elevation_none_when_unrecorded() -> None:
    flow = build_flow([_split(1, gain=None, loss=None)])

    assert flow["segments"][0]["elevation_gain_m"] is None
    assert flow["segments"][0]["elevation_loss_m"] is None
