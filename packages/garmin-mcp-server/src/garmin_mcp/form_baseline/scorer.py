"""Form baseline scorer module.

Scores actual form metrics against baseline expectations and generates star ratings.

Deviations are measured in units of the metric's own model error (sigma), not in
fixed percentages: each baseline model has a different prediction error, so the
same percentage deviation is statistically ordinary for one metric and unusual
for another. Scaling by sigma makes the star ratings comparable across metrics.

Uses asymmetric penalty: lower-than-expected values (= more efficient) receive
reduced penalties, while higher-than-expected values (= less efficient) receive
full penalties. A consistency adjustment rewards balanced improvement across all
three metrics and penalizes divergent patterns.
"""

import math
from typing import Any

from .predictor import predict_expectations
from .trainer import GCTPowerModel, LinearModel

# Penalty factors by direction.
# For GCT/VO/VR: lower-than-expected (negative delta) = efficiency improvement
#   → reduced penalty; higher-than-expected (positive delta) = degradation → full.
# For cadence the direction is REVERSED: higher-than-expected (positive delta) =
#   improvement → reduced penalty; lower-than-expected (negative delta) =
#   degradation → full penalty.
# The improvement factor is uniform across metrics so that an equal statistical
# improvement earns an equal rating regardless of which metric it lands in.
IMPROVEMENT_FACTOR: dict[str, float] = {
    "gct": 0.3,
    "vo": 0.3,
    "vr": 0.3,
    "cadence": 0.3,
}
DEGRADATION_FACTOR: dict[str, float] = {
    "gct": 1.0,
    "vo": 1.0,
    "vr": 1.0,
    "cadence": 1.0,
}

# One sigma of model error costs this much penalty. Combined with the existing
# 10/20/40/60 star cuts (see compute_star_rating) the degradation side becomes
# 5* < 0.5 sigma, 4* < 1 sigma, 3* < 2 sigma, 2* < 3 sigma.
PENALTY_PER_SIGMA = 20.0

# Legacy fallback: penalty per percentage point when no usable model error is
# available (old baselines persisted without a usable rmse).
PENALTY_PER_PCT = 10.0


def _sigma_pct(
    metric: str,
    model: GCTPowerModel | LinearModel,
    expected: float,
) -> float | None:
    """Model prediction error as a percentage of the expected value.

    Linear (vo/vr/cadence): ``100 * rmse / expected``.
    GCT power model: rmse lives in log-speed space, so the relative error on gct
    is ``100 * (exp(rmse / abs(d)) - 1)``.

    Args:
        metric: 'gct', 'vo', 'vr', or 'cadence'
        model: Trained model for that metric
        expected: Expected value predicted by the model (metric units)

    Returns:
        Sigma as a percentage of the expected value, or None when it cannot be
        derived (missing/zero rmse or expected).
    """
    rmse = model.rmse
    if not rmse or rmse <= 0.0:
        return None

    if metric == "gct" and isinstance(model, GCTPowerModel):
        # log(v) = alpha + d * log(gct)  ->  a residual of `rmse` in log-speed
        # space maps to a log-gct shift of rmse / |d|.
        if not model.d:
            return None
        return 100.0 * (math.exp(rmse / abs(model.d)) - 1.0)

    if not expected:
        return None
    return 100.0 * rmse / abs(expected)


def _compute_penalty(
    metric: str,
    delta_pct: float,
    sigma_pct: float | None = None,
) -> float:
    """Compute asymmetric, sigma-scaled penalty for a single metric.

    For GCT/VO/VR a negative delta (actual < expected) is an improvement.
    For cadence the direction is reversed: a positive delta (actual > expected)
    is the improvement and a negative delta (actual < expected) is degradation.

    The deviation is expressed in units of the metric's own model error, so one
    sigma always costs ``PENALTY_PER_SIGMA`` regardless of metric. When no usable
    sigma is available the legacy fixed-percentage formula is used instead.

    Args:
        metric: 'gct', 'vo', 'vr', or 'cadence'
        delta_pct: Percentage delta from expected
        sigma_pct: Model error as a percentage of expected (see :func:`_sigma_pct`)

    Returns:
        Penalty score clamped to 0-100.
    """
    # Reversed direction for cadence: positive delta = improvement.
    is_improvement = delta_pct > 0 if metric == "cadence" else delta_pct < 0

    factor = (
        IMPROVEMENT_FACTOR[metric] if is_improvement else DEGRADATION_FACTOR[metric]
    )

    if sigma_pct is not None and sigma_pct > 0.0:
        magnitude = abs(delta_pct / sigma_pct) * PENALTY_PER_SIGMA
    else:
        magnitude = abs(delta_pct) * PENALTY_PER_PCT

    return max(0.0, min(100.0, magnitude * factor))


def _compute_consistency_adjustment(
    gct_delta_pct: float,
    vo_delta_pct: float,
    vr_delta_pct: float,
) -> float:
    """Compute consistency adjustment across the three form metrics.

    Rewards balanced improvement (all deltas negative) and penalizes
    divergent patterns (large spread between metrics).

    Args:
        gct_delta_pct: GCT percentage delta from expected
        vo_delta_pct: VO percentage delta from expected
        vr_delta_pct: VR percentage delta from expected

    Returns:
        Adjustment value (positive = bonus, negative = penalty) to apply
        to the overall score.
    """
    deltas = [gct_delta_pct, vo_delta_pct, vr_delta_pct]
    all_improved = all(d <= 0 for d in deltas)
    spread = max(deltas) - min(deltas)

    if all_improved:
        return min(5.0, abs(sum(deltas)) / 3.0 * 0.5)
    elif spread > 15.0:
        return -10.0
    elif spread > 10.0:
        return -5.0
    elif spread > 5.0:
        return -2.0
    return 0.0


def score_observation(
    models: dict[str, GCTPowerModel | LinearModel],
    obs: dict[str, float],
) -> dict[str, Any]:
    """Score actual observation against baseline expectations.

    Deviations are scaled by each metric's own model error (sigma), derived from
    the ``models`` dict, so that an equal statistical deviation earns an equal
    penalty across metrics. Models without a usable rmse fall back to the legacy
    fixed-percentage penalty.

    Uses asymmetric penalty calculation: improvement direction (actual < expected)
    receives a reduced penalty factor, while degradation (actual > expected) uses
    the full penalty factor. A consistency adjustment is applied to the overall
    score based on the spread and direction of all three metrics.

    Args:
        models: Dictionary of trained models (gct, vo, vr)
        obs: Observation dictionary containing:
            - pace_s_per_km: Pace in seconds per kilometer (required)
            - gct_ms: Actual ground contact time in ms (required)
            - vo_cm: Actual vertical oscillation in cm (required)
            - vr_pct: Actual vertical ratio in % (required)
            - gct_L: Left foot GCT in ms (optional)
            - gct_R: Right foot GCT in ms (optional)

    Returns:
        Dictionary containing:
            - All fields from predict_expectations
            - gct_delta_pct: Percentage difference from expected
            - gct_sigma_pct: Model error as % of expected (None if unavailable)
            - gct_penalty: Penalty score for GCT (asymmetric, sigma-scaled)
            - vo_delta_cm: Absolute difference from expected (cm)
            - vo_delta_pct: Percentage difference from expected
            - vo_sigma_pct: Model error as % of expected (None if unavailable)
            - vo_penalty: Penalty score for VO (asymmetric, sigma-scaled)
            - vr_delta_pct: Percentage difference from expected
            - vr_sigma_pct: Model error as % of expected (None if unavailable)
            - vr_penalty: Penalty score for VR (asymmetric, sigma-scaled)
            - score: Overall score (0-100, with consistency adjustment)
            - gct_needs_improvement: Boolean flag
            - vo_needs_improvement: Boolean flag
            - vr_needs_improvement: Boolean flag

    Example:
        >>> obs = {
        ...     'pace_s_per_km': 240.0,
        ...     'gct_ms': 220.0,
        ...     'vo_cm': 8.5,
        ...     'vr_pct': 7.2
        ... }
        >>> result = score_observation(models, obs)
        >>> print(result['score'])  # Overall form score
        85.3
    """
    # Get expectations
    expectations = predict_expectations(models, obs["pace_s_per_km"])

    # Calculate deltas
    gct_delta_pct = (
        (obs["gct_ms"] - expectations["gct_ms_exp"]) / expectations["gct_ms_exp"]
    ) * 100.0

    vo_delta_cm = obs["vo_cm"] - expectations["vo_cm_exp"]
    vo_delta_pct = (vo_delta_cm / expectations["vo_cm_exp"]) * 100.0

    vr_delta_pct = (
        (obs["vr_pct"] - expectations["vr_pct_exp"]) / expectations["vr_pct_exp"]
    ) * 100.0

    # Model error per metric (sigma), used to scale the penalties so that an
    # equal statistical deviation earns an equal rating across metrics.
    gct_sigma_pct = _sigma_pct("gct", models["gct"], expectations["gct_ms_exp"])
    vo_sigma_pct = _sigma_pct("vo", models["vo"], expectations["vo_cm_exp"])
    vr_sigma_pct = _sigma_pct("vr", models["vr"], expectations["vr_pct_exp"])

    # Calculate asymmetric penalties
    gct_penalty = _compute_penalty("gct", gct_delta_pct, gct_sigma_pct)
    vo_penalty = _compute_penalty("vo", vo_delta_pct, vo_sigma_pct)
    vr_penalty = _compute_penalty("vr", vr_delta_pct, vr_sigma_pct)

    # Overall score with consistency adjustment
    avg_penalty = (gct_penalty + vo_penalty + vr_penalty) / 3.0
    adjustment = _compute_consistency_adjustment(
        gct_delta_pct, vo_delta_pct, vr_delta_pct
    )
    overall_score = max(0.0, min(100.0, 100.0 - avg_penalty + adjustment))

    # Needs improvement flags (penalty > 20 = needs improvement)
    gct_needs_improvement = gct_penalty > 20.0
    vo_needs_improvement = vo_penalty > 20.0
    vr_needs_improvement = vr_penalty > 20.0

    result = {
        **expectations,
        "gct_ms_actual": obs["gct_ms"],
        "vo_cm_actual": obs["vo_cm"],
        "vr_pct_actual": obs["vr_pct"],
        "gct_delta_pct": gct_delta_pct,
        "gct_sigma_pct": gct_sigma_pct,
        "gct_penalty": gct_penalty,
        "vo_delta_cm": vo_delta_cm,
        "vo_delta_pct": vo_delta_pct,
        "vo_sigma_pct": vo_sigma_pct,
        "vo_penalty": vo_penalty,
        "vr_delta_pct": vr_delta_pct,
        "vr_sigma_pct": vr_sigma_pct,
        "vr_penalty": vr_penalty,
        "score": overall_score,
        "gct_needs_improvement": gct_needs_improvement,
        "vo_needs_improvement": vo_needs_improvement,
        "vr_needs_improvement": vr_needs_improvement,
    }

    # Cadence is an INDEPENDENT metric: it is NOT included in overall_score or
    # the consistency adjustment. It is only scored when a cadence model is
    # available and the observation provides a cadence value.
    cadence_exp = expectations.get("cadence_exp")
    if cadence_exp is not None and obs.get("cadence") is not None:
        cadence_actual = obs["cadence"]
        cadence_delta_pct = ((cadence_actual - cadence_exp) / cadence_exp) * 100.0
        cadence_sigma_pct = _sigma_pct("cadence", models["cadence"], cadence_exp)
        cadence_penalty = _compute_penalty(
            "cadence", cadence_delta_pct, cadence_sigma_pct
        )
        result["cadence_actual"] = cadence_actual
        result["cadence_delta_pct"] = cadence_delta_pct
        result["cadence_sigma_pct"] = cadence_sigma_pct
        result["cadence_penalty"] = cadence_penalty
        result["cadence_needs_improvement"] = cadence_penalty > 20.0

    return result


def compute_star_rating(
    penalty: float,
    delta_pct: float,
) -> dict[str, Any]:
    """Compute star rating from penalty score.

    With asymmetric penalties, the direction information is already encoded
    in the penalty value, so only penalty thresholds are used for rating.
    The delta_pct parameter is kept for interface compatibility but is not
    used in the rating logic.

    Star rating logic (sigma equivalents are for the degradation side, where the
    factor is 1.0, given PENALTY_PER_SIGMA = 20):
    - 5 stars (5.0): Excellent - penalty < 10 (< 0.5 sigma)
    - 4 stars (4.0): Good - penalty < 20 (< 1 sigma)
    - 3 stars (3.0): Average - penalty < 40 (< 2 sigma)
    - 2 stars (2.0): Below Average - penalty < 60 (< 3 sigma)
    - 1 star (1.0): Poor - penalty >= 60 (>= 3 sigma)

    Args:
        penalty: Penalty score (0-100, already asymmetric)
        delta_pct: Percentage delta from expected (kept for compatibility)

    Returns:
        Dictionary containing:
            - star_rating: String representation (5 filled + empty stars)
            - score: Numeric score (1.0-5.0)
            - category: Category name (excellent/good/average/below_average/poor)

    Example:
        >>> rating = compute_star_rating(penalty=8.5, delta_pct=4.2)
        >>> print(rating['score'])
        5.0
    """
    # Unicode stars: U+2605 (filled) U+2606 (empty)
    filled_star = "\u2605"  # ★
    empty_star = "\u2606"  # ☆

    # Determine rating based on penalty only (direction is encoded in penalty)
    if penalty < 10.0:
        star_rating = filled_star * 5
        score = 5.0
        category = "excellent"
    elif penalty < 20.0:
        star_rating = filled_star * 4 + empty_star
        score = 4.0
        category = "good"
    elif penalty < 40.0:
        star_rating = filled_star * 3 + empty_star * 2
        score = 3.0
        category = "average"
    elif penalty < 60.0:
        star_rating = filled_star * 2 + empty_star * 3
        score = 2.0
        category = "below_average"
    else:
        star_rating = filled_star + empty_star * 4
        score = 1.0
        category = "poor"

    return {
        "star_rating": star_rating,
        "score": score,
        "category": category,
    }
