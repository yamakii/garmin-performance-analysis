"""
DuckDB Reader for Garmin Performance Data

Provides unified read-only access to DuckDB for querying performance data.
Delegates to specialized readers for different data domains.
"""

from pathlib import Path
from typing import Any, Literal

from garmin_mcp.database.readers import (
    DurabilityReader,
    ExportReader,
    FormReader,
    MetadataReader,
    PerformanceReader,
    PhysiologyReader,
    RaceReader,
    SplitsReader,
    StrengthSessionsReader,
    TimeSeriesReader,
    TrainingLoadReader,
    UtilityReader,
)


class GarminDBReader:
    """
    Unified DuckDB reader.

    This class delegates to specialized reader classes:
    - MetadataReader: Activity date/ID queries
    - SplitsReader: Splits data queries
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
        self.race = RaceReader(db_path)
        self.training_load = TrainingLoadReader(db_path)
        self.durability = DurabilityReader(db_path)
        self.strength_sessions = StrengthSessionsReader(db_path)
        self.utility = UtilityReader(db_path)

        # Expose db_path for handlers and scripts
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

    def get_activity_dates(self, activity_ids: list[int]) -> dict[int, str]:
        """Bulk-fetch activity dates for multiple activities in one query.

        Args:
            activity_ids: List of activity IDs

        Returns:
            Dict mapping activity_id -> activity_date (YYYY-MM-DD str)
        """
        return self.metadata.get_activity_dates(activity_ids)

    def get_bulk_activity_fields(
        self, activity_ids: list[int], fields: list[str]
    ) -> dict[int, dict[str, Any]]:
        """Bulk-fetch arbitrary ``activities`` columns in a single query.

        Args:
            activity_ids: List of activity IDs
            fields: Column names to fetch (validated against an allowlist)

        Returns:
            Dict mapping activity_id -> {field: value}
        """
        return self.metadata.get_bulk_activity_fields(activity_ids, fields)

    # ========== Latest Ingest Date Methods ==========

    def get_latest_activity_date(self) -> str | None:
        """Return the most recent activity date stored in DuckDB.

        Used by catch-up window resolution. No Garmin access; reads only the
        ``activities`` table. Restricted to rows with a recorded distance
        (``total_distance_km IS NOT NULL``) so non-distance entries do not
        skew the latest-run cursor.

        Returns:
            Latest ``activity_date`` as ``YYYY-MM-DD``, or ``None`` when the
            table is empty (or all rows lack a distance).
        """
        rows = self.execute_read_query(
            "SELECT MAX(activity_date) FROM activities "
            "WHERE total_distance_km IS NOT NULL"
        )
        if rows and rows[0][0] is not None:
            return str(rows[0][0])
        return None

    def get_latest_weight_date(self) -> str | None:
        """Return the most recent body-composition date stored in DuckDB.

        Used by catch-up window resolution. No Garmin access; reads only the
        ``body_composition`` table.

        Returns:
            Latest ``date`` as ``YYYY-MM-DD``, or ``None`` when the table is
            empty.
        """
        rows = self.execute_read_query("SELECT MAX(date) FROM body_composition")
        if rows and rows[0][0] is not None:
            return str(rows[0][0])
        return None

    def get_latest_strength_date(self) -> str | None:
        """Return the most recent strength-session date stored in DuckDB.

        Used by catch-up window resolution. No Garmin access; reads only the
        ``strength_sessions`` table.

        Returns:
            Latest ``activity_date`` as ``YYYY-MM-DD``, or ``None`` when the
            table is empty.
        """
        rows = self.execute_read_query(
            "SELECT MAX(activity_date) FROM strength_sessions"
        )
        if rows and rows[0][0] is not None:
            return str(rows[0][0])
        return None

    def get_latest_wellness_date(self) -> str | None:
        """Return the most recent daily-wellness date stored in DuckDB.

        Used by catch-up window resolution. No Garmin access; reads only the
        ``daily_wellness`` table.

        Returns:
            Latest ``date`` as ``YYYY-MM-DD``, or ``None`` when the table is
            empty.
        """
        rows = self.execute_read_query("SELECT MAX(date) FROM daily_wellness")
        if rows and rows[0][0] is not None:
            return str(rows[0][0])
        return None

    # ========== Body Composition Methods ==========

    def get_body_composition_trend(self, weeks: int = 12) -> dict[str, Any]:
        """Body-composition trend over the last ``weeks`` weeks (#501).

        Reads ``body_composition`` for the trailing window and decomposes the
        weight change between the first and last measurement into fat / lean
        components. Also derives a lean-mass power-to-weight ratio using the most
        recent ``lactate_threshold.functional_threshold_power`` and the latest
        measurement's body fat (null-safe; skipped when body fat or FTP missing).

        Args:
            weeks: Trailing window length in weeks (default: 12).

        Returns:
            ``{"weeks", "series": [{"date","weight_kg","fat_mass","lean_mass"}],
            "change": {...decompose_weight_change...}, "lean_pwr": float|None}``.
            ``series`` is date-ascending; ``fat_mass`` / ``lean_mass`` are
            ``None`` for rows lacking body fat. ``change`` is an empty-ish
            decomposition (all-None deltas) when fewer than 2 measurements
            exist. Dates are ``YYYY-MM-DD`` strings.
        """
        from datetime import datetime, timedelta

        from garmin_mcp.analysis.body_composition import (
            decompose_weight_change,
            lean_power_to_weight,
        )

        cutoff = (datetime.now() - timedelta(weeks=weeks)).strftime("%Y-%m-%d")
        rows = self.execute_read_query(
            """
            SELECT date, weight_kg, body_fat_percentage
            FROM body_composition
            WHERE date >= ?
            ORDER BY date ASC
            """,
            (cutoff,),
        )

        series: list[dict[str, Any]] = []
        for date_val, weight_kg, body_fat_pct in rows:
            fat_mass: float | None = None
            lean_mass: float | None = None
            if weight_kg is not None and body_fat_pct is not None:
                fat_mass = round(weight_kg * body_fat_pct / 100.0, 2)
                lean_mass = round(weight_kg - fat_mass, 2)
            series.append(
                {
                    "date": str(date_val),
                    "weight_kg": weight_kg,
                    "fat_mass": fat_mass,
                    "lean_mass": lean_mass,
                }
            )

        if len(rows) >= 2:
            first = {
                "weight_kg": rows[0][1],
                "body_fat_pct": rows[0][2],
            }
            last = {
                "weight_kg": rows[-1][1],
                "body_fat_pct": rows[-1][2],
            }
            change = decompose_weight_change(first, last)
        else:
            change = {
                "delta_weight": None,
                "delta_fat": None,
                "delta_lean": None,
                "lean_loss_ratio": None,
                "muscle_loss_warning": False,
            }

        # Lean power-to-weight from the most recent FTP and the latest body comp.
        ftp_rows = self.execute_read_query("""
            SELECT functional_threshold_power
            FROM lactate_threshold
            WHERE functional_threshold_power IS NOT NULL
            ORDER BY date_power DESC NULLS LAST
            LIMIT 1
            """)
        ftp_w = ftp_rows[0][0] if ftp_rows else None
        lean_pwr: float | None = None
        if rows:
            lean_pwr = lean_power_to_weight(
                ftp_w=ftp_w,
                weight_kg=rows[-1][1],
                body_fat_pct=rows[-1][2],
            )

        return {
            "weeks": weeks,
            "series": series,
            "change": change,
            "lean_pwr": lean_pwr,
        }

    def get_weight_economy_coupling(
        self,
        weeks: int = 52,
        training_types: list[str] | None = None,
        max_gap_days: int = 14,
    ) -> dict[str, Any]:
        """Couple easy runs with body weight and fit the longitudinal EF model (#554).

        Joins easy runs (``hr_efficiency.training_type`` in ``training_types``,
        default ``["aerobic_base"]``) within the last ``weeks`` weeks against all
        ``body_composition`` weights by nearest-neighbour date matching
        (``max_gap_days``), derives the efficiency factor
        ``EF = avg_speed_ms / avg_heart_rate`` per run, attaches a per-activity
        VO2max fitness covariate (nearest ``vo2_max`` by date), and fits the
        longitudinal OLS ``EF ~ weight + days (+ fitness)`` (#552/#553). Reports
        the weight effect as an *association* (effect size + collinearity note),
        not a clean causal coefficient. ``activities.body_mass_kg`` is not used
        (unbackfilled); weight always comes from ``body_composition``.

        Args:
            weeks: Trailing window length in weeks (default: 52).
            training_types: ``hr_efficiency.training_type`` values to treat as
                easy runs (default: ``["aerobic_base"]``).
            max_gap_days: Maximum allowed absolute day gap for the run/weight join.

        Returns:
            ``{"weeks", "n_runs_total", "n_matched", "weight_spread_kg", "model",
            "series": [{"activity_id","run_date","weight_kg","ef",
            "weight_gap_days"}], "note"}``. ``model`` is the
            :class:`WeightEconomyModel` as a dict, or ``None`` (with a ``"reason"``
            string) when too few runs matched for the regression. Never raises on
            insufficient data. Dates are ``YYYY-MM-DD`` strings.
        """
        import dataclasses
        from datetime import datetime, timedelta

        from garmin_mcp.analysis.running_economy import (
            RunRecord,
            WeightMeasurement,
            fit_weight_economy_model,
            join_runs_with_weight,
        )

        if training_types is None:
            training_types = ["aerobic_base"]

        cutoff = (datetime.now() - timedelta(weeks=weeks)).strftime("%Y-%m-%d")
        placeholders = ",".join("?" for _ in training_types)
        run_rows = self.execute_read_query(
            f"""
            SELECT a.activity_id, a.activity_date, a.avg_speed_ms, a.avg_heart_rate
            FROM activities a
            JOIN hr_efficiency h ON a.activity_id = h.activity_id
            WHERE h.training_type IN ({placeholders})
              AND a.activity_date >= ?
              AND a.avg_speed_ms IS NOT NULL
              AND a.avg_heart_rate IS NOT NULL
            ORDER BY a.activity_date ASC
            """,
            (*training_types, cutoff),
        )
        runs = [
            RunRecord(
                activity_id=int(activity_id),
                run_date=run_date,
                avg_speed_ms=float(avg_speed_ms),
                avg_heart_rate=float(avg_heart_rate),
            )
            for activity_id, run_date, avg_speed_ms, avg_heart_rate in run_rows
        ]

        weight_rows = self.execute_read_query("""
            SELECT date, weight_kg
            FROM body_composition
            WHERE weight_kg IS NOT NULL
            ORDER BY date ASC
            """)
        measurements = [
            WeightMeasurement(measure_date=measure_date, weight_kg=float(weight_kg))
            for measure_date, weight_kg in weight_rows
        ]

        # Fitness covariate: nearest VO2max (by date) per run activity.
        vo2_rows = self.execute_read_query("""
            SELECT date, value
            FROM vo2_max
            WHERE value IS NOT NULL AND date IS NOT NULL
            ORDER BY date ASC
            """)
        vo2_points = [(vo2_date, float(value)) for vo2_date, value in vo2_rows]
        fitness_by_activity: dict[int, float] = {}
        for run in runs:
            if not vo2_points:
                break
            nearest = min(vo2_points, key=lambda p: abs((run.run_date - p[0]).days))
            fitness_by_activity[run.activity_id] = nearest[1]

        coupled = join_runs_with_weight(runs, measurements, max_gap_days=max_gap_days)
        weights = [c.weight_kg for c in coupled]
        weight_spread = round(max(weights) - min(weights), 2) if weights else 0.0
        series = [
            {
                "activity_id": c.activity_id,
                "run_date": str(c.run_date),
                "weight_kg": c.weight_kg,
                "ef": c.ef,
                "weight_gap_days": c.weight_gap_days,
            }
            for c in coupled
        ]

        result: dict[str, Any] = {
            "weeks": weeks,
            "n_runs_total": len(runs),
            "n_matched": len(coupled),
            "weight_spread_kg": weight_spread,
            "model": None,
            "series": series,
            "note": "",
        }

        fitness = fitness_by_activity if fitness_by_activity else None
        try:
            model = fit_weight_economy_model(coupled, fitness_by_activity=fitness)
        except ValueError as exc:
            result["model"] = None
            result["reason"] = str(exc)
            result["note"] = (
                "insufficient matched runs for the longitudinal regression; "
                "no association estimated"
            )
            return result

        result["model"] = dataclasses.asdict(model)
        result["note"] = model.note
        return result

    def get_recovery_trend(self, weeks: int = 8) -> dict[str, Any]:
        """RHR / HRV recovery trend over the last ``weeks`` weeks (#499).

        Reads ``daily_wellness`` for the trailing window and derives a
        resting-HR trend (7-day vs 30-day median) and an HRV recovery status
        (consecutive nights below baseline). Backs "my cardio came back" with
        objective markers; ``hrv.under_recovery`` is meant to be AND-ed with a
        high ``get_acwr`` to flag under-recovery.

        Args:
            weeks: Trailing window length in weeks (default: 8).

        Returns:
            ``{"weeks", "rhr": {median_7d, median_30d, rhr_trend}, "hrv":
            {latest_ms, status, hrv_below_baseline_days, under_recovery},
            "series": [{date, resting_hr, hrv_overnight_ms}]}``. ``series`` is
            date-ascending; medians / HRV fields are ``None`` when data is
            missing (null-safe). Dates are ``YYYY-MM-DD`` strings.
        """
        from datetime import datetime, timedelta

        from garmin_mcp.analysis.recovery import (
            compute_hrv_recovery,
            compute_rhr_trend,
        )

        cutoff = (datetime.now() - timedelta(weeks=weeks)).strftime("%Y-%m-%d")
        rows = self.execute_read_query(
            """
            SELECT date, resting_hr, hrv_overnight_ms,
                   hrv_baseline_low, hrv_baseline_high
            FROM daily_wellness
            WHERE date >= ?
            ORDER BY date ASC
            """,
            (cutoff,),
        )

        series: list[dict[str, Any]] = []
        daily_rhr: list[tuple[str, int | None]] = []
        hrv_rows: list[tuple[str, float | None, float | None, float | None]] = []
        for date_val, resting_hr, hrv_ms, base_low, base_high in rows:
            date_str = str(date_val)
            series.append(
                {
                    "date": date_str,
                    "resting_hr": resting_hr,
                    "hrv_overnight_ms": hrv_ms,
                }
            )
            daily_rhr.append((date_str, resting_hr))
            hrv_rows.append((date_str, hrv_ms, base_low, base_high))

        return {
            "weeks": weeks,
            "rhr": compute_rhr_trend(daily_rhr),
            "hrv": compute_hrv_recovery(hrv_rows),
            "series": series,
        }

    def get_recovery_status(self, date: str | None = None) -> dict[str, Any]:
        """Morning go/no-go recovery status for ``date`` (#500).

        Synthesizes the day's Training Readiness, Body Battery, sleep score and
        the HRV ``under_recovery`` flag (#499) into a recommended training
        intensity (rest/easy/moderate/quality), to support a data-backed
        "run or rest" decision.

        Args:
            date: Target ``YYYY-MM-DD`` day. ``None`` (default) uses the latest
                date present in ``daily_wellness``.

        Returns:
            ``{"date", "recommendation", "score", "reasons",
            "training_readiness", "body_battery_high", "sleep_score"}``. When the
            day has no data (device off) ``recommendation`` is ``"unknown"`` with
            a "go by feel" reason (null-safe). ``date`` is ``None`` only when the
            table is empty. Dates are ``YYYY-MM-DD`` strings.
        """
        from garmin_mcp.analysis.recovery import (
            classify_recovery_status,
            compute_hrv_recovery,
        )

        if date is None:
            latest = self.execute_read_query("SELECT MAX(date) FROM daily_wellness", ())
            date = str(latest[0][0]) if latest and latest[0][0] is not None else None

        if date is None:
            return {
                "date": None,
                "recommendation": "unknown",
                "score": None,
                "reasons": ["データ無し・感覚優先"],
                "training_readiness": None,
                "body_battery_high": None,
                "sleep_score": None,
            }

        day_rows = self.execute_read_query(
            """
            SELECT training_readiness, body_battery_high, sleep_score
            FROM daily_wellness
            WHERE date = ?
            """,
            (date,),
        )
        readiness: int | None = None
        body_battery_high: int | None = None
        sleep_score: int | None = None
        if day_rows:
            readiness, body_battery_high, sleep_score = day_rows[0]

        # Derive the HRV under-recovery flag from the trailing window up to date.
        hrv_window = self.execute_read_query(
            """
            SELECT date, hrv_overnight_ms, hrv_baseline_low, hrv_baseline_high
            FROM daily_wellness
            WHERE date <= ?
            ORDER BY date ASC
            """,
            (date,),
        )
        hrv_rows: list[tuple[str, float | None, float | None, float | None]] = [
            (str(d), ms, low, high) for d, ms, low, high in hrv_window
        ]
        under_recovery = compute_hrv_recovery(hrv_rows)["under_recovery"]

        status = classify_recovery_status(
            readiness, body_battery_high, sleep_score, under_recovery
        )
        return {
            "date": date,
            "recommendation": status["recommendation"],
            "score": status["score"],
            "reasons": status["reasons"],
            "training_readiness": readiness,
            "body_battery_high": body_battery_high,
            "sleep_score": sleep_score,
        }

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

    def get_bulk_metric_averages(
        self, activity_ids: list[int], column: str
    ) -> dict[int, float]:
        """Get average metric value per activity in a single SQL query.

        Args:
            activity_ids: List of activity IDs
            column: DuckDB column name (e.g., "pace_seconds_per_km")

        Returns:
            Dict mapping activity_id to average value
        """
        return self.splits.get_bulk_metric_averages(activity_ids, column)

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

    # ========== Race Methods ==========

    def get_race_readiness(
        self, user_id: str = "default", lookback_weeks: int = 8
    ) -> dict[str, Any]:
        """Get race readiness (current VDOT, predictions, and goal progress).

        Args:
            user_id: Profile owner identifier (defaults to ``"default"``)
            lookback_weeks: Lookback window for fitness assessment (default 8)

        Returns:
            Dict with current_vdot, predicted_times, goal, and progress.
        """
        return self.race.get_race_readiness(user_id, lookback_weeks)

    # ========== Training Load Methods ==========

    def get_acwr(self, end_date: str | None = None) -> dict[str, Any]:
        """Get the distance-based Acute:Chronic Workload Ratio (ACWR).

        Args:
            end_date: ``YYYY-MM-DD`` reference day (defaults to the latest
                ``activity_date``).

        Returns:
            Dict with end_date, acute_load_7d, chronic_load_28d_weekly, acwr,
            status, and load_metric.
        """
        return self.training_load.get_acwr(end_date)

    def get_load_trend(
        self, lookback_weeks: int = 12, end_date: str | None = None
    ) -> dict[str, Any]:
        """Get the weekly load and ACWR trend over ``lookback_weeks``.

        Args:
            lookback_weeks: Number of trailing weekly buckets (default 12).
            end_date: ``YYYY-MM-DD`` reference day (defaults to the latest
                ``activity_date``).

        Returns:
            Dict with a ``weeks`` array (week_start, load_km, acwr, status) and
            ``load_metric``.
        """
        return self.training_load.get_load_trend(lookback_weeks, end_date)

    # ========== Durability Methods ==========

    def get_activity_durability(self, activity_id: int) -> dict[str, Any] | None:
        """Get one activity's first-half vs second-half cardiac decoupling.

        Args:
            activity_id: Activity ID.

        Returns:
            Dict with activity_id, activity_date, distance_km, decoupling_pct,
            and pace_fade_pct, or None when HR/speed data is missing or the
            timestamp midpoint cannot split the series.
        """
        return self.durability.get_activity_durability(activity_id)

    def get_durability_trend(
        self, start_date: str, end_date: str, min_distance_km: float = 15.0
    ) -> dict[str, Any]:
        """Get the long-run decoupling trend over a date window.

        Args:
            start_date: Inclusive window start (``YYYY-MM-DD``).
            end_date: Inclusive window end (``YYYY-MM-DD``).
            min_distance_km: Minimum distance to qualify as a long run
                (default 15.0).

        Returns:
            Dict with an ``activities`` array (per-activity durability, date
            ascending) and a ``trend`` block (decoupling_slope_per_day,
            data_points, direction).
        """
        return self.durability.get_durability_trend(
            start_date, end_date, min_distance_km
        )

    # ========== Strength Session Methods ==========

    def get_strength_sessions(
        self, start_date: str, end_date: str
    ) -> list[dict[str, Any]]:
        """Get strength-training summaries with date in ``[start, end]``.

        Args:
            start_date: Inclusive window start (``YYYY-MM-DD``).
            end_date: Inclusive window end (``YYYY-MM-DD``).

        Returns:
            List of strength-session dicts (``activity_date`` ascending) with
            ``category_counts`` as a dict and dates as strings. Empty list when
            no session falls in the range. No Garmin access.
        """
        return self.strength_sessions.get_strength_sessions(start_date, end_date)

    # ========== Heat Adjustment Methods ==========

    def get_heat_adjusted_trend(
        self,
        activity_ids: list[int],
        start_date: str,
        end_date: str,
        ref_temp_c: float = 15.0,
    ) -> dict[str, Any]:
        """Get the climate-neutral HR-at-pace trend with per-run heat_cost.

        Thin wrapper around
        ``HeatAdjustmentModel(ref_temp_c).compute_trend(...)``. Fits the
        temperature-hinge regression and returns, for each run in the window,
        the ``heat_cost`` and climate-neutral HR (reprojected onto
        ``ref_temp_c``), plus the time trend of the neutral HR.

        Args:
            activity_ids: Activity IDs to include.
            start_date: Inclusive lower date bound (``YYYY-MM-DD``).
            end_date: Inclusive upper date bound (``YYYY-MM-DD``).
            ref_temp_c: Hinge reference temperature in Celsius (default 15.0).

        Returns:
            ``json.dumps``-serializable dict (``status="ok"`` with coefficients
            and points, or ``status="insufficient_data"`` when too few complete
            rows fall in the window).
        """
        from garmin_mcp.rag.queries.heat_adjustment import HeatAdjustmentModel

        model = HeatAdjustmentModel(db_path=str(self.db_path), ref_temp_c=ref_temp_c)
        return model.compute_trend(activity_ids, start_date, end_date)

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
