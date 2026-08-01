"""Japanese evaluation text generation for form metrics.

This module generates natural Japanese evaluation text for GCT, VO, and VR metrics
based on the deviation from expected values.

The wording bands follow the metric's own model error (sigma) so that the text
agrees with the sigma-scaled star ratings produced by
:mod:`garmin_mcp.form_baseline.scorer`. ``IDEAL_SIGMA`` matches the 4-star cut
(penalty 20) and ``MODERATE_SIGMA`` the 2-star cut (penalty 50) on the
degradation side. When no model error is available the legacy fixed-percentage
bands are used instead.
"""

# Band edges in units of model error (sigma).
IDEAL_SIGMA = 1.0
MODERATE_SIGMA = 2.5

# Legacy fallback bands (percentage points), used when sigma is unavailable.
LEGACY_IDEAL_PCT = 2.0
LEGACY_MODERATE_PCT = 5.0


def _band_edges(sigma_pct: float | None) -> tuple[float, float]:
    """Return the (ideal, moderate) band edges in percentage points.

    Args:
        sigma_pct: Model error as a percentage of the expected value, or None

    Returns:
        Tuple of (ideal_edge_pct, moderate_edge_pct).
    """
    if sigma_pct is not None and sigma_pct > 0:
        return sigma_pct * IDEAL_SIGMA, sigma_pct * MODERATE_SIGMA
    return LEGACY_IDEAL_PCT, LEGACY_MODERATE_PCT


def _format_pace(pace_s_per_km: float) -> str:
    """Format pace in seconds per km to MM:SS format.

    Args:
        pace_s_per_km: Pace in seconds per kilometer

    Returns:
        Formatted pace string (e.g., "7:11")
    """
    minutes = int(pace_s_per_km // 60)
    seconds = int(pace_s_per_km % 60)
    return f"{minutes}:{seconds:02d}"


def generate_evaluation_text(
    metric: str,
    actual: float,
    expected: float,
    delta_pct: float,
    pace_s_per_km: float,
    star_rating: str,
    score: float,
    sigma_pct: float | None = None,
) -> str:
    """Generate Japanese evaluation text for a single metric.

    Asymmetric evaluation: lower-than-expected values indicate efficiency improvement
    and receive positive text, while higher-than-expected values indicate degradation.

    Args:
        metric: 'gct', 'vo', 'vr', or 'cadence'
        actual: Actual measured value
        expected: Expected value from baseline model
        delta_pct: Delta percentage ((actual - expected) / expected * 100)
        pace_s_per_km: Pace in seconds per km (for context)
        star_rating: Star rating string (e.g., '★★★★★')
        score: Numeric score (0-5.0)
        sigma_pct: Model error as a percentage of the expected value. The wording
            bands scale with it so the text matches the sigma-scaled star rating.
            Falls back to the legacy fixed 2%/5% bands when None or non-positive.

    Returns:
        Japanese evaluation text

    Example:
        >>> generate_evaluation_text(
        ...     'gct', 258.0, 261.0, -1.1, 431.0, '★★★★★', 5.0, 2.0
        ... )
        '258msは期待値261ms±2.0%の理想範囲内です。適切な接地時間を維持できています。★★★★★'
    """
    # Cadence has REVERSED semantics (higher cadence = better), so it is
    # handled separately from the GCT/VO/VR efficiency metrics.
    if metric == "cadence":
        return _generate_cadence_text(
            actual=actual,
            expected=expected,
            delta_pct=delta_pct,
            star_rating=star_rating,
            sigma_pct=sigma_pct,
        )

    # Metric-specific labels
    labels = {
        "gct": {
            "name": "接地時間",
            "unit": "ms",
            "direction_low": "短く",
            "direction_high": "長く",
            "improvement_action": "接地時間の安定化",
        },
        "vo": {
            "name": "上下動",
            "unit": "cm",
            "direction_low": "小さく",
            "direction_high": "大きく",
            "improvement_action": "上下動の安定化トレーニング",
        },
        "vr": {
            "name": "上下動比",
            "unit": "%",
            "direction_low": "低く",
            "direction_high": "高く",
            "improvement_action": "フォームバランスの改善",
        },
    }

    label = labels[metric]
    name = label["name"]
    unit = label["unit"]

    # Format values: GCT=integer, VO/VR=1 decimal place
    if metric == "gct":
        actual_str = f"{actual:.0f}"
        expected_str = f"{expected:.0f}"
    else:  # vo or vr
        actual_str = f"{actual:.1f}"
        expected_str = f"{expected:.1f}"

    # Band edges follow the model error (sigma) when it is available, so the
    # wording stays consistent with the sigma-scaled star rating.
    ideal_edge, moderate_edge = _band_edges(sigma_pct)

    # Asymmetric evaluation: improvement direction (lower) is positive,
    # degradation direction (higher) is negative.
    if abs(delta_pct) <= ideal_edge:
        # Ideal (within 1 sigma of expected)
        text = (
            f"{actual_str}{unit}は期待値{expected_str}{unit}"
            f"±{ideal_edge:.1f}%の理想範囲内です。"
            f"適切な{name}を維持できています。{star_rating}"
        )
    elif delta_pct < 0 and abs(delta_pct) <= moderate_edge:
        # Slight improvement (within the moderate band, lower = more efficient)
        direction = label["direction_low"]
        text = (
            f"{actual_str}{unit}は期待値{expected_str}{unit}より"
            f"{abs(delta_pct):.1f}%{direction}、効率的なフォームです。{star_rating}"
        )
    elif delta_pct < 0:
        # Large improvement (beyond the moderate band, lower = more efficient)
        direction = label["direction_low"]
        text = (
            f"{actual_str}{unit}は期待値{expected_str}{unit}より"
            f"{abs(delta_pct):.0f}%{direction}、効率面で良好です。"
            f"この指標自体は良好で、他の指標とのバランスで総合評価されています。{star_rating}"
        )
    elif abs(delta_pct) <= moderate_edge:
        # Slightly degraded (within the moderate band, higher = less efficient)
        direction = label["direction_high"]
        text = (
            f"{actual_str}{unit}は期待値{expected_str}{unit}より"
            f"{abs(delta_pct):.1f}%{direction}、やや外れています。"
            f"通常のフォームから軽度のズレが見られます。{star_rating}"
        )
    else:
        # Significantly degraded (beyond the moderate band, higher = less efficient)
        direction = label["direction_high"]
        text = (
            f"{actual_str}{unit}は期待値{expected_str}{unit}より"
            f"{abs(delta_pct):.0f}%{direction}、大きく外れています。"
            f"フォームの不安定さが見られます。{label['improvement_action']}を推奨します。{star_rating}"
        )

    return text


def _generate_cadence_text(
    actual: float,
    expected: float,
    delta_pct: float,
    star_rating: str,
    sigma_pct: float | None = None,
) -> str:
    """Generate Japanese evaluation text for cadence.

    Cadence has reversed semantics compared to GCT/VO/VR: a higher-than-expected
    cadence (positive delta) is an improvement, while a lower-than-expected
    cadence (negative delta) is degradation.

    Args:
        actual: Actual measured cadence (spm)
        expected: Expected cadence from baseline model (spm)
        delta_pct: Delta percentage ((actual - expected) / expected * 100)
        star_rating: Star rating string (e.g., '★★★★★')
        sigma_pct: Model error as a percentage of the expected value (see
            :func:`generate_evaluation_text`)

    Returns:
        Japanese evaluation text
    """
    actual_str = f"{actual:.0f}"
    expected_str = f"{expected:.0f}"
    ideal_edge, moderate_edge = _band_edges(sigma_pct)

    if abs(delta_pct) <= ideal_edge:
        text = (
            f"{actual_str}spmは期待値{expected_str}spm"
            f"±{ideal_edge:.1f}%の理想範囲内です。"
            f"適切なケイデンスを維持できています。{star_rating}"
        )
    elif delta_pct > 0 and abs(delta_pct) <= moderate_edge:
        text = (
            f"{actual_str}spmは期待値{expected_str}spmより"
            f"{abs(delta_pct):.1f}%高く、効率的なピッチ走法です。{star_rating}"
        )
    elif delta_pct > 0:
        text = (
            f"{actual_str}spmは期待値{expected_str}spmより"
            f"{abs(delta_pct):.0f}%高く、良好なケイデンスです。{star_rating}"
        )
    elif abs(delta_pct) <= moderate_edge:
        text = (
            f"{actual_str}spmは期待値{expected_str}spmより"
            f"{abs(delta_pct):.1f}%低く、やや下回っています。"
            f"ピッチをわずかに上げる余地があります。{star_rating}"
        )
    else:
        text = (
            f"{actual_str}spmは期待値{expected_str}spmより"
            f"{abs(delta_pct):.0f}%低く、大きく下回っています。"
            f"ピッチを上げる意識でケイデンスの改善を推奨します。{star_rating}"
        )

    return text


def generate_overall_text(evaluation: dict) -> str:
    """Generate overall evaluation text.

    Args:
        evaluation: Evaluation dictionary containing:
            - overall_score: float (0-5.0)
            - overall_star_rating: str (e.g., "★★★★☆")

    Returns:
        Overall evaluation text in Japanese

    Examples:
        >>> generate_overall_text({"overall_score": 4.5, "overall_star_rating": "★★★★☆"})
        '(総合評価: ★★★★☆ 4.5/5.0)'
    """
    score = evaluation["overall_score"]
    stars = evaluation["overall_star_rating"]
    return f"(総合評価: {stars} {score:.1f}/5.0)"
