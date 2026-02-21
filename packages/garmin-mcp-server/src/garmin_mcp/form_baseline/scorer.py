"""Form baseline scorer module.

Scores actual form metrics against baseline expectations and generates star ratings.

Uses asymmetric penalty: lower-than-expected values (= more efficient) receive
reduced penalties, while higher-than-expected values (= less efficient) receive
full penalties. A consistency adjustment rewards balanced improvement across all
three metrics and penalizes divergent patterns.
"""

from typing import Any

from .predictor import predict_expectations
from .trainer import GCTPowerModel, LinearModel

# Penalty factors by direction.
# Lower-than-expected (negative delta) = efficiency improvement → reduced penalty.
# Higher-than-expected (positive delta) = degradation → full penalty.
IMPROVEMENT_FACTOR: dict[str, float] = {"gct": 0.3, "vo": 0.3, "vr": 0.2}
DEGRADATION_FACTOR: dict[str, float] = {"gct": 1.0, "vo": 1.0, "vr": 1.0}


def _compute_penalty(metric: str, delta_pct: float) -> float:
    """Compute asymmetric penalty for a single metric.

    Args:
        metric: 'gct', 'vo', or 'vr'
        delta_pct: Percentage delta from expected (negative = improvement)

    Returns:
        Penalty score clamped to 0-100.
    """
    factor = IMPROVEMENT_FACTOR[metric] if delta_pct < 0 else DEGRADATION_FACTOR[metric]
    return max(0.0, min(100.0, abs(delta_pct) * factor * 10.0))


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
            - gct_penalty: Penalty score for GCT (asymmetric)
            - vo_delta_cm: Absolute difference from expected (cm)
            - vo_delta_pct: Percentage difference from expected
            - vo_penalty: Penalty score for VO (asymmetric)
            - vr_delta_pct: Percentage difference from expected
            - vr_penalty: Penalty score for VR (asymmetric)
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

    # Calculate asymmetric penalties
    gct_penalty = _compute_penalty("gct", gct_delta_pct)
    vo_penalty = _compute_penalty("vo", vo_delta_pct)
    vr_penalty = _compute_penalty("vr", vr_delta_pct)

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

    return {
        **expectations,
        "gct_ms_actual": obs["gct_ms"],
        "vo_cm_actual": obs["vo_cm"],
        "vr_pct_actual": obs["vr_pct"],
        "gct_delta_pct": gct_delta_pct,
        "gct_penalty": gct_penalty,
        "vo_delta_cm": vo_delta_cm,
        "vo_delta_pct": vo_delta_pct,
        "vo_penalty": vo_penalty,
        "vr_delta_pct": vr_delta_pct,
        "vr_penalty": vr_penalty,
        "score": overall_score,
        "gct_needs_improvement": gct_needs_improvement,
        "vo_needs_improvement": vo_needs_improvement,
        "vr_needs_improvement": vr_needs_improvement,
    }


def compute_star_rating(
    penalty: float,
    delta_pct: float,
) -> dict[str, Any]:
    """Compute star rating from penalty score.

    With asymmetric penalties, the direction information is already encoded
    in the penalty value, so only penalty thresholds are used for rating.
    The delta_pct parameter is kept for interface compatibility but is not
    used in the rating logic.

    Star rating logic:
    - 5 stars (5.0): Excellent - penalty < 10
    - 4 stars (4.0): Good - penalty < 20
    - 3 stars (3.0): Average - penalty < 40
    - 2 stars (2.0): Below Average - penalty < 60
    - 1 star (1.0): Poor - penalty >= 60

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
