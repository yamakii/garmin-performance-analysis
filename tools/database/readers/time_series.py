"""
Time series reader for second-by-second activity data.

Handles queries to time_series_metrics table with support for
statistics-only mode and SQL-based anomaly detection.
"""

import logging
from typing import Any

from tools.database.readers.base import BaseDBReader

logger = logging.getLogger(__name__)


class TimeSeriesReader(BaseDBReader):
    """Reader for time series metrics and anomaly detection."""

    def get_time_series_statistics(
        self,
        activity_id: int,
        start_time_s: int,
        end_time_s: int,
        metrics: list[str],
    ) -> dict[str, Any]:
        """Get statistics for specified metrics in time range using SQL.

        This method calculates AVG, STDDEV, MIN, MAX directly in DuckDB,
        providing significant token reduction compared to loading raw JSON.

        Args:
            activity_id: Activity ID.
            start_time_s: Start time in seconds.
            end_time_s: End time in seconds.
            metrics: List of metric column names (e.g., ['heart_rate', 'speed']).

        Returns:
            Dictionary with statistics:
            {
                "activity_id": int,
                "time_range": {"start_time_s": int, "end_time_s": int},
                "statistics": {
                    "metric_name": {
                        "avg": float,
                        "std": float,
                        "min": float,
                        "max": float
                    },
                    ...
                },
                "data_points": int
            }
        """
        try:
            with self._get_connection() as conn:
                # Build SQL for statistics calculation
                stats_selects = []
                for metric in metrics:
                    stats_selects.append(
                        f"AVG({metric}) as {metric}_avg, "
                        f"STDDEV({metric}) as {metric}_std, "
                        f"MIN({metric}) as {metric}_min, "
                        f"MAX({metric}) as {metric}_max"
                    )

                stats_sql = ", ".join(stats_selects)

                query = f"""
                SELECT
                    {stats_sql},
                    COUNT(*) as data_points
                FROM time_series_metrics
                WHERE activity_id = ?
                  AND timestamp_s >= ?
                  AND timestamp_s < ?
                """

                result = conn.execute(
                    query, [activity_id, start_time_s, end_time_s]
                ).fetchone()

                if not result or result[-1] == 0:
                    # No data found
                    return {
                        "activity_id": activity_id,
                        "time_range": {
                            "start_time_s": start_time_s,
                            "end_time_s": end_time_s,
                        },
                        "statistics": {},
                        "data_points": 0,
                    }

                # Parse result into statistics dict
                statistics = {}
                col_idx = 0
                for metric in metrics:
                    statistics[metric] = {
                        "avg": (
                            float(result[col_idx])
                            if result[col_idx] is not None
                            else 0.0
                        ),
                        "std": (
                            float(result[col_idx + 1])
                            if result[col_idx + 1] is not None
                            else 0.0
                        ),
                        "min": (
                            float(result[col_idx + 2])
                            if result[col_idx + 2] is not None
                            else 0.0
                        ),
                        "max": (
                            float(result[col_idx + 3])
                            if result[col_idx + 3] is not None
                            else 0.0
                        ),
                    }
                    col_idx += 4

                return {
                    "activity_id": activity_id,
                    "time_range": {
                        "start_time_s": start_time_s,
                        "end_time_s": end_time_s,
                    },
                    "statistics": statistics,
                    "data_points": int(result[-1]),
                }

        except Exception as e:
            return {
                "activity_id": activity_id,
                "error": f"Error querying time series statistics: {e}",
            }

    def get_time_series_raw(
        self,
        activity_id: int,
        start_time_s: int,
        end_time_s: int,
        metrics: list[str],
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Get raw time series data for specified metrics and time range.

        Use this when you need actual data points (e.g., for plotting).
        For analysis, prefer get_time_series_statistics() for token efficiency.

        Args:
            activity_id: Activity ID.
            start_time_s: Start time in seconds.
            end_time_s: End time in seconds.
            metrics: List of metric column names.
            limit: Optional limit on number of rows returned.

        Returns:
            Dictionary with raw time series:
            {
                "activity_id": int,
                "time_range": {"start_time_s": int, "end_time_s": int},
                "time_series": [
                    {"timestamp_s": int, "metric1": float, ...},
                    ...
                ]
            }
        """
        try:
            with self._get_connection() as conn:
                # Build SELECT clause
                select_cols = ["timestamp_s"] + metrics
                select_sql = ", ".join(select_cols)

                query = f"""
                SELECT {select_sql}
                FROM time_series_metrics
                WHERE activity_id = ?
                  AND timestamp_s >= ?
                  AND timestamp_s < ?
                ORDER BY timestamp_s
                """

                if limit is not None:
                    query += f" LIMIT {limit}"

                results = conn.execute(
                    query, [activity_id, start_time_s, end_time_s]
                ).fetchall()

                # Convert to list of dicts
                time_series = []
                for row in results:
                    data_point = {"timestamp_s": row[0]}
                    for i, metric in enumerate(metrics):
                        data_point[metric] = (
                            row[i + 1] if row[i + 1] is not None else None
                        )
                    time_series.append(data_point)

                return {
                    "activity_id": activity_id,
                    "time_range": {
                        "start_time_s": start_time_s,
                        "end_time_s": end_time_s,
                    },
                    "time_series": time_series,
                }

        except Exception as e:
            return {
                "activity_id": activity_id,
                "error": f"Error querying raw time series: {e}",
            }

    def detect_anomalies_sql(
        self,
        activity_id: int,
        metrics: list[str],
        z_threshold: float = 2.0,
    ) -> dict[str, Any]:
        """Detect anomalies using SQL-based z-score calculation.

        Calculates z-scores in DuckDB using window functions, providing
        efficient anomaly detection without loading full time series.

        Args:
            activity_id: Activity ID.
            metrics: List of metric column names to check for anomalies.
            z_threshold: Z-score threshold (default: 2.0).

        Returns:
            Dictionary with detected anomalies:
            {
                "activity_id": int,
                "anomalies": [
                    {
                        "timestamp_s": int,
                        "metric": str,
                        "value": float,
                        "z_score": float
                    },
                    ...
                ],
                "summary": {
                    "total_anomalies": int,
                    "by_metric": {metric: count, ...}
                }
            }
        """
        try:
            with self._get_connection() as conn:
                all_anomalies = []

                for metric in metrics:
                    # Calculate z-scores using window functions
                    query = f"""
                    WITH stats AS (
                        SELECT
                            timestamp_s,
                            {metric} as value,
                            AVG({metric}) OVER () as mean_val,
                            STDDEV({metric}) OVER () as std_val
                        FROM time_series_metrics
                        WHERE activity_id = ?
                          AND {metric} IS NOT NULL
                    )
                    SELECT
                        timestamp_s,
                        value,
                        CASE
                            WHEN std_val > 0 THEN ABS((value - mean_val) / std_val)
                            ELSE 0
                        END as z_score
                    FROM stats
                    WHERE std_val > 0
                      AND ABS((value - mean_val) / std_val) > ?
                    ORDER BY z_score DESC
                    """

                    results = conn.execute(query, [activity_id, z_threshold]).fetchall()

                    for row in results:
                        all_anomalies.append(
                            {
                                "timestamp_s": int(row[0]),
                                "metric": metric,
                                "value": float(row[1]),
                                "z_score": float(row[2]),
                            }
                        )

                # Generate summary
                by_metric: dict[str, int] = {}
                for metric in metrics:
                    count = sum(1 for a in all_anomalies if a["metric"] == metric)
                    by_metric[metric] = count

                summary = {
                    "total_anomalies": len(all_anomalies),
                    "by_metric": by_metric,
                }

                return {
                    "activity_id": activity_id,
                    "anomalies": all_anomalies,
                    "summary": summary,
                }

        except Exception as e:
            return {
                "activity_id": activity_id,
                "error": f"Error detecting anomalies: {e}",
            }
