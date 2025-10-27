"""Japanese evaluation text generation for form metrics.

This module generates natural Japanese evaluation text for GCT, VO, and VR metrics
based on the deviation from expected values.
"""

from typing import Literal


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
    metric: Literal["gct", "vo", "vr"],
    actual: float,
    expected: float,
    delta_pct: float,
    pace_s_per_km: float,
    star_rating: str,
    score: float,
) -> str:
    """Generate Japanese evaluation text for a form metric.

    Args:
        metric: Metric type ('gct', 'vo', 'vr')
        actual: Actual measured value
        expected: Expected value based on pace
        delta_pct: Percentage deviation from expected
        pace_s_per_km: Pace in seconds per kilometer
        star_rating: Star rating string (e.g., "★★★★★")
        score: Numeric score (0-5.0)

    Returns:
        Natural Japanese evaluation text

    Examples:
        >>> generate_evaluation_text("gct", 258, 261, -1.3, 431, "★★★★★", 5.0)
        '258msは期待値261msより1.3%優秀で、非常に効率的な接地時間です。...'
    """
    pace_str = _format_pace(pace_s_per_km)

    # Metric-specific labels
    metric_labels = {
        "gct": {
            "unit": "ms",
            "name": "接地時間",
            "better": "短縮",
            "worse": "長め",
            "improvement_action": "接地時間の短縮トレーニング",
        },
        "vo": {
            "unit": "cm",
            "name": "上下動",
            "better": "低減",
            "worse": "高め",
            "improvement_action": "上下動の抑制トレーニング",
        },
        "vr": {
            "unit": "%",
            "name": "上下動比",
            "better": "低減",
            "worse": "高め",
            "improvement_action": "上下動比の改善トレーニング",
        },
    }

    label = metric_labels[metric]
    unit = label["unit"]
    name = label["name"]

    # Format values based on metric type
    if metric == "gct":
        actual_str = f"{actual:.0f}"
        expected_str = f"{expected:.0f}"
    else:
        actual_str = f"{actual:.1f}"
        expected_str = f"{expected:.1f}"

    # Generate evaluation text based on delta_pct thresholds
    if delta_pct < -5:
        # Excellent (delta < -5%)
        text = (
            f"{actual_str}{unit}は期待値{expected_str}{unit}より"
            f"{abs(delta_pct):.1f}%優秀で、非常に効率的な{name}です。"
            f"このペース（{pace_str}/km）において理想的なフォームを実現しています。{star_rating}"
        )
    elif delta_pct < -2:
        # Good (-5% < delta < -2%)
        text = (
            f"{actual_str}{unit}は期待値{expected_str}{unit}より"
            f"{abs(delta_pct):.1f}%優秀です。このペースでの標準的な"
            f"ランナーより効率的な走りができています。{star_rating}"
        )
    elif abs(delta_pct) <= 2:
        # Ideal (abs(delta) <= 2%)
        text = (
            f"{actual_str}{unit}は期待値{expected_str}{unit}±2%の理想範囲内です。"
            f"適切な{name}を維持できています。{star_rating}"
        )
    elif delta_pct <= 5:
        # Slightly suboptimal (2% < delta <= 5%)
        text = (
            f"{actual_str}{unit}は期待値{expected_str}{unit}より"
            f"{delta_pct:.1f}%{label['worse']}です。軽度の改善余地が"
            f"ありますが、許容範囲内です。{star_rating}"
        )
    else:
        # Needs improvement (delta > 5%)
        text = (
            f"{actual_str}{unit}は期待値{expected_str}{unit}より"
            f"{delta_pct:.0f}%{label['worse']}く、改善の余地があります。"
            f"{label['improvement_action']}を推奨します。{star_rating}"
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
