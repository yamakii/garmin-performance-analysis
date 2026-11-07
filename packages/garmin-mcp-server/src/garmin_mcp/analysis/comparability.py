"""Whether two runs may be compared, metric by metric (#1523).

Every run-to-run comparison -- the run report's ``vs_previous``, the recurrence
look-back, the CONTEXT ``previous_same_type`` and ``compare_similar_workouts``
-- asks the same question first: were both runs measured the same way and run
under the same load? A pod run compared with a wrist run differs in ground
contact because the sensor differs; a chest-strap run compared with a wrist run
differs in heart rate for the same reason; a run with a 3 kg backpack differs
in both because the athlete carried something. Such a pair is not compared
silently: :func:`assess` names the metrics it may not compare and why, and the
caller drops those deltas and says so.

The module also carries the static provenance of each metric -- measured by a
sensor, derived on the device from other measurements, or computed here -- so
the coach can tell a confirmation apart from a number computed from the same
inputs (stride length is speed / cadence; flight time is step time minus
ground contact).

Pure: no I/O except :func:`load_profiles`, which takes the query callable of
its caller so it works on any connection.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

#: Running-dynamics metrics: their values depend on the dynamics sensor.
DYNAMICS_METRICS: frozenset[str] = frozenset(
    {"gct_ms", "vo_cm", "vr_pct", "stride_length_cm", "balance"}
)

#: Heart-rate metrics: their values depend on the HR sensor.
HR_METRICS: frozenset[str] = frozenset(
    {"avg_hr", "hr_per_pace", "drift_pct", "hr_efficiency"}
)

#: Comparison keys built on top of one of the metrics above. When the metric
#: a key is built from is excluded, the key goes with it.
DERIVED_FROM: dict[str, frozenset[str]] = {
    "pace_at_hr": frozenset({"avg_hr"}),
    "decoupling_pct": frozenset({"drift_pct"}),
    "hr_diff": frozenset({"avg_hr"}),
}

#: How each metric came to be, for a run without a running pod. ``measured``
#: is read off a sensor, ``device_derived`` is computed by the watch from other
#: measurements, ``computed`` is computed by this system.
METRIC_PROVENANCE: dict[str, str] = {
    "pace_s_per_km": "measured",
    "avg_hr": "measured",
    "cadence_spm": "measured",
    "power": "device_derived",
    "gct_ms": "device_derived",
    "vo_cm": "device_derived",
    "vr_pct": "device_derived",
    "balance": "device_derived",
    "stride_length_cm": "device_derived",
    "flight_time_ms": "computed",
    "drift_pct": "computed",
    "decoupling_pct": "computed",
    "pace_at_hr": "computed",
    "hr_per_pace": "computed",
    "hr_efficiency": "computed",
    "hr_vs_expected": "computed",
}

# The metrics a running pod measures directly (on the wrist the watch infers
# them from the accelerometer).
_POD_MEASURED: frozenset[str] = frozenset({"gct_ms", "vo_cm", "balance"})

# A load difference smaller than this (kg) is not a different run.
LOAD_DIFF_KG = 1.0

REASON_DYNAMICS = "dynamics_source_differs"
REASON_HR = "hr_source_differs"
REASON_LOAD = "load_differs"

# What :func:`load_profiles` returns for a run it knows nothing about.
_EMPTY_PROFILE: dict[str, Any] = {
    "dynamics_source": None,
    "hr_source": None,
    "load_kg": None,
}


@dataclass(frozen=True)
class Comparability:
    """Which metrics of a pair may be compared, and why the rest may not."""

    comparable_metrics: frozenset[str]
    excluded_metrics: frozenset[str]
    reasons: tuple[str, ...]

    def allows(self, metric: str) -> bool:
        """Whether ``metric`` (or the key it is derived from) may be compared."""
        if metric in self.excluded_metrics:
            return False
        return not (DERIVED_FROM.get(metric, frozenset()) & self.excluded_metrics)

    @property
    def hr_comparable(self) -> bool:
        """No heart-rate metric is excluded."""
        return not (HR_METRICS & self.excluded_metrics)

    @property
    def sensors_match(self) -> bool:
        """Neither sensor differs (a load difference does not count)."""
        return not ({REASON_DYNAMICS, REASON_HR} & set(self.reasons))

    def to_dict(self) -> dict[str, list[str]]:
        """``{"excluded_metrics", "reasons"}`` as plain JSON lists."""
        return {
            "excluded_metrics": sorted(self.excluded_metrics),
            "reasons": list(self.reasons),
        }


def assess(today: Mapping[str, Any], other: Mapping[str, Any]) -> Comparability:
    """Which metrics ``today`` and ``other`` may be compared on.

    Args:
        today: ``{"dynamics_source", "hr_source", "load_kg"}`` of one run.
        other: The same keys of the run it is compared with.

    Returns:
        The comparable / excluded metric sets and the reasons, in the fixed
        order dynamics, hr, load. A ``None`` sensor on either side is a legacy
        row and stays comparable; a ``None`` load is an unloaded run.
    """
    excluded: set[str] = set()
    reasons: list[str] = []

    if _differs(today.get("dynamics_source"), other.get("dynamics_source")):
        excluded |= DYNAMICS_METRICS
        reasons.append(REASON_DYNAMICS)
    if _differs(today.get("hr_source"), other.get("hr_source")):
        excluded |= HR_METRICS
        reasons.append(REASON_HR)
    if abs(_load(today) - _load(other)) >= LOAD_DIFF_KG:
        excluded |= HR_METRICS | DYNAMICS_METRICS
        reasons.append(REASON_LOAD)

    every = DYNAMICS_METRICS | HR_METRICS
    return Comparability(
        comparable_metrics=frozenset(every - excluded),
        excluded_metrics=frozenset(excluded),
        reasons=tuple(reasons),
    )


def drop_excluded(
    deltas: Mapping[str, Any], comparability: Comparability
) -> dict[str, Any]:
    """``deltas`` without the keys ``comparability`` excludes, plus why.

    Keys that are not metrics (ids, dates) pass through. The result carries
    ``comparability = {"excluded_metrics", "reasons"}``.
    """
    kept = {key: value for key, value in deltas.items() if comparability.allows(key)}
    kept["comparability"] = comparability.to_dict()
    return kept


def provenance_for(metric: str, dynamics_source: str | None) -> str:
    """``measured`` / ``device_derived`` / ``computed`` for one run's metric.

    Ground contact, vertical oscillation and balance are measured only by a
    running pod; on the wrist the watch infers them. Anything not in
    :data:`METRIC_PROVENANCE` is something this system computed.
    """
    if metric in _POD_MEASURED and dynamics_source == "pod":
        return "measured"
    return METRIC_PROVENANCE.get(metric, "computed")


def provenance_map(dynamics_source: str | None) -> dict[str, str]:
    """:func:`provenance_for` for every metric in :data:`METRIC_PROVENANCE`."""
    return {
        metric: provenance_for(metric, dynamics_source) for metric in METRIC_PROVENANCE
    }


def load_profiles(
    query: Callable[[str, Sequence[Any]], Iterable[Sequence[Any]]],
    activity_ids: Iterable[int],
    user_id: str = "default",
) -> dict[int, dict[str, Any]]:
    """The comparability profile of each run, read with the caller's ``query``.

    ``dynamics_source`` / ``hr_source`` come from ``activities`` (#1459) and
    ``load_kg`` from the newest ``load`` row of ``activity_context`` (#1520).
    A database without the columns or the table leaves them ``None`` -- every
    run then stays comparable.

    Args:
        query: ``(sql, params) -> rows``.
        activity_ids: The runs to profile.
        user_id: Owner of the ``activity_context`` rows.

    Returns:
        ``{activity_id: {"dynamics_source", "hr_source", "load_kg"}}`` with an
        entry for every requested id.
    """
    ids = sorted({int(activity_id) for activity_id in activity_ids})
    profiles = {activity_id: dict(_EMPTY_PROFILE) for activity_id in ids}
    if not ids:
        return profiles

    columns = _present_columns(query)
    placeholders = ", ".join("?" for _ in ids)

    sensor_columns = [
        column
        for column in ("dynamics_source", "hr_source")
        if ("activities", column) in columns
    ]
    if sensor_columns:
        for row in query(
            f"SELECT activity_id, {', '.join(sensor_columns)} FROM activities "
            f"WHERE activity_id IN ({placeholders})",
            ids,
        ):
            profile = profiles.get(int(row[0]))
            if profile is not None:
                for index, column in enumerate(sensor_columns, start=1):
                    profile[column] = row[index]

    if ("activity_context", "load_kg") in columns:
        for row in query(
            "SELECT activity_id, load_kg FROM activity_context "
            f"WHERE user_id = ? AND kind = 'load' AND activity_id IN ({placeholders}) "
            "QUALIFY ROW_NUMBER() OVER ("
            "PARTITION BY activity_id ORDER BY created_at DESC, context_id DESC) = 1",
            [user_id, *ids],
        ):
            profile = profiles.get(int(row[0]))
            if profile is not None:
                profile["load_kg"] = None if row[1] is None else float(row[1])

    return profiles


def _present_columns(
    query: Callable[[str, Sequence[Any]], Iterable[Sequence[Any]]],
) -> set[tuple[str, str]]:
    """``(table, column)`` pairs of the two tables :func:`load_profiles` reads."""
    return {
        (str(row[0]), str(row[1]))
        for row in query(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'main' "
            "AND table_name IN ('activities', 'activity_context')",
            [],
        )
    }


def _differs(left: Any, right: Any) -> bool:
    """Both sides recorded and not the same."""
    return left is not None and right is not None and left != right


def _load(profile: Mapping[str, Any]) -> float:
    """The stated load in kg; unstated is unloaded."""
    value = profile.get("load_kg")
    try:
        return 0.0 if value is None else float(value)
    except (TypeError, ValueError):
        return 0.0
