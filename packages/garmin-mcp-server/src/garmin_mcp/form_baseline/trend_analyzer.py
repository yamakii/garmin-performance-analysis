"""Form baseline trend analyzer.

Analyzes changes in form baseline model coefficients over time to detect
form improvements or deterioration.
"""

from datetime import datetime
from typing import Any

from dateutil.relativedelta import relativedelta

from garmin_mcp.database.connection import get_connection


def analyze_form_trend(
    db_path: str,
    activity_date: str,
    comparison_months_back: int = 1,
) -> dict[str, Any]:
    """Analyze form trend by comparing model coefficients with past period.

    Compares the baseline model coefficients from the current period with
    coefficients from N months ago to detect form evolution.

    Design philosophy:
        - Single activity evaluation: "deviation from expected = instability"
        - Period comparison: "change in expected = form evolution"

    Example:
        July 2025 model: GCT d=-2.83 (avg 258ms at same pace)
        Oct 2025 model: GCT d=-3.12 (avg 250ms at same pace)
        → Interpretation: "Ground contact time reduced 3% over 3 months. Form improved."

    Args:
        db_path: Path to DuckDB database
        activity_date: Activity date in YYYY-MM-DD format
        comparison_months_back: Number of months to look back (default: 1)

    Returns:
        Dictionary containing:
            - gct_improvement: bool (True if form improved)
            - vo_improvement: bool
            - vr_improvement: bool
            - gct_delta_d: float (change in GCT power coefficient)
            - vo_delta_b: float (change in VO linear coefficient)
            - vr_delta_b: float (change in VR linear coefficient)
            - current_period: tuple[str, str] (period_start, period_end)
            - past_period: tuple[str, str] | None
            - interpretation_text: str (Japanese interpretation)
            - data_available: bool (False if insufficient history)

    Raises:
        ValueError: If activity_date format is invalid

    Example:
        >>> result = analyze_form_trend(
        ...     db_path="data/database/garmin_performance.duckdb",
        ...     activity_date="2025-10-25",
        ...     comparison_months_back=1
        ... )
        >>> print(result['interpretation_text'])
        1ヶ月前と比較して接地時間が5%短縮しました。フォームが進化しています。
    """
    try:
        activity_dt = datetime.strptime(activity_date, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(
            f"Invalid activity_date format: {activity_date}. Expected YYYY-MM-DD."
        ) from e

    with get_connection(db_path) as conn:
        # Calculate target month end (last day of activity month)
        current_month_end = (
            activity_dt.replace(day=1) + relativedelta(months=1) - relativedelta(days=1)
        ).strftime("%Y-%m-%d")

        # Find baseline period with period_end = current_month_end
        current_baseline = conn.execute(
            """
            SELECT
                period_start, period_end,
                metric, coef_d, coef_b
            FROM form_baseline_history
            WHERE period_end = ?
        """,
            [current_month_end],
        ).fetchall()

        if not current_baseline:
            return {
                "data_available": False,
                "gct_improvement": None,
                "vo_improvement": None,
                "vr_improvement": None,
                "gct_delta_d": None,
                "vo_delta_b": None,
                "vr_delta_b": None,
                "current_period": None,
                "past_period": None,
                "interpretation_text": "データ不足のため、フォームトレンド分析を実行できません。",
            }

        # Extract coefficients from current period
        current_gct_d = None
        current_vo_b = None
        current_vr_b = None
        current_period_start = None
        current_period_end = None

        for row in current_baseline:
            if not current_period_start:
                current_period_start = row[0]
                current_period_end = row[1]

            metric = row[2]
            if metric == "gct":
                current_gct_d = row[3]  # coef_d for power model
            elif metric == "vo":
                current_vo_b = row[4]  # coef_b for linear model
            elif metric == "vr":
                current_vr_b = row[4]  # coef_b for linear model

        # Calculate past month end (N months before activity month)
        past_dt = activity_dt - relativedelta(months=comparison_months_back)
        past_month_end = (
            past_dt.replace(day=1) + relativedelta(months=1) - relativedelta(days=1)
        ).strftime("%Y-%m-%d")

        # Find baseline period with period_end = past_month_end
        past_baseline = conn.execute(
            """
            SELECT
                period_start, period_end,
                metric, coef_d, coef_b
            FROM form_baseline_history
            WHERE period_end = ?
        """,
            [past_month_end],
        ).fetchall()

        if not past_baseline:
            return {
                "data_available": False,
                "gct_improvement": None,
                "vo_improvement": None,
                "vr_improvement": None,
                "gct_delta_d": None,
                "vo_delta_b": None,
                "vr_delta_b": None,
                "current_period": (current_period_start, current_period_end),
                "past_period": None,
                "interpretation_text": f"{comparison_months_back}ヶ月前のデータがないため、フォームトレンド分析を実行できません。",
            }

        # Extract coefficients from past period
        past_gct_d = None
        past_vo_b = None
        past_vr_b = None
        past_period_start = None
        past_period_end = None

        for row in past_baseline:
            if not past_period_start:
                past_period_start = row[0]
                past_period_end = row[1]

            metric = row[2]
            if metric == "gct":
                past_gct_d = row[3]
            elif metric == "vo":
                past_vo_b = row[4]
            elif metric == "vr":
                past_vr_b = row[4]

        # Calculate deltas and improvement flags
        gct_delta_d = (
            current_gct_d - past_gct_d if (current_gct_d and past_gct_d) else None
        )
        vo_delta_b = current_vo_b - past_vo_b if (current_vo_b and past_vo_b) else None
        vr_delta_b = current_vr_b - past_vr_b if (current_vr_b and past_vr_b) else None

        # Improvement thresholds (from planning.md)
        # GCT: d < -0.1 (more negative slope = faster at same GCT = improvement)
        # VO: b < -0.05 (less VO at same speed = improvement)
        # VR: b < -0.1 (less VR at same speed = improvement)
        gct_improvement = gct_delta_d < -0.1 if gct_delta_d is not None else None
        vo_improvement = vo_delta_b < -0.05 if vo_delta_b is not None else None
        vr_improvement = vr_delta_b < -0.1 if vr_delta_b is not None else None

        # Generate Japanese interpretation
        interpretation = _generate_trend_interpretation(
            gct_improvement=gct_improvement,
            vo_improvement=vo_improvement,
            vr_improvement=vr_improvement,
            gct_delta_d=gct_delta_d,
            vo_delta_b=vo_delta_b,
            vr_delta_b=vr_delta_b,
            comparison_months=comparison_months_back,
        )

        return {
            "data_available": True,
            "gct_improvement": gct_improvement,
            "vo_improvement": vo_improvement,
            "vr_improvement": vr_improvement,
            "gct_delta_d": gct_delta_d,
            "vo_delta_b": vo_delta_b,
            "vr_delta_b": vr_delta_b,
            "current_period": (str(current_period_start), str(current_period_end)),
            "past_period": (str(past_period_start), str(past_period_end)),
            "interpretation_text": interpretation,
        }


def _generate_trend_interpretation(
    gct_improvement: bool | None,
    vo_improvement: bool | None,
    vr_improvement: bool | None,
    gct_delta_d: float | None,
    vo_delta_b: float | None,
    vr_delta_b: float | None,
    comparison_months: int,
) -> str:
    """Generate Japanese interpretation text from trend analysis results.

    Args:
        gct_improvement: True if GCT improved
        vo_improvement: True if VO improved
        vr_improvement: True if VR improved
        gct_delta_d: Change in GCT power coefficient
        vo_delta_b: Change in VO linear coefficient
        vr_delta_b: Change in VR linear coefficient
        comparison_months: Number of months compared

    Returns:
        Japanese interpretation text

    Example outputs:
        - "3ヶ月前と比較して接地時間が5%短縮しました。フォームが進化しています。"
        - "フォーム指標は3ヶ月前とほぼ同水準を維持しています。"
        - "接地時間と上下動が改善し、フォームが進化しています。"
    """
    if gct_improvement is None and vo_improvement is None and vr_improvement is None:
        return f"{comparison_months}ヶ月前のデータがないため、フォームトレンド分析を実行できません。"

    improvements = []
    deteriorations = []

    # Check each metric
    if gct_improvement is True:
        improvements.append("接地時間")
    elif gct_improvement is False and gct_delta_d and gct_delta_d > 0.1:
        deteriorations.append("接地時間")

    if vo_improvement is True:
        improvements.append("上下動")
    elif vo_improvement is False and vo_delta_b and vo_delta_b > 0.05:
        deteriorations.append("上下動")

    if vr_improvement is True:
        improvements.append("上下動比")
    elif vr_improvement is False and vr_delta_b and vr_delta_b > 0.1:
        deteriorations.append("上下動比")

    # Generate interpretation based on changes
    if len(improvements) >= 2:
        return f"{comparison_months}ヶ月前と比較して{' と '.join(improvements)}が改善し、フォームが進化しています。"
    elif len(improvements) == 1:
        return f"{comparison_months}ヶ月前と比較して{improvements[0]}が改善しました。フォームが進化しています。"
    elif len(deteriorations) >= 2:
        return f"{comparison_months}ヶ月前と比較して{' と '.join(deteriorations)}が悪化しています。フォームの見直しが必要です。"
    elif len(deteriorations) == 1:
        return (
            f"{comparison_months}ヶ月前と比較して{deteriorations[0]}が悪化しています。"
        )
    else:
        return f"フォーム指標は{comparison_months}ヶ月前とほぼ同水準を維持しています。"
