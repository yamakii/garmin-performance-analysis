"""Which seconds of a run the HR ceiling may judge: steady running only (no I/O).

An easy-run ceiling guards *steady* easy running. Heart rate lags every change
of load, so a second right after a stop, a surge or a stride says more about
that event than about the running around it: a 20 s pickup to 165 bpm keeps HR
above 150 for most of a minute after the pace has come back down, and the
first minute after an auto-pause resumes is run on a heart that has not caught
up yet (#1313). Judging the ceiling on those seconds turns the run's shape into
a verdict on its effort.

This module finds the load-change **events** of one run and, after each one,
the moment its heart rate has **recovered**, read off the HR trace itself
rather than a fixed window -- recovery scales with the event's size, from a
few seconds after a small pickup to a minute or more after a pause:

========================  ====================================================
event                     detected from
========================  ====================================================
``stop``                  speed <= ``STOP_SPEED_MPS`` for >= ``STOP_MIN_S``,
                          or ``sum_moving_duration`` not advancing
``pause_resume``          ``Δsum_elapsed_duration - Δsum_duration > 1``
``burst``                 cadence >= ``BURST_CADENCE_SPM`` or speed >=
                          ``BURST_SPEED_RATIO`` x the previous 120 s median,
                          for >= ``BURST_MIN_S``
``effort_lap_end``        a stride / recovery / interval / rep lap
========================  ====================================================

The recovery ends at the first of: HR back within ``HR_RECOVERY_TOL_BPM`` of
the pre-event baseline for ``HR_RECOVERY_HOLD_S``; a plateau of
``HR_PLATEAU_S`` within ``HR_PLATEAU_BAND_BPM`` away from the baseline, when
speed moved the same way as HR (a new operating point HR will not leave);
``HR_RECOVERY_CAP_S`` after the event; the next event's start.

A plateau alone is not a new operating point. After a stride the athlete jogs
*slower* than before while HR sits above the baseline for a while on its way
down; that is the recovery itself, and ending it there would hand the
ceiling every post-stride second (#1320). Only a plateau held at a speed
``PLATEAU_SPEED_SHIFT`` beyond the pre-event speed in the same direction as
HR -- faster and higher, or slower and lower -- is running at a new level.

Samples are plain mappings with ``timestamp_s`` and optionally
``heart_rate``, ``speed`` (m/s), ``cadence`` (spm, both feet),
``sum_moving_duration``, ``sum_elapsed_duration`` and ``sum_duration`` -- the
``time_series_metrics`` columns -- ordered by ``timestamp_s``. Splits carry
``role_phase`` / ``intensity_type`` and ``start_s`` / ``end_s`` in the same
time domain. Missing values never raise: a run without speed simply has no
stops or bursts to find.
"""

from __future__ import annotations

import bisect
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import median
from typing import Any, Literal

# --- Recovery ------------------------------------------------------------------
HR_RECOVERY_TOL_BPM = 3
HR_RECOVERY_HOLD_S = 10
HR_PLATEAU_S = 20
HR_PLATEAU_BAND_BPM = 2
HR_RECOVERY_CAP_S = 180
# A plateau ends the recovery only at a speed this far (as a fraction of the
# pre-event speed) from where the athlete ran before, in HR's direction.
PLATEAU_SPEED_SHIFT = 0.05

# The pre-event baseline: median HR from 60 s to 5 s before the event starts
# (the last 5 s are already part of the change).
BASELINE_FROM_S = 60
BASELINE_TO_S = 5

# --- Events --------------------------------------------------------------------
STOP_SPEED_MPS = 0.5
STOP_MIN_S = 3
BURST_CADENCE_SPM = 195
BURST_SPEED_RATIO = 1.3
BURST_MIN_S = 5
BURST_LOOKBACK_S = 120
# A speed median over fewer samples than this is no reference: the first
# seconds of a run would otherwise flag the athlete getting up to pace.
BURST_MIN_REFERENCE_SAMPLES = 30
# ``Δsum_elapsed_duration - Δsum_duration`` above this is a pause.
PAUSE_GAP_S = 1.0

# Laps whose load is *meant* to differ from the steady running around them.
EFFORT_ROLES: frozenset[str] = frozenset({"stride", "recovery", "interval", "rep"})
# ``intensity_type`` -> effort role, consulted only when ``role_phase`` is null.
_EFFORT_INTENSITIES: dict[str, str] = {"RECOVERY": "recovery", "REST": "recovery"}

# Longest gap between two samples still counted as time at the earlier
# sample's value. The watch records roughly every second; a longer gap is a
# pause, and a paused minute must not count as a minute above the ceiling.
MAX_SAMPLE_GAP_S = 10.0

EventKind = Literal["stop", "pause_resume", "burst", "effort_lap_end"]


@dataclass(frozen=True)
class Event:
    """One load change: ``[start_s, end_s)`` in the ``timestamp_s`` domain."""

    kind: EventKind
    start_s: float
    end_s: float


# --------------------------------------------------------------------------- #
# Events
# --------------------------------------------------------------------------- #


def detect_events(
    samples: Sequence[Mapping[str, Any]], splits: Sequence[Mapping[str, Any]]
) -> list[Event]:
    """Every load-change event of one run, ordered by start.

    Args:
        samples: The run's time series (see the module docstring).
        splits: The run's laps with ``role_phase`` and ``start_s`` / ``end_s``.

    Returns:
        Events sorted by ``start_s``. Events may overlap (a stop inside a
        recovery lap); :func:`steady_mask` merges them.
    """
    events: list[Event] = []
    events.extend(_flag_runs(samples, _stop_flags(samples), STOP_MIN_S, "stop"))
    events.extend(_pause_events(samples))
    events.extend(_flag_runs(samples, _burst_flags(samples), BURST_MIN_S, "burst"))
    events.extend(_effort_laps(splits))
    events.sort(key=lambda event: (event.start_s, event.end_s))
    return events


def _stop_flags(samples: Sequence[Mapping[str, Any]]) -> list[bool]:
    """Per sample: standing still, by speed or by a moving clock that stood."""
    flags: list[bool] = []
    previous_moving: float | None = None
    for sample in samples:
        speed = _num(sample.get("speed"))
        moving = _num(sample.get("sum_moving_duration"))
        stopped = speed is not None and speed <= STOP_SPEED_MPS
        if moving is not None and previous_moving is not None:
            stopped = stopped or moving - previous_moving <= 1e-9
        if moving is not None:
            previous_moving = moving
        flags.append(stopped)
    return flags


def _burst_flags(samples: Sequence[Mapping[str, Any]]) -> list[bool]:
    """Per sample: stride cadence, or well above the previous 120 s of pace."""
    flags: list[bool] = []
    window: deque[tuple[float, float]] = deque()
    ordered: list[float] = []
    for sample in samples:
        t = _time(sample)
        while window and window[0][0] < t - BURST_LOOKBACK_S:
            _, old = window.popleft()
            del ordered[bisect.bisect_left(ordered, old)]

        cadence = _num(sample.get("cadence"))
        speed = _num(sample.get("speed"))
        fast = cadence is not None and cadence >= BURST_CADENCE_SPM
        if speed is not None and len(ordered) >= BURST_MIN_REFERENCE_SAMPLES:
            reference = _sorted_median(ordered)
            if reference > STOP_SPEED_MPS and speed >= BURST_SPEED_RATIO * reference:
                fast = True
        flags.append(fast)

        if speed is not None:
            window.append((t, speed))
            bisect.insort(ordered, speed)
    return flags


def _pause_events(samples: Sequence[Mapping[str, Any]]) -> list[Event]:
    """A resume after auto-pause: elapsed time ran on while the timer stood."""
    events: list[Event] = []
    for previous, current in zip(samples, samples[1:], strict=False):
        elapsed = _delta(previous, current, "sum_elapsed_duration")
        timed = _delta(previous, current, "sum_duration")
        if elapsed is None or timed is None:
            continue
        if elapsed - timed > PAUSE_GAP_S:
            events.append(Event("pause_resume", _time(previous), _time(current)))
    return events


def _effort_laps(splits: Sequence[Mapping[str, Any]]) -> list[Event]:
    """Stride / recovery / interval / rep laps with recorded timing."""
    events: list[Event] = []
    for split in splits:
        if _effort_role(split) is None:
            continue
        start = _num(split.get("start_s"))
        end = _num(split.get("end_s"))
        if start is None or end is None or end <= start:
            continue
        events.append(Event("effort_lap_end", start, end))
    return events


def _effort_role(split: Mapping[str, Any]) -> str | None:
    """The lap's effort role, or ``None`` for steady running."""
    role = str(split.get("role_phase") or "").strip().lower()
    if role:
        return role if role in EFFORT_ROLES else None
    intensity = str(split.get("intensity_type") or "").strip().upper()
    return _EFFORT_INTENSITIES.get(intensity)


def _flag_runs(
    samples: Sequence[Mapping[str, Any]],
    flags: Sequence[bool],
    min_s: float,
    kind: EventKind,
) -> list[Event]:
    """Maximal runs of flagged samples lasting at least ``min_s``.

    A run ends where the first unflagged sample starts, so a 10-sample stop
    recorded at 1 Hz lasts 10 s.
    """
    events: list[Event] = []
    start_index: int | None = None
    for index, flagged in enumerate([*flags, False]):
        if flagged and start_index is None:
            start_index = index
        elif not flagged and start_index is not None:
            start = _time(samples[start_index])
            end = (
                _time(samples[index])
                if index < len(samples)
                else _time(samples[index - 1]) + 1.0
            )
            if end - start >= min_s:
                events.append(Event(kind, start, end))
            start_index = None
    return events


# --------------------------------------------------------------------------- #
# Recovery
# --------------------------------------------------------------------------- #


def recovery_end(
    samples: Sequence[Mapping[str, Any]],
    event: Event,
    next_event_start: float | None,
    *,
    baselines: tuple[float | None, float | None] | None = None,
) -> float:
    """When heart rate has absorbed ``event``, read off the HR trace.

    Args:
        samples: The run's time series.
        event: The load change to recover from.
        next_event_start: Where the next event starts (its own window takes
            over there), or ``None`` for the last event.
        baselines: ``(hr, speed)`` to recover to, when the caller knows them
            better than the 60 s before this event -- see
            :func:`event_baselines`. ``None`` reads them before the event.

    Returns:
        The first of: the start of a ``HR_RECOVERY_HOLD_S`` hold within
        ``HR_RECOVERY_TOL_BPM`` of the baseline; the start of a
        ``HR_PLATEAU_S`` plateau within ``HR_PLATEAU_BAND_BPM`` that sits away
        from the baseline; ``event.end_s + HR_RECOVERY_CAP_S``;
        ``next_event_start``. Never earlier than ``event.end_s``.
    """
    limit = event.end_s + HR_RECOVERY_CAP_S
    if next_event_start is not None:
        limit = min(limit, next_event_start)
    if limit <= event.end_s:
        return event.end_s

    series = _hr_series(samples)
    speeds = _speed_series(samples)
    if baselines is None:
        baseline = _baseline(series, event.start_s)
        baseline_speed = _baseline(speeds, event.start_s)
    else:
        baseline, baseline_speed = baselines
    after = [(t, hr) for t, hr in series if t >= event.end_s]

    for index, (t, _hr) in enumerate(after):
        if t >= limit:
            break
        if baseline is not None and _holds_near(
            after, index, baseline, HR_RECOVERY_TOL_BPM, HR_RECOVERY_HOLD_S
        ):
            return t
        if _is_new_level(after, index, baseline, speeds, baseline_speed):
            return t
    return limit


def _baseline(
    series: Sequence[tuple[float, float]], event_start: float
) -> float | None:
    """Median value (HR or speed) from ``BASELINE_FROM_S`` to ``BASELINE_TO_S``
    before the event."""
    values = [
        hr
        for t, hr in series
        if event_start - BASELINE_FROM_S <= t <= event_start - BASELINE_TO_S
    ]
    return float(median(values)) if values else None


def _window(
    series: Sequence[tuple[float, float]], index: int, span: float
) -> list[float] | None:
    """HR values of ``[t_index, t_index + span)``, or ``None`` if not observed.

    The window counts as observed when the trace continues past it or its last
    sample is within a second of its end -- a hold cannot be claimed on data
    the run never recorded.
    """
    start = series[index][0]
    values: list[float] = []
    last_t = start
    for t, hr in series[index:]:
        if t >= start + span:
            return values
        values.append(hr)
        last_t = t
    return values if last_t >= start + span - 1.0 else None


def _holds_near(
    series: Sequence[tuple[float, float]],
    index: int,
    centre: float,
    tolerance: float,
    span: float,
) -> bool:
    """Whether HR stays within ``centre ± tolerance`` for ``span`` seconds."""
    values = _window(series, index, span)
    if not values:
        return False
    return all(abs(hr - centre) <= tolerance for hr in values)


def _is_new_level(
    series: Sequence[tuple[float, float]],
    index: int,
    baseline: float | None,
    speeds: Sequence[tuple[float, float]],
    baseline_speed: float | None,
) -> bool:
    """A new operating point: HR flat away from the baseline, speed moved too.

    ``HR_PLATEAU_S`` of HR within ``HR_PLATEAU_BAND_BPM``, away from the
    baseline, is only half of it: HR also sits flat and high on a slow jog
    while it is still coming down from a stride. The plateau counts only when
    the speed over the same window moved ``PLATEAU_SPEED_SHIFT`` from the
    pre-event speed in HR's direction. Without a baseline or speed to compare
    against the plateau cannot be told from a recovery, so it does not count --
    the hold rule, the cap or the next event ends the recovery instead.
    A flat stretch *at* the baseline is the return itself (the hold rule).
    """
    if baseline is None or baseline_speed is None or baseline_speed <= 0:
        return False
    values = _window(series, index, HR_PLATEAU_S)
    if not values or max(values) - min(values) > 2 * HR_PLATEAU_BAND_BPM:
        return False
    shift = float(median(values)) - baseline
    if abs(shift) <= HR_RECOVERY_TOL_BPM:
        return False
    start = series[index][0]
    window_speeds = [speed for t, speed in speeds if start <= t < start + HR_PLATEAU_S]
    if not window_speeds:
        return False
    ratio = float(median(window_speeds)) / baseline_speed
    if shift > 0:
        return ratio >= 1.0 + PLATEAU_SPEED_SHIFT
    return ratio <= 1.0 - PLATEAU_SPEED_SHIFT


# --------------------------------------------------------------------------- #
# Masks and what is read through them
# --------------------------------------------------------------------------- #


def steady_mask(
    samples: Sequence[Mapping[str, Any]], splits: Sequence[Mapping[str, Any]]
) -> list[bool]:
    """``True`` for every sample outside an event and its HR recovery.

    Overlapping or touching events are merged first, so a stop inside a
    recovery lap is one excursion with one recovery.
    """
    spans = _merge(detect_events(samples, splits))
    intervals: list[tuple[float, float]] = []
    for span, baselines in zip(spans, event_baselines(samples, spans), strict=True):
        index = len(intervals)
        next_start = spans[index + 1].start_s if index + 1 < len(spans) else None
        end = recovery_end(samples, span, next_start, baselines=baselines)
        intervals.append((span.start_s, end))
    return _outside(samples, intervals)


def event_baselines(
    samples: Sequence[Mapping[str, Any]], spans: Sequence[Event]
) -> list[tuple[float | None, float | None]]:
    """The ``(hr, speed)`` each merged event has to recover to.

    Normally the 60 s before the event. But when an event starts before the
    previous one's recovery has ended -- the second of a set of strides, a
    stop in the middle of the jog back -- those 60 s are that recovery, not
    steady running: HR still 153 after a stride would make 156 after the next
    one look "recovered" at once (#1320). Such an event inherits the previous
    event's baseline, so a chain of events recovers to the steady running
    before its first one.
    """
    series = _hr_series(samples)
    speeds = _speed_series(samples)
    result: list[tuple[float | None, float | None]] = []
    for index, span in enumerate(spans):
        own = (_baseline(series, span.start_s), _baseline(speeds, span.start_s))
        if index == 0:
            result.append(own)
            continue
        previous = spans[index - 1]
        inherited = result[-1]
        # Recovery of the previous event, cut by this one if it had not ended.
        previous_end = recovery_end(
            samples, previous, span.start_s, baselines=inherited
        )
        result.append(inherited if previous_end >= span.start_s else own)
    return result


def event_mask(
    samples: Sequence[Mapping[str, Any]], splits: Sequence[Mapping[str, Any]]
) -> list[bool]:
    """``True`` for every sample outside an event (no HR recovery added).

    Form metrics have no lag: a stride's ground contact is over when the
    stride is, so the form judged share masks the events alone.
    """
    spans = _merge(detect_events(samples, splits))
    return _outside(samples, [(span.start_s, span.end_s) for span in spans])


def seconds_over(
    samples: Sequence[Mapping[str, Any]], mask: Sequence[bool], ceiling: int
) -> dict[str, float] | None:
    """Seconds (and share of judged time) with HR above ``ceiling``.

    Only samples the mask keeps are counted; each stands for the time until
    the next sample (capped at ``MAX_SAMPLE_GAP_S``).

    Returns:
        ``{"seconds_over", "pct_over"}``, or ``None`` when no judged sample
        carries a heart rate (the caller falls back to the zone totals).
    """
    total = 0.0
    over = 0.0
    for sample, weight, keep in zip(samples, _weights(samples), mask, strict=False):
        hr = _num(sample.get("heart_rate"))
        if not keep or hr is None:
            continue
        total += weight
        if hr > ceiling:
            over += weight
    if total <= 0:
        return None
    return {
        "seconds_over": round(over, 1),
        "pct_over": round(over / total * 100.0, 1),
    }


def seconds_in_band(
    samples: Sequence[Mapping[str, Any]], mask: Sequence[bool], low: int, high: int
) -> dict[str, float] | None:
    """Seconds (and shares) with HR inside, above and below ``[low, high]``.

    Only samples the mask keeps are counted, each weighted like
    :func:`seconds_over`. Both bounds are inclusive.

    Returns:
        ``{"seconds_in", "seconds_above", "seconds_below", "pct_in",
        "pct_above"}`` (shares in percent of the judged time), or ``None``
        when no judged sample carries a heart rate.
    """
    inside = above = below = 0.0
    for sample, weight, keep in zip(samples, _weights(samples), mask, strict=False):
        hr = _num(sample.get("heart_rate"))
        if not keep or hr is None:
            continue
        if hr > high:
            above += weight
        elif hr < low:
            below += weight
        else:
            inside += weight
    total = inside + above + below
    if total <= 0:
        return None
    return {
        "seconds_in": round(inside, 1),
        "seconds_above": round(above, 1),
        "seconds_below": round(below, 1),
        "pct_in": round(inside / total * 100.0, 1),
        "pct_above": round(above / total * 100.0, 1),
    }


def seconds_over_varying(
    samples: Sequence[Mapping[str, Any]],
    mask: Sequence[bool],
    ceilings: Sequence[int | None],
) -> dict[str, float] | None:
    """Like :func:`seconds_over`, with each sample judged on its own ceiling.

    A prescription whose steps carry different ceilings (a long run with a
    marathon-pace block allowed higher) judges every second against the
    ceiling of the step it was run in. A sample whose ceiling is ``None`` is
    not judged.

    Returns:
        ``{"seconds_over", "pct_over"}``, or ``None`` when no judged sample
        with a ceiling carries a heart rate.
    """
    total = 0.0
    over = 0.0
    for sample, weight, keep, ceiling in zip(
        samples, _weights(samples), mask, ceilings, strict=False
    ):
        hr = _num(sample.get("heart_rate"))
        if not keep or hr is None or ceiling is None:
            continue
        total += weight
        if hr > ceiling:
            over += weight
    if total <= 0:
        return None
    return {
        "seconds_over": round(over, 1),
        "pct_over": round(over / total * 100.0, 1),
    }


def judged_share(
    samples: Sequence[Mapping[str, Any]], mask: Sequence[bool]
) -> float | None:
    """Share of the run's time the mask keeps (``None`` without samples)."""
    weights = _weights(samples)
    total = sum(weights)
    if total <= 0:
        return None
    kept = sum(weight for weight, keep in zip(weights, mask, strict=False) if keep)
    return round(kept / total, 3)


def masked_mean_hr(
    samples: Sequence[Mapping[str, Any]], mask: Sequence[bool]
) -> float | None:
    """Time-weighted mean HR of the samples the mask keeps, or ``None``."""
    total = 0.0
    weighted = 0.0
    for sample, weight, keep in zip(samples, _weights(samples), mask, strict=False):
        hr = _num(sample.get("heart_rate"))
        if not keep or hr is None:
            continue
        total += weight
        weighted += hr * weight
    if total <= 0:
        return None
    return round(weighted / total, 1)


def masked_split_hr(
    samples: Sequence[Mapping[str, Any]],
    mask: Sequence[bool],
    splits: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Copies of ``splits`` whose ``avg_hr`` / ``max_hr`` read steady seconds only.

    A kilometre's average HR mixes whatever happened in it: a stride and the
    jog HR still coming down from it lift a 144 bpm kilometre to 151, and a
    ceiling touch detected on that average would be the stride again (#1320).
    Each split is re-read over the samples the mask keeps inside its
    ``[start_s, end_s)``: ``avg_hr`` time-weighted, ``max_hr`` the peak. A split
    with no kept sample gets ``None`` for both (nothing steady to judge); a
    split without timing is copied unchanged.
    """
    weights = _weights(samples)
    kept = [
        (_time(sample), hr, weight)
        for sample, weight, keep in zip(samples, weights, mask, strict=False)
        if keep and (hr := _num(sample.get("heart_rate"))) is not None
    ]
    times = [t for t, _hr, _w in kept]

    result: list[dict[str, Any]] = []
    for split in splits:
        start = _num(split.get("start_s"))
        end = _num(split.get("end_s"))
        copy = dict(split)
        if start is None or end is None:
            result.append(copy)
            continue
        inside = kept[bisect.bisect_left(times, start) : bisect.bisect_left(times, end)]
        total = sum(weight for _t, _hr, weight in inside)
        if total <= 0:
            copy["avg_hr"] = None
            copy["max_hr"] = None
        else:
            copy["avg_hr"] = round(
                sum(hr * weight for _t, hr, weight in inside) / total, 1
            )
            copy["max_hr"] = max(hr for _t, hr, _w in inside)
        result.append(copy)
    return result


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _merge(events: Sequence[Event]) -> list[Event]:
    """Overlapping or touching events as one span (the first one's kind)."""
    merged: list[Event] = []
    for event in sorted(events, key=lambda e: (e.start_s, e.end_s)):
        if merged and event.start_s <= merged[-1].end_s:
            last = merged[-1]
            merged[-1] = Event(last.kind, last.start_s, max(last.end_s, event.end_s))
        else:
            merged.append(event)
    return merged


def _outside(
    samples: Sequence[Mapping[str, Any]], intervals: Sequence[tuple[float, float]]
) -> list[bool]:
    """Per sample: not inside any ``[start, end)`` of ``intervals``.

    The intervals are merged first, so one forward sweep over the (ordered)
    samples decides every sample against at most one interval.
    """
    ordered: list[tuple[float, float]] = []
    for start, end in sorted(intervals):
        if ordered and start <= ordered[-1][1]:
            ordered[-1] = (ordered[-1][0], max(ordered[-1][1], end))
        else:
            ordered.append((start, end))

    mask: list[bool] = []
    cursor = 0
    for sample in samples:
        t = _time(sample)
        while cursor < len(ordered) and ordered[cursor][1] <= t:
            cursor += 1
        inside = cursor < len(ordered) and ordered[cursor][0] <= t
        mask.append(not inside)
    return mask


def _weights(samples: Sequence[Mapping[str, Any]]) -> list[float]:
    """Seconds each sample stands for: until the next one, capped; last = 1 s."""
    weights: list[float] = []
    for index, sample in enumerate(samples):
        if index + 1 < len(samples):
            gap = _time(samples[index + 1]) - _time(sample)
            weights.append(min(max(gap, 0.0), MAX_SAMPLE_GAP_S))
        else:
            weights.append(1.0)
    return weights


def _hr_series(samples: Sequence[Mapping[str, Any]]) -> list[tuple[float, float]]:
    """``(t, hr)`` of every sample that carries a heart rate."""
    return [
        (_time(sample), hr)
        for sample in samples
        if (hr := _num(sample.get("heart_rate"))) is not None
    ]


def _speed_series(
    samples: Sequence[Mapping[str, Any]],
) -> list[tuple[float, float]]:
    """``(t, speed)`` of every moving sample (a stop says nothing of pace)."""
    return [
        (_time(sample), speed)
        for sample in samples
        if (speed := _num(sample.get("speed"))) is not None and speed > STOP_SPEED_MPS
    ]


def _delta(
    previous: Mapping[str, Any], current: Mapping[str, Any], key: str
) -> float | None:
    """``current[key] - previous[key]``, or ``None`` when either is missing."""
    before = _num(previous.get(key))
    after = _num(current.get(key))
    if before is None or after is None:
        return None
    return after - before


def _sorted_median(ordered: Sequence[float]) -> float:
    """Median of an already sorted, non-empty sequence."""
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _time(sample: Mapping[str, Any]) -> float:
    """The sample's ``timestamp_s`` as a float."""
    return float(sample["timestamp_s"])


def _num(value: Any) -> float | None:
    """A plain ``float`` or ``None`` (DuckDB / numpy scalars tolerated)."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
