"""Pre-fetch a shared trend CONTEXT bundle for the trend-narration workflow.

Queries DuckDB once for a period ``[period_start, period_end]`` and folds every
longitudinal trend reader (load / metric / fitness-curve / recovery /
durability / ACWR / heat-adjusted) plus the deterministic derivations into a
single JSON bundle keyed by period. The trend-narration LLM consumes this
bundle and only writes prose — all accuracy-sensitive numbers (period deltas,
build streaks, cross-signal fusion flags) are computed here (Issue #790).

Usage:
    uv run python -m garmin_mcp.scripts.prefetch_trend_context \
        --period-start 2026-06-15 --period-end 2026-06-21 --granularity week

Output (JSON to stdout, one line):
    {
      "period_start": "2026-06-15",
      "period_end": "2026-06-21",
      "granularity": "week",
      "user_id": "default",
      "activity_ids": [123, 124],
      "headline_metrics": {"load_delta_pct": ..., "build_weeks": ...,
                            "fusion_flags": {...}},
      "fusion_flags": {...},
      "load_trend": {...},
      "metric_trends": {"pace": {...}, "heart_rate": {...}},
      "fitness_curve": {...},
      "recovery_trend": {...} | null,
      "recovery_trend_note": null | "<why recovery_trend is null>",
      "durability_trend": {...},
      "acwr": {...},
      "heat_adjusted_trend": {...}
    }

All bundle keys are additive (Issue #235): each trend reader is called
independently and any per-reader failure yields ``null`` for that key rather
than aborting the whole bundle. On a fatal error (bad dates) the bundle is
``{"error": "..."}`` and the CLI exits 1.

Weekly granularity is statistically honest (Issue #813): a single week's N
cannot support in-week regressions, so at ``granularity == "week"``:

- ``metric_trends[*]`` are descriptive (median + previous-week baseline +
  ``delta_pct``; ``mode="descriptive"``, no ``slope`` / ``p_value`` / ``trend``).
- ``durability_trend`` / ``heat_adjusted_trend`` are fit over fixed trailing
  windows (8 / 12 weeks) and carry ``in_period_activity_ids`` so the narration
  can position this week's values on the trailing trend.
- ``fitness_curve`` is pinned to a 90-day window (for both granularities).

The ``month`` path keeps the original in-period regression behavior.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from datetime import date, datetime, timedelta
from functools import partial
from typing import Any

from garmin_mcp.analysis.derivations import compute_trend_headline_metrics
from garmin_mcp.database.connection import get_connection, get_db_path

# Metrics folded into ``metric_trends`` (per the monthly-granularity table:
# analyze_metric_trend takes the [period_start, period_end] window directly).
_METRIC_TREND_METRICS = ("pace", "heart_rate")

# Trailing window length (weeks) for the RHR/HRV recovery trend. get_recovery_trend
# is anchored to now() with no end_date param, so it only represents a period
# whose period_end falls inside this trailing window (see monthly table, #790).
_RECOVERY_TREND_WEEKS = 8

# Statistically-honest weekly windowing (Issue #813). At week granularity the
# in-week N cannot support regressions, so metric trends become descriptive
# (previous-week baseline) and the durability / heat-hinge fits run over fixed
# trailing windows large enough to have real N and temperature spread. The
# fitness curve is a 90-day rolling-max metric by design and is pinned to 90d
# for both granularities (a 7-day window makes an easy week look like collapse).
_FITNESS_CURVE_WINDOW_DAYS = 90
_DURABILITY_TREND_WEEKS = 8
_HEAT_FIT_WEEKS = 12


def _safe[T](fn: Callable[[], T]) -> T | None:
    """Call ``fn`` and return its result, or ``None`` on any exception.

    Keeps a single failing trend reader from aborting the whole bundle
    (per-reader null-on-error; additive keys, Issue #235).
    """
    try:
        return fn()
    except Exception:
        return None


def _resolve_activity_ids(conn: Any, period_start: str, period_end: str) -> list[int]:
    """Return activity IDs whose ``activity_date`` is within the period.

    Inclusive on both bounds, ordered chronologically (date then id) for
    deterministic output.
    """
    rows = conn.execute(
        """
        SELECT activity_id
        FROM activities
        WHERE activity_date BETWEEN ? AND ?
        ORDER BY activity_date ASC, activity_id ASC
        """,
        [period_start, period_end],
    ).fetchall()
    return [int(row[0]) for row in rows]


def _recovery_window_covers(period_end: date, weeks: int) -> bool:
    """Whether the trailing ``weeks``-week window ending today covers period_end.

    ``get_recovery_trend`` reads ``[today - weeks, today]`` (anchored on now()),
    so it only describes a period whose ``period_end`` lies in that window.
    """
    today = date.today()
    window_start = today - timedelta(weeks=weeks)
    return window_start <= period_end <= today


def prefetch_trend_context(
    period_start: str,
    period_end: str,
    granularity: str = "week",
    user_id: str = "default",
) -> dict[str, Any]:
    """Fetch a single trend CONTEXT bundle for ``[period_start, period_end]``.

    Args:
        period_start: Inclusive lower bound (``YYYY-MM-DD``).
        period_end: Inclusive upper bound (``YYYY-MM-DD``).
        granularity: ``"week"`` or ``"month"``. Only affects recovery-trend
            windowing (get_recovery_trend has no end_date param; a month whose
            period_end is outside the trailing recovery window yields
            ``recovery_trend=None`` + a ``recovery_trend_note``).
        user_id: Athlete profile key (defaults to ``"default"``).

    Returns:
        A JSON-serializable bundle (see module docstring). ``{"error": "..."}``
        on a fatal error (e.g. unparseable dates).
    """
    try:
        start_d = datetime.strptime(period_start, "%Y-%m-%d").date()
        end_d = datetime.strptime(period_end, "%Y-%m-%d").date()
    except ValueError as exc:
        return {"error": f"invalid period bounds: {exc}"}
    if end_d < start_d:
        return {
            "error": f"period_end {period_end} precedes period_start {period_start}"
        }

    is_week = granularity == "week"

    db_path = get_db_path()
    db_path_str = str(db_path)

    # Weekly windowing bounds (Issue #813): the previous week (for the
    # descriptive metric baseline) and the trailing heat-fit window.
    prev_start = str(start_d - timedelta(days=7))
    prev_end = str(start_d - timedelta(days=1))
    heat_start = str(end_d - timedelta(days=_HEAT_FIT_WEEKS * 7 - 1))
    durability_start = str(end_d - timedelta(days=_DURABILITY_TREND_WEEKS * 7 - 1))

    # Single read txn: resolve the in-range activity IDs (and, weekly, the
    # previous-week and trailing heat-window IDs) once.
    prev_activity_ids: list[int] = []
    heat_activity_ids: list[int] = []
    with get_connection(db_path) as conn:
        activity_ids = _resolve_activity_ids(conn, period_start, period_end)
        if is_week:
            prev_activity_ids = _resolve_activity_ids(conn, prev_start, prev_end)
            heat_activity_ids = _resolve_activity_ids(conn, heat_start, period_end)

    # Number of trailing weekly buckets that fully cover the window (plus one so
    # the prior week is available for a period-over-period delta).
    window_days = (end_d - start_d).days + 1
    lookback_weeks = (window_days + 6) // 7 + 1

    # Build a single reader (facade) that fans out to every specialized reader.
    from garmin_mcp.database.db_reader import GarminDBReader
    from garmin_mcp.rag.queries.trends import PerformanceTrendAnalyzer

    reader = GarminDBReader(db_path_str)
    trend_analyzer = PerformanceTrendAnalyzer(db_path_str)

    load_trend = _safe(
        lambda: reader.get_load_trend(lookback_weeks, end_date=period_end)
    )
    acwr = _safe(lambda: reader.get_acwr(end_date=period_end))

    # Fitness curve is a 90-day rolling-max metric by design; pin the window so a
    # single easy week does not read as a fitness collapse (Issue #813).
    fitness_curve = _safe(
        lambda: reader.fitness_curve.get_objective_fitness_curve(
            window_days=_FITNESS_CURVE_WINDOW_DAYS
        )
    )

    if is_week:
        # Durability: fit the decoupling trend over a trailing 8-week window
        # (N ~= 8-16 long runs) and mark this week's qualifying runs so the
        # narration can position them on that trailing trend (Issue #813).
        durability_trend = _safe(
            lambda: reader.get_durability_trend(durability_start, period_end)
        )
        if isinstance(durability_trend, dict):
            period_id_set = set(activity_ids)
            durability_trend["window"] = {
                "start": durability_start,
                "end": period_end,
                "weeks": _DURABILITY_TREND_WEEKS,
            }
            durability_trend["in_period_activity_ids"] = [
                a["activity_id"]
                for a in durability_trend.get("activities", [])
                if a.get("activity_id") in period_id_set
            ]

        # Heat hinge: fit over a trailing 12-week window so N >= 10 and the
        # temperature spread can actually identify a hinge; carry this week's
        # runs so the narration references their heat_cost points (Issue #813).
        heat_adjusted_trend = _safe(
            lambda: reader.get_heat_adjusted_trend(
                heat_activity_ids, heat_start, period_end
            )
        )
        if isinstance(heat_adjusted_trend, dict):
            heat_adjusted_trend["in_period_activity_ids"] = list(activity_ids)
    else:
        durability_trend = _safe(
            lambda: reader.get_durability_trend(period_start, period_end)
        )
        heat_adjusted_trend = _safe(
            lambda: reader.get_heat_adjusted_trend(
                activity_ids, period_start, period_end
            )
        )

    metric_trends: dict[str, Any] = {}
    for metric in _METRIC_TREND_METRICS:
        if is_week:
            # Descriptive summary vs the previous week; no within-week regression
            # (N too small, confounded by workout-type mix) (Issue #813).
            metric_trends[metric] = _safe(
                partial(
                    trend_analyzer.summarize_metric_period,
                    metric,
                    activity_ids,
                    prev_activity_ids,
                )
            )
        else:
            metric_trends[metric] = _safe(
                partial(
                    trend_analyzer.analyze_metric_trend,
                    metric,
                    period_start,
                    period_end,
                    activity_ids,
                )
            )

    # Recovery trend is anchored to now() (no end_date). Only include it when the
    # trailing window covers period_end; otherwise null + an explanatory note.
    recovery_trend: dict[str, Any] | None = None
    recovery_trend_note: str | None = None
    if _recovery_window_covers(end_d, _RECOVERY_TREND_WEEKS):
        recovery_trend = _safe(lambda: reader.get_recovery_trend(_RECOVERY_TREND_WEEKS))
    else:
        recovery_trend_note = (
            f"period_end {period_end} is outside the trailing "
            f"{_RECOVERY_TREND_WEEKS}-week recovery window anchored at today; "
            "get_recovery_trend has no end_date param (follow-up)."
        )

    bundle: dict[str, Any] = {
        "period_start": period_start,
        "period_end": period_end,
        "granularity": granularity,
        "user_id": user_id,
        "activity_ids": activity_ids,
        "load_trend": load_trend,
        "metric_trends": metric_trends,
        "fitness_curve": fitness_curve,
        "recovery_trend": recovery_trend,
        "recovery_trend_note": recovery_trend_note,
        "durability_trend": durability_trend,
        "acwr": acwr,
        "heat_adjusted_trend": heat_adjusted_trend,
    }

    # Deterministic fold: headline metrics + top-level fusion flags (Issue #790).
    headline_metrics = compute_trend_headline_metrics(bundle)
    bundle["headline_metrics"] = headline_metrics
    bundle["fusion_flags"] = headline_metrics["fusion_flags"]

    return bundle


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pre-fetch a shared trend CONTEXT bundle for a period."
    )
    parser.add_argument("--period-start", required=True, help="YYYY-MM-DD (inclusive)")
    parser.add_argument("--period-end", required=True, help="YYYY-MM-DD (inclusive)")
    parser.add_argument(
        "--granularity",
        default="week",
        choices=["week", "month"],
        help="Period granularity (default: week).",
    )
    parser.add_argument("--user-id", default="default", help="Athlete profile key.")
    args = parser.parse_args()

    result = prefetch_trend_context(
        args.period_start, args.period_end, args.granularity, args.user_id
    )
    print(json.dumps(result, ensure_ascii=False))

    return 1 if "error" in result else 0


if __name__ == "__main__":
    sys.exit(main())
