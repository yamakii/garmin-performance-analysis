"""Did the run do what it was for? (Issue #1340).

``analysis.run_moments`` finds *what happened* and ``analysis.run_policy`` says
what each scene means for the run's purpose. Neither asks the question a coach
asks first: **did this run deliver what it was for?** A long run is for holding
one effort over a distance, so a second half the athlete could no longer hold
is a miss however it showed up -- walking, a pace that drifted out, a heart
rate that sank because the running stopped.

That last point is why this module measures the run against *itself* rather
than against any one symptom. A threshold on how much walking a run contains
would miss a run that fell apart without walking, and would flag a run that
walked at an aid stop and then finished exactly as intended.

The measure:

* the **established pace** is the median of the opening third, so the yardstick
  is the pace this run actually settled into;
* a kilometre is **sustained** while its pace stays within
  :data:`BREAKDOWN_PACE_RATIO` of that;
* a **breakdown** is a stretch that reaches the end of the run, covers at least
  :data:`BREAKDOWN_MIN_KM`, and is almost entirely unsustained
  (:data:`BREAKDOWN_SUSTAINED_TOLERANCE` leaves room for one kilometre found
  again near home). A stretch the athlete came back from is a dip, not a
  breakdown.

Purposes whose point is not holding one effort -- intervals, fartlek, a
recovery jog -- are out of scope and return ``None``; they are judged on their
reps and their ceiling instead.

The module is pure: no I/O, no DB access.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import median
from typing import Any

#: Purposes that ask the athlete to hold an effort over a distance.
SUSTAIN_PURPOSES: frozenset[str] = frozenset(
    {
        "easy",
        "long_easy",
        "long_goal_pace",
        "long_fast_finish",
        "progression",
        "tempo",
        "race",
    }
)

# A kilometre slower than the established pace by more than this is not being
# held any more. 25% is a stride-length change plus a hill plus a bad patch --
# past it the athlete is doing something other than the run they started.
BREAKDOWN_PACE_RATIO = 1.25

# Shorter than this, a slow stretch is a bad patch, not the run coming apart.
BREAKDOWN_MIN_KM = 2.0

# Share of a trailing stretch that may still be sustained and have it count as
# a breakdown: the kilometre found again near home does not undo the collapse.
BREAKDOWN_SUSTAINED_TOLERANCE = 0.25

# Splits shorter than this are GPS fragments; they move the athlete down the
# road (so they carry position) but carry no judgeable pace. Mirrors the
# fragment rule ``run_moments`` draws with.
MIN_JUDGED_KM = 0.4


@dataclass(frozen=True)
class Outcome:
    """What the run delivered against its purpose.

    Attributes:
        met: ``True`` when the run held its effort to the end.
        sustained_share: Share of the judged distance run at the established
            pace.
        breakdown_from_km: Distance into the run where it came apart, or
            ``None``. Measured like a scene's ``km_from``: the start of the
            first kilometre of the breakdown.
        sustained_pace_s_per_km: Distance-weighted pace over the sustained
            kilometres -- the pace this run actually held (#1341).
        reason: Short English explanation.
    """

    met: bool
    sustained_share: float
    breakdown_from_km: float | None
    sustained_pace_s_per_km: float | None
    reason: str


def evaluate(purpose: str, splits: Sequence[Mapping[str, Any]]) -> Outcome | None:
    """Judge one run against what its purpose asked for.

    Args:
        purpose: The resolved purpose id (``analysis.run_purpose``).
        splits: The run's split rows in order, read for ``distance_km`` and
            ``pace_s_per_km``. Fragments still carry position.

    Returns:
        The :class:`Outcome`, or ``None`` when the purpose is not one this
        measure applies to, or the run has too little to judge.
    """
    if purpose not in SUSTAIN_PURPOSES:
        return None

    judged = _judged_splits(splits)
    if not judged:
        return None

    established = _established_pace(judged)
    if established is None:
        return None

    for row in judged:
        row["sustained"] = row["pace"] <= established * BREAKDOWN_PACE_RATIO

    total = sum(row["km"] for row in judged)
    held = sum(row["km"] for row in judged if row["sustained"])
    share = round(held / total, 3) if total > 0 else 0.0
    breakdown_from_km = _breakdown_start(judged, total)

    return Outcome(
        met=breakdown_from_km is None,
        sustained_share=share,
        breakdown_from_km=breakdown_from_km,
        sustained_pace_s_per_km=_sustained_pace(judged),
        reason=(
            f"held the established pace over {share:.0%} of the run"
            if breakdown_from_km is None
            else f"came apart from {breakdown_from_km:g} km to the finish"
        ),
    )


def _judged_splits(splits: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Splits with a usable pace, each carrying where in the run it sits.

    Position accumulates over *every* split, fragments included, so a scene
    built from ``start_km`` lands where the athlete actually was.
    """
    judged: list[dict[str, Any]] = []
    cumulative = 0.0
    for split in splits:
        distance = _as_float(split.get("distance_km")) or 0.0
        pace = _as_float(split.get("pace_s_per_km"))
        start_km = cumulative
        cumulative += distance
        if distance < MIN_JUDGED_KM or pace is None or pace <= 0:
            continue
        judged.append({"km": distance, "pace": pace, "start_km": round(start_km, 3)})
    return judged


def _established_pace(judged: Sequence[Mapping[str, Any]]) -> float | None:
    """The pace the run settled into: the median of its opening third."""
    size = max(1, len(judged) // 3)
    paces = [float(row["pace"]) for row in judged[:size]]
    return float(median(paces)) if paces else None


def _breakdown_start(
    judged: Sequence[Mapping[str, Any]], total_km: float
) -> float | None:
    """Where a stretch that never recovers begins, or ``None``.

    Scans from the front so the breakdown is reported from its *first*
    kilometre rather than from wherever the tail happens to start.
    """
    for index, row in enumerate(judged):
        if row["sustained"]:
            continue
        tail = judged[index:]
        distance = sum(item["km"] for item in tail)
        if distance < BREAKDOWN_MIN_KM:
            return None
        held = sum(item["km"] for item in tail if item["sustained"])
        if distance > 0 and held / distance <= BREAKDOWN_SUSTAINED_TOLERANCE:
            return float(row["start_km"])
    return None


def _sustained_pace(judged: Sequence[Mapping[str, Any]]) -> float | None:
    """Distance-weighted pace over the kilometres the run held, or ``None``."""
    held = [row for row in judged if row["sustained"]]
    distance = sum(float(row["km"]) for row in held)
    if distance <= 0:
        return None
    weighted = sum(float(row["pace"]) * float(row["km"]) for row in held)
    return round(weighted / distance, 1)


def _as_float(value: Any) -> float | None:
    """``float(value)`` when it is a real number, else ``None``."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    # NaN compares unequal to itself; a missing sensor reading is not a number.
    return number if number == number else None  # noqa: PLR0124
