"""Deterministic race-time prediction (no I/O).

Blends two independent fitness signals into a single confidence-tagged
race-time prediction per distance:

- **VDOT**: :meth:`VDOTCalculator.predict_race_time` from the athlete's current
  Daniels VDOT (Garmin-derived, tends optimistic).
- **Objective fitness curve**: the best-effort performance VDOT extracted from
  real splits per distance bucket (2/5/10km, see ``objective_fitness``), which
  is non-optimistic but only covers the distances actually run.

For a target distance the two predicted times are blended
(``curve 0.6 / vdot 0.4``) and tagged with a confidence:

- both sources present and within ``AGREEMENT_THRESHOLD`` (3%) -> ``"high"``
- both present but diverging -> ``"medium"``
- only one source (VDOT-only, or curve-only) -> ``"low"``
- the curve bucket is not near the target (half/full extrapolated from 10km)
  downgrades the confidence one level (``high`` -> ``medium`` -> ``low``)

Pure function, no DB/IO; the reader wires DuckDB-derived inputs in.
"""

from __future__ import annotations

from typing import Any

from garmin_mcp.fitness.vdot import VDOTCalculator

# Blend weights: the objective curve (real splits) outweighs the optimistic
# VDOT estimate, but VDOT still contributes (Issue #716).
CURVE_WEIGHT = 0.6
VDOT_WEIGHT = 0.4

# Relative gap between the two predicted times below which the sources are said
# to "agree" (confidence high).
AGREEMENT_THRESHOLD = 0.03

# A curve bucket is treated as a direct match (not extrapolated) when it is
# within this relative distance of the target. 5km/10km targets hit their own
# bucket exactly; half/full fall back to the 10km bucket (extrapolated).
BUCKET_MATCH_TOLERANCE = 0.15

# Standard race distances (km) -> readiness output keys (mirrors race.py).
_DISTANCE_KEYS: dict[float, str] = {
    5.0: "race_5k",
    10.0: "race_10k",
    21.0975: "half",
    42.195: "full",
}

_DEFAULT_DISTANCES_KM: tuple[float, ...] = (5.0, 10.0, 21.0975, 42.195)

_CONFIDENCE_DOWNGRADE: dict[str, str] = {
    "high": "medium",
    "medium": "low",
    "low": "low",
}


def predict_race_times(
    current_vdot: float | None,
    fitness_curve: dict[str, Any] | None,
    distances_km: tuple[float, ...] = _DEFAULT_DISTANCES_KM,
) -> dict[str, Any]:
    """Blend VDOT and objective-curve race-time predictions per distance.

    Args:
        current_vdot: Current Daniels VDOT, or ``None`` when unavailable.
        fitness_curve: ``FitnessCurveReader.get_objective_fitness_curve``'s
            return value (its ``objective_curve`` provides per-bucket objective
            VDOT), or ``None``.
        distances_km: Race distances to predict (default 5k/10k/half/full).

    Returns:
        When both sources are missing: ``{"insufficient_data": True}`` (matches
        the ``derivations.py`` convention). Otherwise a dict keyed by
        ``race_5k`` / ``race_10k`` / ``half`` / ``full`` (or ``race_{d}k`` for
        non-standard distances), each mapping to::

            {"predicted_seconds": int,
             "confidence": "high" | "medium" | "low",
             "sources": ["vdot"] | ["curve"] | ["vdot", "curve"]}
    """
    curve_buckets = _extract_curve_buckets(fitness_curve)

    if current_vdot is None and not curve_buckets:
        return {"insufficient_data": True}

    return {
        _distance_key(distance_km): _predict_one(
            current_vdot, curve_buckets, distance_km
        )
        for distance_km in distances_km
    }


def _distance_key(distance_km: float) -> str:
    """Map a distance (km) to its readiness output key."""
    for standard, key in _DISTANCE_KEYS.items():
        if abs(distance_km - standard) < 1e-6:
            return key
    return f"race_{distance_km:g}k"


def _extract_curve_buckets(
    fitness_curve: dict[str, Any] | None,
) -> dict[float, float]:
    """Latest objective VDOT per source distance bucket from the curve.

    ``objective_curve`` is ascending by run date, so the last point for a given
    ``source_distance_km`` is the most recent (current) objective VDOT for that
    bucket.
    """
    if not fitness_curve:
        return {}
    curve = fitness_curve.get("objective_curve") or []
    buckets: dict[float, float] = {}
    for point in curve:
        dist = point.get("source_distance_km")
        vdot = point.get("vdot")
        if dist is None or vdot is None:
            continue
        buckets[float(dist)] = float(vdot)
    return buckets


def _curve_prediction(
    curve_buckets: dict[float, float], distance_km: float
) -> tuple[int, bool] | None:
    """Predicted seconds from the nearest curve bucket + whether extrapolated.

    Returns ``None`` when the curve has no buckets. ``extrapolated`` is True
    when the nearest bucket is not within ``BUCKET_MATCH_TOLERANCE`` of the
    target distance (e.g. predicting half/full from the 10km bucket).
    """
    if not curve_buckets:
        return None
    nearest = min(curve_buckets, key=lambda b: abs(b - distance_km))
    objective_vdot = curve_buckets[nearest]
    extrapolated = abs(nearest - distance_km) / distance_km > BUCKET_MATCH_TOLERANCE
    predicted = VDOTCalculator.predict_race_time(objective_vdot, distance_km)
    return predicted, extrapolated


def _predict_one(
    current_vdot: float | None,
    curve_buckets: dict[float, float],
    distance_km: float,
) -> dict[str, Any]:
    """Blend the two sources for a single distance (see module docstring)."""
    vdot_seconds = (
        VDOTCalculator.predict_race_time(current_vdot, distance_km)
        if current_vdot is not None
        else None
    )
    curve_pred = _curve_prediction(curve_buckets, distance_km)

    if vdot_seconds is not None and curve_pred is not None:
        curve_seconds, extrapolated = curve_pred
        blended = round(CURVE_WEIGHT * curve_seconds + VDOT_WEIGHT * vdot_seconds)
        divergence = abs(curve_seconds - vdot_seconds) / vdot_seconds
        confidence = "high" if divergence < AGREEMENT_THRESHOLD else "medium"
        if extrapolated:
            confidence = _CONFIDENCE_DOWNGRADE[confidence]
        return {
            "predicted_seconds": int(blended),
            "confidence": confidence,
            "sources": ["vdot", "curve"],
        }

    if vdot_seconds is not None:
        return {
            "predicted_seconds": int(vdot_seconds),
            "confidence": "low",
            "sources": ["vdot"],
        }

    # curve-only (current_vdot is None but a bucket exists)
    assert curve_pred is not None
    curve_seconds, _extrapolated = curve_pred
    return {
        "predicted_seconds": int(curve_seconds),
        "confidence": "low",
        "sources": ["curve"],
    }
