"""Data loading components extracted from ReportGeneratorWorker."""

import logging
from typing import Any

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.reporting.components.formatting import format_pace

logger = logging.getLogger(__name__)


class ReportDataLoader:
    """Loads performance data, section analyses, and splits from DuckDB."""

    def __init__(self, db_reader: GarminDBReader) -> None:
        self.db_reader = db_reader

    def load_performance_data(
        self,
        activity_id: int,
        *,
        comparator: Any = None,
        physiological_calculator: Any = None,
        chart_generator: Any = None,
        insight_generator: Any = None,
    ) -> dict[str, Any] | None:
        """
        Load all performance data from DuckDB.

        Args:
            activity_id: Activity ID
            comparator: WorkoutComparator instance for similarity comparison
            physiological_calculator: PhysiologicalCalculator instance
            chart_generator: ChartGenerator instance
            insight_generator: InsightGenerator instance

        Returns:
            Complete performance data dict or None
        """
        from garmin_mcp.reporting.components.formatting import (
            get_training_type_category,
        )

        logger.info("[1/4] Loading performance data from DuckDB...")

        try:
            # Load basic info and metrics from activities table
            results = self.db_reader.execute_read_query(
                """
                SELECT
                    activity_name,
                    location_name,
                    start_time_local,
                    total_distance_km,
                    total_time_seconds,
                    avg_pace_seconds_per_km,
                    avg_heart_rate,
                    temp_celsius,
                    relative_humidity_percent,
                    wind_speed_kmh,
                    gear_type,
                    gear_model
                FROM activities
                WHERE activity_id = ?
                """,
                (activity_id,),
            )
            result = results[0] if results else None

            if not result:
                logger.warning(
                    f"Warning: No performance data found in DuckDB for activity {activity_id}"
                )
                return None

            # Load form efficiency statistics
            form_results = self.db_reader.execute_read_query(
                """
                SELECT
                    gct_average, gct_std, gct_rating,
                    vo_average, vo_std, vo_rating,
                    vr_average, vr_std, vr_rating
                FROM form_efficiency
                WHERE activity_id = ?
                """,
                (activity_id,),
            )
            form_eff = form_results[0] if form_results else None

            # Load performance trends (support both 3-phase and 4-phase)
            schema_check = self.db_reader.execute_read_query(
                "PRAGMA table_info('performance_trends')"
            )
            column_names = [row[1] for row in schema_check]

            if "recovery_avg_pace_seconds_per_km" in column_names:
                perf_results = self.db_reader.execute_read_query(
                    """
                    SELECT
                        pace_consistency, hr_drift_percentage, cadence_consistency, fatigue_pattern,
                        warmup_avg_pace_seconds_per_km, warmup_avg_hr,
                        run_avg_pace_seconds_per_km, run_avg_hr, run_avg_power,
                        recovery_avg_pace_seconds_per_km, recovery_avg_hr,
                        cooldown_avg_pace_seconds_per_km, cooldown_avg_hr
                    FROM performance_trends
                    WHERE activity_id = ?
                    """,
                    (activity_id,),
                )
            else:
                perf_results = self.db_reader.execute_read_query(
                    """
                    SELECT
                        pace_consistency, hr_drift_percentage, cadence_consistency, fatigue_pattern,
                        warmup_avg_pace_seconds_per_km, warmup_avg_hr,
                        main_avg_pace_seconds_per_km, main_avg_hr, NULL,
                        NULL, NULL,
                        finish_avg_pace_seconds_per_km, finish_avg_hr
                    FROM performance_trends
                    WHERE activity_id = ?
                    """,
                    (activity_id,),
                )
            perf_trends = perf_results[0] if perf_results else None

            # Load HR efficiency (includes training_type)
            hr_results = self.db_reader.execute_read_query(
                """
                SELECT training_type
                FROM hr_efficiency
                WHERE activity_id = ?
                """,
                (activity_id,),
            )
            hr_eff = hr_results[0] if hr_results else None

            # Load heart rate zone times (if table exists)
            try:
                hr_zone_times = self.db_reader.execute_read_query(
                    """
                    SELECT zone_number, time_in_zone_seconds
                    FROM heart_rate_zones
                    WHERE activity_id = ?
                    ORDER BY zone_number
                    """,
                    (activity_id,),
                )
            except Exception:
                hr_zone_times = []

            # Load VO2 Max data (uses fallback to most recent data)
            vo2_max_dict = self.db_reader.get_vo2_max_data(activity_id)

            # Load lactate threshold data
            lactate_threshold_dict = self.db_reader.get_lactate_threshold_data(
                activity_id
            )

            # Build response data
            data: dict[str, Any] = {
                "activity_name": result[0],
                "location_name": result[1],
                "basic_metrics": {
                    "start_time": result[2],
                    "distance_km": result[3],
                    "duration_seconds": result[4],
                    "avg_pace_seconds_per_km": result[5],
                    "avg_heart_rate": result[6],
                },
                "weight_kg": None,
                "weather_data": {
                    "temp_celsius": result[7],
                    "relative_humidity_percent": result[8],
                    "wind_speed_kmh": result[9],
                },
                "gear_name": f"{result[10]} {result[11]}" if result[10] else None,
            }

            # Add form efficiency data if available
            if form_eff:
                data["form_efficiency"] = {
                    "gct_average": form_eff[0],
                    "gct_std": form_eff[1],
                    "gct_rating": form_eff[2],
                    "vo_average": form_eff[3],
                    "vo_std": form_eff[4],
                    "vo_rating": form_eff[5],
                    "vr_average": form_eff[6],
                    "vr_std": form_eff[7],
                    "vr_rating": form_eff[8],
                }

            # Add performance metrics if available
            if perf_trends:
                data["performance_metrics"] = {
                    "pace_consistency": perf_trends[0],
                    "hr_drift_percentage": perf_trends[1],
                    "cadence_consistency": perf_trends[2],
                    "fatigue_pattern": perf_trends[3],
                }
                data["warmup_metrics"] = {
                    "avg_pace_seconds_per_km": perf_trends[4],
                    "avg_hr": perf_trends[5],
                }
                if perf_trends[9] is not None:
                    data["run_metrics"] = {
                        "avg_pace_seconds_per_km": perf_trends[6],
                        "avg_hr": perf_trends[7],
                        "avg_power": perf_trends[8],
                        "pace_consistency": perf_trends[0],
                    }
                    data["recovery_metrics"] = {
                        "avg_pace_seconds_per_km": perf_trends[9],
                        "avg_hr": perf_trends[10],
                    }
                    data["cooldown_metrics"] = {
                        "avg_pace_seconds_per_km": perf_trends[11],
                        "avg_hr": perf_trends[12],
                        "fatigue_pattern": perf_trends[3],
                    }
                else:
                    data["run_metrics"] = {
                        "avg_pace_seconds_per_km": perf_trends[6],
                        "avg_hr": perf_trends[7],
                        "avg_power": perf_trends[8],
                        "pace_consistency": perf_trends[0],
                    }
                    data["cooldown_metrics"] = {
                        "avg_pace_seconds_per_km": perf_trends[11],
                        "avg_hr": perf_trends[12],
                        "fatigue_pattern": perf_trends[3],
                    }
                    data["main_metrics"] = data["run_metrics"]
                    data["finish_metrics"] = data["cooldown_metrics"]

            # Add training type if available
            if hr_eff:
                data["training_type"] = hr_eff[0]

            # Add VO2 Max data if available
            if vo2_max_dict:
                data["vo2_max_data"] = vo2_max_dict

            # Add lactate threshold data if available
            if lactate_threshold_dict:
                data["lactate_threshold_data"] = lactate_threshold_dict

            # Add similar workouts comparison (Phase 3)
            if comparator:
                comparison_pace, pace_source = comparator.get_comparison_pace(data)

                current_metrics = {
                    "avg_pace": comparison_pace,
                    "avg_hr": data["basic_metrics"]["avg_heart_rate"],
                    "pace_source": pace_source,
                }
                data["similar_workouts"] = comparator.load_similar_workouts(
                    activity_id, current_metrics
                )

                # Generate workout insight based on comparison data
                if data["similar_workouts"] and insight_generator:
                    data["similar_workouts"]["insight"] = (
                        insight_generator.generate_workout_insight(
                            data["similar_workouts"],
                            data.get("training_type", "aerobic_base"),
                        )
                    )

                # Generate reference info
                if insight_generator:
                    data["reference_info"] = insight_generator.generate_reference_info(
                        data.get("vo2_max_data"),
                        data.get("lactate_threshold_data"),
                        data.get("training_type", "aerobic_base"),
                    )
                else:
                    data["reference_info"] = ""
            else:
                data["similar_workouts"] = None
                data["reference_info"] = ""

            # Add pace-corrected form efficiency (Phase 4)
            if form_eff and physiological_calculator:
                run_metrics = physiological_calculator.calculate_run_phase_power_stride(
                    activity_id
                )

                baselines = physiological_calculator.calculate_power_stride_baselines(
                    activity_id,
                    data.get("similar_workouts"),
                    data.get("training_type"),
                )

                data["form_efficiency_pace_corrected"] = (
                    physiological_calculator.calculate_pace_corrected_form_efficiency(
                        data["basic_metrics"]["avg_pace_seconds_per_km"],
                        data["form_efficiency"],
                        run_power=run_metrics.get("avg_power"),
                        run_stride=run_metrics.get("avg_stride"),
                        baseline_power=baselines.get("baseline_power"),
                        baseline_stride=baselines.get("baseline_stride"),
                    )
                )

            # Load splits and generate Mermaid graph data
            data["splits"] = self.load_splits(activity_id)
            if chart_generator:
                data["mermaid_data"] = chart_generator.generate_mermaid_data(
                    data.get("splits")
                )
            else:
                data["mermaid_data"] = None

            # Phase 2 Enhancements
            training_type = data.get("training_type", "")
            training_type_category = get_training_type_category(training_type)
            data["training_type_category"] = training_type_category

            if (
                training_type_category in ["tempo_threshold", "interval_sprint"]
                and physiological_calculator
            ):
                physiological_indicators = (
                    physiological_calculator.calculate_physiological_indicators(
                        training_type_category,
                        data.get("vo2_max_data"),
                        data.get("lactate_threshold_data"),
                        data.get("run_metrics", {}),
                        hr_zone_times,
                    )
                )
                data.update(physiological_indicators)

            if comparator:
                data["target_segments_description"] = (
                    comparator.get_evaluation_target_text(training_type_category)
                )
            else:
                data["target_segments_description"] = ""

            if (
                training_type_category == "interval_sprint"
                and data.get("splits")
                and chart_generator
            ):
                data["interval_graph_analysis"] = (
                    chart_generator.generate_mermaid_analysis(
                        data["splits"], training_type_category
                    )
                )

            return data

        except Exception as e:
            logger.error(f"Error loading performance data: {e}")
            return None

    def load_section_analyses(
        self,
        activity_id: int,
        performance_data: dict[str, Any] | None = None,
        physiological_calculator: Any = None,
    ) -> dict[str, dict[str, Any]] | None:
        """
        Load section analyses from DuckDB matching actual data structures.

        Args:
            activity_id: Activity ID
            performance_data: Optional performance data containing pace_corrected calculations
            physiological_calculator: PhysiologicalCalculator instance for table building

        Returns:
            Section analyses dict or None
        """
        logger.info("[2/4] Loading section analyses from DuckDB...")

        analyses: dict[str, Any] = {}

        # Load efficiency analysis
        efficiency_data = self.db_reader.get_section_analysis(activity_id, "efficiency")
        if efficiency_data:
            if (
                performance_data
                and "form_efficiency_pace_corrected" in performance_data
                and physiological_calculator
            ):
                table_data = physiological_calculator.build_form_efficiency_table(
                    performance_data["form_efficiency_pace_corrected"]
                )

                analyses["efficiency"] = {
                    **table_data,
                    "efficiency": efficiency_data.get("efficiency", ""),
                    "evaluation": efficiency_data.get("evaluation", ""),
                    "form_trend": efficiency_data.get("form_trend", ""),
                    "efficiency_text": efficiency_data.get("efficiency", ""),
                    "hr_efficiency_text": efficiency_data.get(
                        "evaluation", efficiency_data.get("hr_efficiency_text", "")
                    ),
                }
            elif (
                "form_efficiency_table" in efficiency_data
                or "efficiency" in efficiency_data
            ):
                analyses["efficiency"] = efficiency_data
            else:
                analyses["efficiency"] = efficiency_data
        else:
            logger.warning("Warning: efficiency section analysis missing")

        # Load environment analysis
        environment_data = self.db_reader.get_section_analysis(
            activity_id, "environment"
        )
        if environment_data:
            analyses["environment_analysis"] = environment_data.get("environmental", {})
        else:
            logger.warning("Warning: environment section analysis missing")

        # Load phase analysis
        phase_data = self.db_reader.get_section_analysis(activity_id, "phase")
        if phase_data:
            analyses["phase_evaluation"] = phase_data
        else:
            logger.warning("Warning: phase section analysis missing")

        # Load split analysis
        split_data = self.db_reader.get_section_analysis(activity_id, "split")
        if split_data:
            analyses["split_analysis"] = split_data
        else:
            logger.warning("Warning: split section analysis missing or empty")

        # Load summary analysis
        summary_data = self.db_reader.get_section_analysis(activity_id, "summary")
        if summary_data:
            if "key_strengths" in summary_data and isinstance(
                summary_data["key_strengths"], str
            ):
                summary_data["key_strengths"] = [
                    line.strip()
                    for line in summary_data["key_strengths"].split("\n\n")
                    if line.strip()
                ]

            if "improvement_areas" in summary_data and isinstance(
                summary_data["improvement_areas"], str
            ):
                summary_data["improvement_areas"] = [
                    line.strip()
                    for line in summary_data["improvement_areas"].split("\n\n")
                    if line.strip()
                ]

            analyses["summary"] = summary_data
        else:
            logger.warning("Warning: summary section analysis missing")

        if not analyses:
            logger.warning("Warning: No section analyses found in DuckDB")
            return None

        return analyses

    def load_splits_data(self, activity_id: int) -> list[dict[str, Any]] | None:
        """
        Load splits data from splits table.

        Args:
            activity_id: Activity ID

        Returns:
            List of split dictionaries or None
        """
        logger.info("[2.5/4] Loading splits data from DuckDB...")

        try:
            result = self.db_reader.execute_read_query(
                """
                SELECT
                    split_index,
                    distance,
                    pace_seconds_per_km,
                    heart_rate,
                    cadence,
                    power,
                    stride_length,
                    ground_contact_time,
                    vertical_oscillation,
                    vertical_ratio,
                    elevation_gain,
                    elevation_loss,
                    pace_str,
                    intensity_type
                FROM splits
                WHERE activity_id = ?
                ORDER BY split_index
                """,
                (activity_id,),
            )

            if not result:
                logger.warning(
                    f"Warning: No splits data found in DuckDB for activity {activity_id}"
                )
                return None

            splits = []
            for row in result:
                splits.append(
                    {
                        "index": row[0],
                        "distance": row[1],
                        "pace_seconds_per_km": row[2],
                        "pace_formatted": (row[12] if row[12] else "N/A"),
                        "heart_rate": row[3],
                        "cadence": row[4],
                        "power": row[5],
                        "stride_length": (row[6] / 100 if row[6] else None),
                        "ground_contact_time": row[7],
                        "vertical_oscillation": row[8],
                        "vertical_ratio": row[9],
                        "elevation_gain": row[10],
                        "elevation_loss": row[11],
                        "intensity_type": row[13],
                    }
                )

            return splits

        except Exception as e:
            logger.error(f"Error loading splits data: {e}")
            return None

    def load_splits(self, activity_id: int) -> list[dict[str, Any]]:
        """
        Load splits from DuckDB (used internally by load_performance_data).

        Args:
            activity_id: Activity ID

        Returns:
            List of split dictionaries with index, pace, HR, etc.
        """
        try:
            result = self.db_reader.execute_read_query(
                """
                SELECT
                    split_index AS index,
                    pace_seconds_per_km,
                    heart_rate,
                    cadence,
                    power,
                    stride_length,
                    ground_contact_time,
                    vertical_oscillation,
                    vertical_ratio,
                    elevation_gain,
                    elevation_loss,
                    intensity_type
                FROM splits
                WHERE activity_id = ?
                ORDER BY split_index
                """,
                (activity_id,),
            )

            if not result:
                logger.warning(f"No splits found for activity {activity_id}")
                return []

            splits = []
            for row in result:
                pace_seconds = row[1]
                if pace_seconds and pace_seconds > 0:
                    pace_formatted = format_pace(pace_seconds)
                else:
                    pace_formatted = "N/A"

                # Normalize intensity_type (Garmin uses uppercase)
                raw_intensity_type = row[11]
                intensity_type = None
                if raw_intensity_type:
                    intensity_upper = raw_intensity_type.upper()
                    if intensity_upper == "WARMUP":
                        intensity_type = "warmup"
                    elif intensity_upper == "INTERVAL":
                        intensity_type = "active"
                    elif intensity_upper == "RECOVERY":
                        intensity_type = "rest"
                    elif intensity_upper == "COOLDOWN":
                        intensity_type = "cooldown"
                    else:
                        intensity_type = raw_intensity_type.lower()

                splits.append(
                    {
                        "index": row[0],
                        "pace_seconds_per_km": pace_seconds,
                        "pace_formatted": pace_formatted,
                        "heart_rate": row[2],
                        "cadence": row[3],
                        "power": row[4],
                        "stride_length": (row[5] / 100 if row[5] else None),
                        "ground_contact_time": row[6],
                        "vertical_oscillation": row[7],
                        "vertical_ratio": row[8],
                        "elevation_gain": row[9],
                        "elevation_loss": row[10],
                        "intensity_type": intensity_type,
                    }
                )

            logger.info(f"Loaded {len(splits)} splits for activity {activity_id}")
            return splits

        except Exception as e:
            logger.error(f"Error loading splits: {e}", exc_info=True)
            return []
