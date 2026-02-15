"""
DuckDB Reader for Garmin Performance Data

Provides unified read-only access to DuckDB for querying performance data.
This class maintains backward compatibility by delegating to specialized readers.
"""

from pathlib import Path
from typing import Any, Literal

from garmin_mcp.database.readers import (
    AggregateReader,
    ExportReader,
    FormReader,
    MetadataReader,
    PerformanceReader,
    PhysiologyReader,
    SplitsReader,
    TimeSeriesReader,
    UtilityReader,
)


class GarminDBReader:
    """
    Unified DuckDB reader with backward compatibility.

    This class delegates to specialized reader classes:
    - MetadataReader: Activity date/ID queries
    - SplitsReader: Splits data queries
    - AggregateReader: Pre-computed performance metrics
    - TimeSeriesReader: Time series data and anomaly detection
    - ExportReader: Query result export
    """

    def __init__(self, db_path: str | None = None):
        """Initialize DuckDB reader with database path.

        Args:
            db_path: Optional path to DuckDB database file.
                    If None, uses default path from garmin_mcp.utils.paths.
        """
        # Initialize all specialized readers
        self.metadata = MetadataReader(db_path)
        self.splits = SplitsReader(db_path)
        self.time_series = TimeSeriesReader(db_path)
        self.export = ExportReader(db_path)

        # Specialized readers (split from AggregateReader)
        self.form = FormReader(db_path)
        self.physiology = PhysiologyReader(db_path)
        self.performance = PerformanceReader(db_path)
        self.utility = UtilityReader(db_path)

        # Backward compatibility: aggregate delegates to specialized readers
        self.aggregate = AggregateReader(
            db_path,
            form=self.form,
            physiology=self.physiology,
            performance=self.performance,
            utility=self.utility,
        )

        # For backward compatibility, expose db_path
        self.db_path = self.metadata.db_path

    def execute_read_query(
        self, sql: str, params: tuple[Any, ...] = ()
    ) -> list[tuple[Any, ...]]:
        """Execute a read-only SQL query and return all results.

        Centralizes DuckDB connection management so callers don't need
        to import duckdb or manage connections directly.

        Args:
            sql: SQL query string
            params: Query parameters

        Returns:
            List of result tuples
        """
        with self.metadata._get_connection() as conn:
            result: list[tuple[Any, ...]] = conn.execute(sql, params).fetchall()
            return result

    def execute_read_query_with_columns(
        self, sql: str, params: tuple[Any, ...] = ()
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        """Execute a read-only SQL query and return results with column names.

        Args:
            sql: SQL query string
            params: Query parameters

        Returns:
            Tuple of (results, column_names)
        """
        with self.metadata._get_connection() as conn:
            result = conn.execute(sql, params)
            columns = [desc[0] for desc in result.description]
            rows = result.fetchall()
            return rows, columns

    # ========== Metadata Methods ==========

    def get_activity_date(self, activity_id: int) -> str | None:
        """Get activity date from DuckDB.

        Args:
            activity_id: Activity ID

        Returns:
            Activity date in YYYY-MM-DD format, or None if not found
        """
        return self.metadata.get_activity_date(activity_id)

    def query_activity_by_date(self, date: str) -> int | None:
        """Query activity ID by date from DuckDB.

        Args:
            date: Activity date in YYYY-MM-DD format

        Returns:
            Activity ID if found, None otherwise
        """
        return self.metadata.query_activity_by_date(date)

    # ========== Splits Methods ==========

    def get_splits_pace_hr(
        self, activity_id: int, statistics_only: bool = False
    ) -> dict[str, list[dict]] | dict[str, Any]:
        """Get pace and heart rate data for all splits.

        Args:
            activity_id: Activity ID
            statistics_only: If True, return only aggregated statistics (~80% reduction)

        Returns:
            Full mode: Dict with 'splits' key containing list of split data
            Statistics mode: Dict with aggregated statistics
        """
        return self.splits.get_splits_pace_hr(activity_id, statistics_only)

    def get_splits_form_metrics(
        self, activity_id: int, statistics_only: bool = False
    ) -> dict[str, list[dict]] | dict[str, Any]:
        """Get form metrics (GCT, VO, VR) for all splits.

        Args:
            activity_id: Activity ID
            statistics_only: If True, return only aggregated statistics (~80% reduction)

        Returns:
            Full mode: Dict with 'splits' key containing list of split data
            Statistics mode: Dict with aggregated statistics
        """
        return self.splits.get_splits_form_metrics(activity_id, statistics_only)

    def get_splits_elevation(
        self, activity_id: int, statistics_only: bool = False
    ) -> dict[str, list[dict]] | dict[str, Any]:
        """Get elevation data for all splits.

        Args:
            activity_id: Activity ID
            statistics_only: If True, return only aggregated statistics (~80% reduction)

        Returns:
            Full mode: Dict with 'splits' key containing list of split data
            Statistics mode: Dict with aggregated statistics
        """
        return self.splits.get_splits_elevation(activity_id, statistics_only)

    def get_splits_comprehensive(
        self, activity_id: int, statistics_only: bool = False
    ) -> dict[str, list[dict]] | dict[str, Any]:
        """
        Get comprehensive split data (12 fields) from splits table.

        Proxy to SplitsReader.get_splits_comprehensive().

        Args:
            activity_id: Activity ID
            statistics_only: If True, return only aggregated statistics (mean, median, std, min, max)
                           instead of per-split data. Reduces output size by ~80%.
                           Default: False (backward compatible)

        Returns:
            Full mode (statistics_only=False):
                Dict with 'splits' key containing list of split data with all 12 fields
            Statistics mode (statistics_only=True):
                Dict with aggregated statistics for 12 metrics
        """
        return self.splits.get_splits_comprehensive(activity_id, statistics_only)

    def get_splits_all(
        self, activity_id: int, max_output_size: int = 10240
    ) -> dict[str, list[dict]]:
        """Get all split data from splits table (全22フィールド).

        DEPRECATED: This function returns large amounts of data.
        Consider using `export()` MCP function for large datasets.

        Args:
            activity_id: Activity ID
            max_output_size: Maximum output size in bytes (default: 10KB)

        Returns:
            Complete split data with all metrics

        Raises:
            ValueError: If output size exceeds max_output_size
        """
        return self.splits.get_splits_all(activity_id, max_output_size)

    def get_split_time_ranges(self, activity_id: int) -> list[dict[str, Any]]:
        """Get time ranges for all splits of an activity.

        Args:
            activity_id: Activity ID

        Returns:
            List of dictionaries with split time range data
        """
        return self.splits.get_split_time_ranges(activity_id)

    # ========== Form Methods ==========

    def get_form_efficiency_summary(self, activity_id: int) -> dict[str, Any] | None:
        """Get form efficiency summary (GCT, VO, VR metrics).

        Args:
            activity_id: Activity ID

        Returns:
            Form efficiency data with ratings, or None if not found
        """
        return self.form.get_form_efficiency_summary(activity_id)

    def get_form_evaluations(self, activity_id: int) -> dict[str, Any] | None:
        """Get pace-corrected form evaluation results.

        Args:
            activity_id: Activity ID

        Returns:
            Form evaluation data with expected values, actual values, scores,
            star ratings, and evaluation texts, or None if not found
        """
        return self.form.get_form_evaluations(activity_id)

    # ========== Physiology Methods ==========

    def get_hr_efficiency_analysis(self, activity_id: int) -> dict[str, Any] | None:
        """Get HR efficiency analysis (zone distribution, training type).

        Args:
            activity_id: Activity ID

        Returns:
            HR efficiency data, or None if not found
        """
        return self.physiology.get_hr_efficiency_analysis(activity_id)

    def get_heart_rate_zones_detail(self, activity_id: int) -> dict[str, Any] | None:
        """Get heart rate zones detail (boundaries, time distribution).

        Args:
            activity_id: Activity ID

        Returns:
            Heart rate zones data, or None if not found
        """
        return self.physiology.get_heart_rate_zones_detail(activity_id)

    def get_vo2_max_data(self, activity_id: int) -> dict[str, Any] | None:
        """Get VO2 max data (precise value, fitness age, category).

        Args:
            activity_id: Activity ID

        Returns:
            VO2 max data, or None if not found
        """
        return self.physiology.get_vo2_max_data(activity_id)

    def get_lactate_threshold_data(self, activity_id: int) -> dict[str, Any] | None:
        """Get lactate threshold data (HR, speed, power).

        Args:
            activity_id: Activity ID

        Returns:
            Lactate threshold data, or None if not found
        """
        return self.physiology.get_lactate_threshold_data(activity_id)

    # ========== Performance Methods ==========

    def get_performance_trends(self, activity_id: int) -> dict[str, Any] | None:
        """Get performance trends data (pace consistency, HR drift, phase analysis).

        Args:
            activity_id: Activity ID

        Returns:
            Performance trends data with phase breakdowns, or None if not found
        """
        return self.performance.get_performance_trends(activity_id)

    def get_weather_data(self, activity_id: int) -> dict[str, Any] | None:
        """Get weather data (temperature, humidity, wind).

        Args:
            activity_id: Activity ID

        Returns:
            Weather data, or None if not found
        """
        return self.performance.get_weather_data(activity_id)

    def get_section_analysis(
        self, activity_id: int, section_type: str, max_output_size: int = 10240
    ) -> dict[str, Any] | None:
        """Get section analysis from DuckDB.

        DEPRECATED: This function may return large amounts of data.
        Consider using extract_insights() MCP function instead.

        Args:
            activity_id: Activity ID
            section_type: Section type (efficiency, environment, phase, split, summary)
            max_output_size: Maximum output size in bytes (default: 10KB)

        Returns:
            Section analysis data, or None if not found

        Raises:
            ValueError: If output size exceeds max_output_size
        """
        return self.performance.get_section_analysis(
            activity_id, section_type, max_output_size
        )

    # ========== Time Series Methods ==========

    def get_time_series_statistics(
        self,
        activity_id: int,
        start_time_s: int,
        end_time_s: int,
        metrics: list[str],
    ) -> dict[str, Any]:
        """Get statistics for specified metrics in time range using SQL.

        Args:
            activity_id: Activity ID
            start_time_s: Start time in seconds
            end_time_s: End time in seconds
            metrics: List of metric column names

        Returns:
            Dictionary with statistics (avg, std, min, max)
        """
        return self.time_series.get_time_series_statistics(
            activity_id, start_time_s, end_time_s, metrics
        )

    def get_time_series_raw(
        self,
        activity_id: int,
        start_time_s: int,
        end_time_s: int,
        metrics: list[str],
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Get raw time series data for specified metrics and time range.

        Args:
            activity_id: Activity ID
            start_time_s: Start time in seconds
            end_time_s: End time in seconds
            metrics: List of metric column names
            limit: Optional limit on number of rows returned

        Returns:
            Dictionary with raw time series
        """
        return self.time_series.get_time_series_raw(
            activity_id, start_time_s, end_time_s, metrics, limit
        )

    def detect_anomalies_sql(
        self,
        activity_id: int,
        metrics: list[str],
        z_threshold: float = 2.0,
    ) -> dict[str, Any]:
        """Detect anomalies using SQL-based z-score calculation.

        Args:
            activity_id: Activity ID
            metrics: List of metric column names to check
            z_threshold: Z-score threshold (default: 2.0)

        Returns:
            Dictionary with detected anomalies and summary
        """
        return self.time_series.detect_anomalies_sql(activity_id, metrics, z_threshold)

    # ========== Export Methods ==========

    def export_query_result(
        self,
        query: str,
        output_path: Path,
        export_format: Literal["parquet", "csv"] = "parquet",
        max_rows: int = 100000,
    ) -> dict[str, Any]:
        """Export query result to file using DuckDB COPY TO.

        Args:
            query: SQL query to execute
            output_path: Output file path
            export_format: Export format (parquet or csv)
            max_rows: Maximum rows to export (safety limit)

        Returns:
            Export metadata (rows, columns, size_mb)

        Raises:
            ValueError: If query returns more than max_rows
        """
        return self.export.export_query_result(
            query, output_path, export_format, max_rows
        )
