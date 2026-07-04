"""Single source for *material form-anomaly event* semantics (pure, no I/O).

The "material form-anomaly event" concept was historically re-implemented in
three places -- the injury-risk factor, the web "今週の注意点" caution card, and
ad-hoc consumers -- each with its own constants and dedup logic (#809). Any fix
inevitably missed a consumer. This module is the *one* place that decides:

- whether a raw z-score spike counts as a **material, severe** anomaly
  (``is_material_severe``),
- how per-metric spikes collapse into deduped **events**
  (``count_material_events``),
- how many of those are **high-severity** (``count_high_severity``), and
- whether a run should **flag** given its event count, running hours and the
  athlete's personal baseline rate (``should_flag_run``).

Both the injury-risk signal and the caution card consume these functions via
``GarminDBReader`` so the web layer never re-derives the aggregation (enforced by
``garmin-web`` architecture-guard test).
"""

from __future__ import annotations

from typing import Any

# An anomaly counts toward the material-event rate only when it is *material*
# (``probable_cause`` other than ``"isolated"``) and severe (``|z| >
# _FORM_SEVERITY_MIN_Z``, matching the detector's medium/high strata). Adjacent
# material anomalies within ``_FORM_EVENT_DEDUP_WINDOW_S`` seconds collapse into
# a single event (one stop/transition, not 2-6 per-metric duplicates).
_FORM_SEVERITY_MIN_Z = 3.5
_FORM_EVENT_DEDUP_WINDOW_S = 2

# High-severity stratum threshold (matches the detector's ``z > 4.5`` high band).
_HIGH_SEVERITY_Z = 4.5

# Run-level flag rule (#809). A run lights up on the caution card only when it
# has at least ``FLAG_MIN_EVENTS`` deduped material events AND those events
# exceed ``FLAG_EXPECTED_MULTIPLIER`` times the count expected from the athlete's
# personal baseline event-rate over the run's duration. The fixed floor alone
# (>= 3) lit up on ordinary long runs whose baseline-expected count already
# reached 4-5; requiring the acute:baseline excess suppresses those.
FLAG_MIN_EVENTS = 3
FLAG_EXPECTED_MULTIPLIER = 2.0


def is_material_severe(anomaly: dict[str, Any]) -> bool:
    """Whether a form anomaly is a *material, severe* signal (not noise).

    Material means an identifiable cause (``probable_cause`` other than
    ``"isolated"`` -- elevation / pace / fatigue). Severe means its z-score
    magnitude exceeds ``_FORM_SEVERITY_MIN_Z`` (the detector's medium/high
    strata). Isolated noise and low-severity (``|z| <= 3.5``) spikes -- which
    occur at the ~0.22% chance base rate even on healthy form -- are excluded.
    """
    if anomaly.get("probable_cause") == "isolated":
        return False
    z = anomaly.get("z_score")
    if z is None:
        return False
    return abs(float(z)) > _FORM_SEVERITY_MIN_Z


def count_material_events(anomalies: list[dict[str, Any]]) -> int:
    """Count deduped material-severe form-anomaly *events* in one activity.

    Filters to material-severe anomalies (``is_material_severe``), then collapses
    anomalies whose timestamps are within ``_FORM_EVENT_DEDUP_WINDOW_S`` seconds
    of the previous one into a single event. A single stop/transition that trips
    2-6 per-metric detections across GCT/VO/VR counts once, not many times.
    """
    timestamps = sorted(a["timestamp"] for a in anomalies if is_material_severe(a))
    if not timestamps:
        return 0
    events = 1
    prev = timestamps[0]
    for ts in timestamps[1:]:
        if ts - prev > _FORM_EVENT_DEDUP_WINDOW_S:
            events += 1
        prev = ts
    return events


def count_high_severity(anomalies: list[dict[str, Any]]) -> int:
    """Count *material* anomalies whose z-score is in the high stratum.

    Counts anomalies that are material (identifiable cause, not ``"isolated"``)
    AND whose ``|z|`` exceeds ``_HIGH_SEVERITY_Z`` (the detector's ``z > 4.5``
    high band). Isolated high-z noise is excluded so the badge reflects only
    genuine, high-magnitude form movement. No dedup is applied -- this is a raw
    high-severity count, not an event count.
    """
    total = 0
    for a in anomalies:
        if a.get("probable_cause") == "isolated":
            continue
        z = a.get("z_score")
        if z is None:
            continue
        if abs(float(z)) > _HIGH_SEVERITY_Z:
            total += 1
    return total


def should_flag_run(events: int, hours: float, baseline_rate: float | None) -> bool:
    """Whether a run should flag on the caution card given its material events.

    A run flags only when it has at least ``FLAG_MIN_EVENTS`` deduped material
    events AND those events exceed ``FLAG_EXPECTED_MULTIPLIER`` times the count
    expected from the personal ``baseline_rate`` (events/hour) over the run's
    ``hours``. When ``baseline_rate`` is ``None`` (too little baseline running to
    compare against) the rule falls back to the conservative fixed floor
    (``events >= FLAG_MIN_EVENTS``).

    Args:
        events: Deduped material-severe event count for the run.
        hours: Run duration in hours (from ``total_time_seconds``).
        baseline_rate: Personal baseline material-event rate (events/hour), or
            ``None`` when the baseline is too sparse to compare against.

    Returns:
        ``True`` when the run is noteworthy enough to surface, else ``False``.
    """
    if events < FLAG_MIN_EVENTS:
        return False
    if baseline_rate is None:
        return True
    return events >= FLAG_EXPECTED_MULTIPLIER * baseline_rate * hours
