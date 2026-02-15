"""
Utility reader for DuckDB.

Handles profiling and histogram operations for data exploration.
"""

import logging
from typing import Any

from garmin_mcp.database.readers.base import BaseDBReader

logger = logging.getLogger(__name__)


class UtilityReader(BaseDBReader):
    """Reader for utility operations (profiling, histograms)."""

    def profile_table_or_query(
        self,
        table_or_query: str,
        date_range: tuple[str, str] | None = None,
    ) -> dict[str, Any]:
        """Get summary statistics for table or query without raw data.

        Args:
            table_or_query: Table name (e.g., 'splits') or SQL query
            date_range: Optional date filter (start_date, end_date) in YYYY-MM-DD format

        Returns:
            Dict with row_count, date_range, and columns statistics.

        Context Cost: ~500-1000 bytes
        """
        try:
            with self._get_connection() as conn:
                # Detect if input is table name or SQL query
                is_query = "SELECT" in table_or_query.upper()

                # Build base query
                if is_query:
                    base_query = f"({table_or_query}) AS subquery"
                else:
                    base_query = table_or_query

                # Apply date_range filter if provided
                if date_range:
                    start_date, end_date = date_range
                    if is_query:
                        base_query = (
                            f"(SELECT * FROM ({table_or_query}) AS inner_query "
                            f"WHERE date BETWEEN '{start_date}' AND '{end_date}') AS subquery"
                        )
                    else:
                        base_query = (
                            f"(SELECT * FROM {table_or_query} "
                            f"WHERE date BETWEEN '{start_date}' AND '{end_date}') AS subquery"
                        )

                # Get row count
                count_query = f"SELECT COUNT(*) FROM {base_query}"
                count_result = conn.execute(count_query).fetchone()
                row_count = count_result[0] if count_result else 0

                # If empty, return early
                if row_count == 0:
                    return {"row_count": 0, "date_range": [], "columns": {}}

                # Get date range (only if date column exists)
                date_range_result = []
                try:
                    date_query = f"SELECT MIN(date), MAX(date) FROM {base_query}"
                    date_result = conn.execute(date_query).fetchone()
                    date_range_result = (
                        [str(date_result[0]), str(date_result[1])]
                        if date_result and date_result[0] and date_result[1]
                        else []
                    )
                except Exception:
                    # date column doesn't exist, skip it
                    pass

                # Get column names (excluding date, activity_id which are metadata)
                sample_query = f"SELECT * FROM {base_query} LIMIT 1"
                conn.execute(sample_query)
                all_columns = [desc[0] for desc in conn.description]

                # Filter out metadata columns
                skip_columns = {"date", "activity_id", "split_number"}
                columns_to_profile = [
                    col for col in all_columns if col not in skip_columns
                ]

                # Limit to first 10 columns if too many (output size control)
                if len(columns_to_profile) > 10:
                    columns_to_profile = columns_to_profile[:10]
                    logger.warning(
                        f"Too many columns ({len(all_columns)}), profiling first 10 only"
                    )

                # Build statistics query for each column
                columns_stats: dict[str, Any] = {}
                for col in columns_to_profile:
                    stats_query = f"""
                        SELECT
                            MIN({col}) AS min_val,
                            MAX({col}) AS max_val,
                            AVG({col}) AS mean_val,
                            MEDIAN({col}) AS median_val,
                            STDDEV({col}) AS std_val,
                            SUM(CASE WHEN {col} IS NULL THEN 1 ELSE 0 END)::FLOAT / COUNT(*)::FLOAT AS null_rate,
                            COUNT(DISTINCT {col}) AS distinct_count
                        FROM {base_query}
                    """

                    try:
                        stats_result = conn.execute(stats_query).fetchone()
                        if stats_result:
                            columns_stats[col] = {
                                "min": stats_result[0],
                                "max": stats_result[1],
                                "mean": (
                                    round(stats_result[2], 2)
                                    if stats_result[2] is not None
                                    else None
                                ),
                                "median": (
                                    round(stats_result[3], 2)
                                    if stats_result[3] is not None
                                    else None
                                ),
                                "std": (
                                    round(stats_result[4], 2)
                                    if stats_result[4] is not None
                                    else None
                                ),
                                "null_rate": (
                                    round(stats_result[5], 4)
                                    if stats_result[5] is not None
                                    else 0.0
                                ),
                                "distinct_count": stats_result[6],
                            }
                    except Exception as e:
                        # Skip columns that can't be profiled (e.g., non-numeric)
                        logger.debug(f"Skipping column {col}: {e}")
                        continue

                return {
                    "row_count": row_count,
                    "date_range": date_range_result,
                    "columns": columns_stats,
                }

        except Exception as e:
            logger.error(f"Error profiling table/query: {e}")
            raise

    def histogram_column(
        self,
        table_or_query: str,
        column: str,
        bins: int = 20,
        date_range: tuple[str, str] | None = None,
    ) -> dict[str, Any]:
        """Get histogram distribution for a column (aggregated, no raw data).

        Args:
            table_or_query: Table name or SQL query
            column: Column name to analyze
            bins: Number of histogram bins (default 20)
            date_range: Optional date filter (start_date, end_date) in YYYY-MM-DD format

        Returns:
            Dict with column, bins, total_count, and statistics.

        Context Cost: ~1KB (20 bins x 50 bytes)
        """
        try:
            with self._get_connection() as conn:
                # Detect if input is table name or SQL query
                is_query = "SELECT" in table_or_query.upper()

                # Build base query
                if is_query:
                    base_query = f"({table_or_query}) AS subquery"
                else:
                    base_query = table_or_query

                # Apply date_range filter if provided
                if date_range:
                    start_date, end_date = date_range
                    if is_query:
                        base_query = (
                            f"(SELECT * FROM ({table_or_query}) AS inner_query "
                            f"WHERE date BETWEEN '{start_date}' AND '{end_date}') AS subquery"
                        )
                    else:
                        base_query = (
                            f"(SELECT * FROM {table_or_query} "
                            f"WHERE date BETWEEN '{start_date}' AND '{end_date}') AS subquery"
                        )

                # Get total count (excluding NULLs)
                count_query = (
                    f"SELECT COUNT(*) FROM {base_query} WHERE {column} IS NOT NULL"
                )
                count_result = conn.execute(count_query).fetchone()
                total_count = count_result[0] if count_result else 0

                # If empty, return early
                if total_count == 0:
                    return {
                        "column": column,
                        "bins": [],
                        "total_count": 0,
                        "statistics": {},
                    }

                # Get min/max for binning
                minmax_query = (
                    f"SELECT MIN({column}), MAX({column}) FROM {base_query} "
                    f"WHERE {column} IS NOT NULL"
                )
                minmax_result = conn.execute(minmax_query).fetchone()
                if not minmax_result or minmax_result[0] is None:
                    return {
                        "column": column,
                        "bins": [],
                        "total_count": 0,
                        "statistics": {},
                    }

                min_val = minmax_result[0]
                max_val = minmax_result[1]

                # Handle single value case
                if min_val == max_val:
                    return {
                        "column": column,
                        "bins": [
                            {"min": min_val, "max": max_val, "count": total_count}
                        ],
                        "total_count": total_count,
                        "statistics": {
                            "min": min_val,
                            "max": max_val,
                            "mean": min_val,
                            "median": min_val,
                        },
                    }

                # Calculate bin width and use FLOOR to assign buckets manually
                bin_width = (max_val - min_val) / bins
                histogram_query = f"""
                    SELECT
                        FLOOR(({column} - {min_val}) / {bin_width}) AS bucket,
                        COUNT(*) as count,
                        MIN({column}) as bin_min,
                        MAX({column}) as bin_max
                    FROM {base_query}
                    WHERE {column} IS NOT NULL
                    GROUP BY bucket
                    ORDER BY bucket
                """

                histogram_result = conn.execute(histogram_query).fetchall()

                # Build bins list
                bins_list = []
                for row in histogram_result:
                    bucket_num, count, bin_min, bin_max = row
                    bins_list.append(
                        {
                            "min": round(bin_min, 2),
                            "max": round(bin_max, 2),
                            "count": count,
                        }
                    )

                # Get statistics
                stats_query = f"""
                    SELECT
                        MIN({column}),
                        MAX({column}),
                        AVG({column}),
                        MEDIAN({column})
                    FROM {base_query}
                    WHERE {column} IS NOT NULL
                """
                stats_result = conn.execute(stats_query).fetchone()

                statistics = {}
                if stats_result:
                    statistics = {
                        "min": (
                            round(stats_result[0], 2)
                            if stats_result[0] is not None
                            else None
                        ),
                        "max": (
                            round(stats_result[1], 2)
                            if stats_result[1] is not None
                            else None
                        ),
                        "mean": (
                            round(stats_result[2], 2)
                            if stats_result[2] is not None
                            else None
                        ),
                        "median": (
                            round(stats_result[3], 2)
                            if stats_result[3] is not None
                            else None
                        ),
                    }

                return {
                    "column": column,
                    "bins": bins_list,
                    "total_count": total_count,
                    "statistics": statistics,
                }

        except Exception as e:
            logger.error(f"Error generating histogram: {e}")
            raise
