"""Handler for physiology tools."""

from typing import Any

from mcp.types import TextContent

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.handlers.base import format_json_response


class PhysiologyHandler:
    """Handles physiology-related tool calls."""

    _tool_names: set[str] = {
        "get_form_efficiency_summary",
        "get_form_evaluations",
        "get_form_baseline_trend",
        "get_hr_efficiency_analysis",
        "get_heart_rate_zones_detail",
        "get_vo2_max_data",
        "get_lactate_threshold_data",
    }

    def __init__(self, db_reader: GarminDBReader) -> None:
        self._db_reader = db_reader

    def handles(self, name: str) -> bool:
        return name in self._tool_names

    async def handle(self, name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if name == "get_form_baseline_trend":
            return await self._get_form_baseline_trend(arguments)

        activity_id = arguments["activity_id"]

        if name == "get_form_efficiency_summary":
            result = self._db_reader.get_form_efficiency_summary(activity_id)  # type: ignore[assignment]
        elif name == "get_form_evaluations":
            result = self._db_reader.get_form_evaluations(activity_id)  # type: ignore[assignment]
        elif name == "get_hr_efficiency_analysis":
            result = self._db_reader.get_hr_efficiency_analysis(activity_id)  # type: ignore[assignment]
        elif name == "get_heart_rate_zones_detail":
            result = self._db_reader.get_heart_rate_zones_detail(activity_id)  # type: ignore[assignment]
        elif name == "get_vo2_max_data":
            result = self._db_reader.get_vo2_max_data(activity_id)  # type: ignore[assignment]
        elif name == "get_lactate_threshold_data":
            result = self._db_reader.get_lactate_threshold_data(activity_id)  # type: ignore[assignment]
        else:
            raise ValueError(f"Unknown tool: {name}")

        return [TextContent(type="text", text=format_json_response(result))]

    async def _get_form_baseline_trend(
        self, arguments: dict[str, Any]
    ) -> list[TextContent]:
        from datetime import datetime

        from dateutil.relativedelta import relativedelta

        from garmin_mcp.database.connection import get_connection

        activity_id = arguments["activity_id"]
        activity_date = arguments["activity_date"]
        user_id = arguments.get("user_id", "default")
        condition_group = arguments.get("condition_group", "flat_road")

        try:
            with get_connection(self._db_reader.db_path) as conn:
                # Get current period baseline
                current_baselines = conn.execute(
                    """
                    SELECT metric, coef_d, coef_b, period_start, period_end
                    FROM form_baseline_history
                    WHERE user_id = ?
                      AND condition_group = ?
                      AND period_start <= ?
                      AND period_end >= ?
                    ORDER BY metric
                    """,
                    [user_id, condition_group, activity_date, activity_date],
                ).fetchall()

                if not current_baselines:
                    result: dict[str, Any] = {
                        "success": False,
                        "error": f"No baseline found for {activity_date}",
                    }
                    return [
                        TextContent(
                            type="text",
                            text=format_json_response(result),
                        )
                    ]

                # Calculate 1 month before the current period start
                current_period_start = datetime.strptime(
                    str(current_baselines[0][3]), "%Y-%m-%d"
                )
                one_month_before = current_period_start - relativedelta(months=1)
                target_date = one_month_before.strftime("%Y-%m-%d")

                # Get previous period baseline (1 month before)
                previous_baselines = conn.execute(
                    """
                    SELECT metric, coef_d, coef_b, period_start, period_end
                    FROM form_baseline_history
                    WHERE user_id = ?
                      AND condition_group = ?
                      AND period_start <= ?
                      AND period_end >= ?
                    ORDER BY metric
                    """,
                    [user_id, condition_group, target_date, target_date],
                ).fetchall()

            if not previous_baselines:
                result = {
                    "success": False,
                    "error": f"No previous baseline found for comparison (target: {target_date})",
                }
                return [
                    TextContent(
                        type="text",
                        text=format_json_response(result),
                    )
                ]

            # Build result with current and previous coefficients
            metrics_data: dict[str, Any] = {}
            for curr in current_baselines:
                metric = curr[0]
                metrics_data[metric] = {
                    "current": {
                        "coef_d": curr[1],
                        "coef_b": curr[2],
                        "period": f"{curr[3]} to {curr[4]}",
                    }
                }

            for prev in previous_baselines:
                metric = prev[0]
                if metric in metrics_data:
                    metrics_data[metric]["previous"] = {
                        "coef_d": prev[1],
                        "coef_b": prev[2],
                        "period": f"{prev[3]} to {prev[4]}",
                    }
                    # Calculate deltas
                    if (
                        metrics_data[metric]["current"]["coef_d"] is not None
                        and prev[1] is not None
                    ):
                        metrics_data[metric]["delta_d"] = (
                            metrics_data[metric]["current"]["coef_d"] - prev[1]
                        )
                    if (
                        metrics_data[metric]["current"]["coef_b"] is not None
                        and prev[2] is not None
                    ):
                        metrics_data[metric]["delta_b"] = (
                            metrics_data[metric]["current"]["coef_b"] - prev[2]
                        )

            result = {
                "success": True,
                "activity_id": activity_id,
                "activity_date": activity_date,
                "metrics": metrics_data,
            }

            return [TextContent(type="text", text=format_json_response(result))]

        except Exception as e:
            result = {"success": False, "error": str(e)}
            return [TextContent(type="text", text=format_json_response(result))]
