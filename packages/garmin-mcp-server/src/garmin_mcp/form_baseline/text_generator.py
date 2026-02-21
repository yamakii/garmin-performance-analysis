"""Japanese evaluation text generation for form metrics.

This module generates natural Japanese evaluation text for GCT, VO, and VR metrics
based on the deviation from expected values.
"""


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
) -> str:
    """Generate Japanese evaluation text for a single metric.

    Asymmetric evaluation: lower-than-expected values indicate efficiency improvement
    and receive positive text, while higher-than-expected values indicate degradation.

    Args:
        metric: 'gct', 'vo', or 'vr'
        actual: Actual measured value
        expected: Expected value from baseline model
        delta_pct: Delta percentage ((actual - expected) / expected * 100)
        pace_s_per_km: Pace in seconds per km (for context)
        star_rating: Star rating string (e.g., '★★★★★')
        score: Numeric score (0-5.0)

    Returns:
        Japanese evaluation text

    Example:
        >>> generate_evaluation_text('gct', 258.0, 261.0, -1.1, 431.0, '★★★★★', 5.0)
        '258msは期待値261ms±2%の理想範囲内です。適切な接地時間を維持できています。★★★★★'
    """
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

    # Asymmetric evaluation: improvement direction (lower) is positive,
    # degradation direction (higher) is negative.
    if abs(delta_pct) <= 2:
        # Ideal (abs(delta) <= 2%)
        text = (
            f"{actual_str}{unit}は期待値{expected_str}{unit}±2%の理想範囲内です。"
            f"適切な{name}を維持できています。{star_rating}"
        )
    elif delta_pct < 0 and abs(delta_pct) <= 5:
        # Slight improvement (2% < |delta| <= 5%, lower = more efficient)
        direction = label["direction_low"]
        text = (
            f"{actual_str}{unit}は期待値{expected_str}{unit}より"
            f"{abs(delta_pct):.1f}%{direction}、効率的なフォームです。{star_rating}"
        )
    elif delta_pct < 0:
        # Large improvement (|delta| > 5%, lower = more efficient)
        direction = label["direction_low"]
        text = (
            f"{actual_str}{unit}は期待値{expected_str}{unit}より"
            f"{abs(delta_pct):.0f}%{direction}、効率面で良好です。"
            f"ただしバランスの確認を推奨します。{star_rating}"
        )
    elif abs(delta_pct) <= 5:
        # Slightly degraded (2% < delta <= 5%, higher = less efficient)
        direction = label["direction_high"]
        text = (
            f"{actual_str}{unit}は期待値{expected_str}{unit}より"
            f"{abs(delta_pct):.1f}%{direction}、やや外れています。"
            f"通常のフォームから軽度のズレが見られます。{star_rating}"
        )
    else:
        # Significantly degraded (delta > 5%, higher = less efficient)
        direction = label["direction_high"]
        text = (
            f"{actual_str}{unit}は期待値{expected_str}{unit}より"
            f"{abs(delta_pct):.0f}%{direction}、大きく外れています。"
            f"フォームの不安定さが見られます。{label['improvement_action']}を推奨します。{star_rating}"
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
