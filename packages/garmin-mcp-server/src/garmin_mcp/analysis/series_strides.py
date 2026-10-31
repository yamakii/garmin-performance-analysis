"""Strides read off the time series, not the laps (#1494, no I/O).

Ingest finds strides only from lap structure: a watch workout's repeat step
(``stride_roles``) or a prescription whose strides block the laps align to.
A free run with manual laps carries neither, so four 20 s pickups after the
jog disappear into one long "main" lap -- the first one can even sit inside a
0.3 km lap that also holds a minute of jogging.

This module looks at the samples instead. A stride is a burst -- the same
per-sample rule ``hr_windows`` uses to keep pickups out of the HR ceiling
(stride cadence, or well above the previous two minutes of pace) -- that

- lasts ``STRIDE_MIN_S`` to ``STRIDE_MAX_S`` once flagged stretches separated
  by at most ``GAP_MERGE_S`` are joined (a GPS speed dip mid-stride while the
  cadence holds is still one stride);
- reaches ``MIN_SPEED_RATIO`` x the run's median running speed, and is cut to
  its samples at stride cadence (the slow-down into the jog is not the
  stride);
- has a neighbour within ``MAX_GAP_S``: strides come as a set, a lone pickup
  is a surge and stays one.

Samples are ``time_series_metrics`` mappings (``timestamp_s``, ``speed`` in
m/s, ``cadence`` in spm, optionally ``heart_rate`` and ``power``) ordered by
``timestamp_s``. Missing values never raise.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import median
from typing import Any

from garmin_mcp.analysis.hr_windows import (
    BURST_CADENCE_SPM,
    STOP_SPEED_MPS,
    burst_flags,
)

STRIDE_MIN_S = 8.0
STRIDE_MAX_S = 45.0
GAP_MERGE_S = 3.0
MAX_GAP_S = 180.0
MIN_REPS = 2
MIN_SPEED_RATIO = 1.25


@dataclass(frozen=True)
class StrideRep:
    """One stride: ``[t_from_s, t_to_s)`` in the ``timestamp_s`` domain."""

    t_from_s: float
    t_to_s: float
    duration_s: float
    peak_pace_s_per_km: float
    avg_pace_s_per_km: float
    peak_cadence: float | None
    peak_power: float | None
    max_hr: float | None
    recovery_after_s: float | None


def detect_series_strides(samples: Sequence[Mapping[str, Any]]) -> list[StrideRep]:
    """Every stride of one run, in run order (``[]`` when there is no set)."""
    if not samples:
        return []
    running = [
        speed
        for sample in samples
        if (speed := _num(sample.get("speed"))) is not None and speed > STOP_SPEED_MPS
    ]
    if not running:
        return []
    floor = MIN_SPEED_RATIO * median(running)

    reps = [
        rep
        for span in _merged_spans(samples, burst_flags(samples))
        if (bounds := _trim(samples, span, floor)) is not None
        and STRIDE_MIN_S <= bounds[1] - bounds[0] <= STRIDE_MAX_S
        and (rep := _rep(samples, bounds, span, floor)) is not None
    ]
    return _in_sets(reps)


def _trim(
    samples: Sequence[Mapping[str, Any]], span: tuple[float, float], floor: float
) -> tuple[float, float] | None:
    """The span cut to the stride itself, ``None`` when it never got fast.

    The burst rule keeps flagging the slow-down after a stride (the two-minute
    speed reference is still low), so a span runs on into the jog. The stride
    is the first..last sample at stride cadence: GPS speed lags the legs by
    several seconds at both ends, the cadence does not. Without cadence the
    samples at stride speed (``>= floor``) bound it instead. Dips *inside* the
    stride are kept. A span with no sample at stride speed is not a stride.
    """
    inside = [s for s in samples if span[0] <= float(s["timestamp_s"]) < span[1]]
    fast = [
        float(s["timestamp_s"])
        for s in inside
        if (speed := _num(s.get("speed"))) is not None and speed >= floor
    ]
    if not fast:
        return None
    legs = [
        float(s["timestamp_s"])
        for s in inside
        if (cadence := _num(s.get("cadence"))) is not None
        and cadence >= BURST_CADENCE_SPM
    ]
    bounds = legs or fast
    return bounds[0], bounds[-1] + 1.0


def _merged_spans(
    samples: Sequence[Mapping[str, Any]], flags: Sequence[bool]
) -> list[tuple[float, float]]:
    """Flagged stretches as ``(start, end)``, gaps up to ``GAP_MERGE_S`` joined."""
    spans: list[tuple[float, float]] = []
    start: float | None = None
    last: float | None = None
    for sample, flagged in zip(samples, flags, strict=True):
        t = float(sample["timestamp_s"])
        if not flagged:
            continue
        if start is None or last is None or t - last > GAP_MERGE_S + 1.0:
            if start is not None and last is not None:
                spans.append((start, last + 1.0))
            start = t
        last = t
    if start is not None and last is not None:
        spans.append((start, last + 1.0))
    return spans


def _rep(
    samples: Sequence[Mapping[str, Any]],
    bounds: tuple[float, float],
    span: tuple[float, float],
    floor: float,
) -> StrideRep | None:
    """The stride's figures, ``None`` without speed.

    Cadence, power and HR are read inside ``bounds``. The paces are read off
    the span's samples at stride speed: GPS speed trails the legs, so inside
    ``bounds`` its first seconds are still the jog's.
    """
    start, end = bounds
    inside = [s for s in samples if start <= float(s["timestamp_s"]) < end]
    speeds = [
        v
        for s in samples
        if span[0] <= float(s["timestamp_s"]) < span[1]
        and (v := _num(s.get("speed"))) is not None
        and v >= floor
    ]
    if not speeds:
        return None
    return StrideRep(
        t_from_s=start,
        t_to_s=end,
        duration_s=end - start,
        peak_pace_s_per_km=round(1000.0 / max(speeds), 1),
        avg_pace_s_per_km=round(1000.0 * len(speeds) / sum(speeds), 1),
        peak_cadence=_peak(inside, "cadence"),
        peak_power=_peak(inside, "power"),
        max_hr=_peak(inside, "heart_rate"),
        recovery_after_s=None,
    )


def _in_sets(reps: Sequence[StrideRep]) -> list[StrideRep]:
    """Reps that belong to a set of ``MIN_REPS``+, with the jog after each."""
    groups: list[list[StrideRep]] = []
    for rep in reps:
        if groups and rep.t_from_s - groups[-1][-1].t_to_s <= MAX_GAP_S:
            groups[-1].append(rep)
        else:
            groups.append([rep])
    out: list[StrideRep] = []
    for group in groups:
        if len(group) < MIN_REPS:
            continue
        for rep, following in zip(group, [*group[1:], None], strict=True):
            recovery = None if following is None else following.t_from_s - rep.t_to_s
            out.append(StrideRep(**{**rep.__dict__, "recovery_after_s": recovery}))
    return out


def _peak(samples: Sequence[Mapping[str, Any]], key: str) -> float | None:
    values = [v for s in samples if (v := _num(s.get(key))) is not None]
    return max(values) if values else None


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
