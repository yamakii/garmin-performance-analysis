"""Form baseline scorer module.

Scores actual form metrics against baseline expectations and generates star ratings.
"""

from typing import Any

from .predictor import predict_expectations
from .trainer import GCTPowerModel, LinearModel


def score_observation(
    models: dict[str, GCTPowerModel | LinearModel],
    obs: dict[str, float],
) -> dict[str, Any]:
    """Score actual observation against baseline expectations.

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
            - gct_penalty: Penalty score for GCT
            - vo_delta_cm: Absolute difference from expected (cm)
            - vo_delta_pct: Percentage difference from expected
            - vo_penalty: Penalty score for VO
            - vr_delta_pct: Percentage difference from expected
            - vr_penalty: Penalty score for VR
            - score: Overall score (0-100)
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

    # Calculate penalties (higher delta = higher penalty)
    # All metrics use percentage-based penalty calculation for consistency
    # GCT: exceeding by >5% is concerning
    gct_penalty = max(0.0, min(100.0, abs(gct_delta_pct) * 10.0))

    # VO: exceeding by >5% is concerning (now percentage-based like GCT/VR)
    vo_penalty = max(0.0, min(100.0, abs(vo_delta_pct) * 10.0))

    # VR: exceeding by >5% is concerning
    vr_penalty = max(0.0, min(100.0, abs(vr_delta_pct) * 10.0))

    # Overall score (100 - average penalty)
    avg_penalty = (gct_penalty + vo_penalty + vr_penalty) / 3.0
    overall_score = max(0.0, 100.0 - avg_penalty)

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
    """Compute star rating from penalty and delta percentage.

    Star rating logic (using ASCII representation):
    - 5 stars (5.0): Excellent - penalty < 10, delta < 5%
    - 4 stars (4.0): Good - penalty < 20, delta < 10%
    - 3 stars (3.0): Average - penalty < 40, delta < 20%
    - 2 stars (2.0): Below Average - penalty < 60, delta < 30%
    - 1 star (1.0): Poor - penalty >= 60 or delta >= 30%

    Args:
        penalty: Penalty score (0-100)
        delta_pct: Percentage delta from expected

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
    abs_delta = abs(delta_pct)

    # Unicode stars: U+2605 (filled) U+2606 (empty)
    filled_star = "\u2605"  # ★
    empty_star = "\u2606"  # ☆

    # Determine rating based on penalty and delta
    if penalty < 10.0 and abs_delta < 5.0:
        star_rating = filled_star * 5
        score = 5.0
        category = "excellent"
    elif penalty < 20.0 and abs_delta < 10.0:
        star_rating = filled_star * 4 + empty_star
        score = 4.0
        category = "good"
    elif penalty < 40.0 and abs_delta < 20.0:
        star_rating = filled_star * 3 + empty_star * 2
        score = 3.0
        category = "average"
    elif penalty < 60.0 and abs_delta < 30.0:
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
