"""
Report Generator Worker

Reads performance data from DuckDB and generates final Markdown report.
Python Worker for report generation from section analyses.
"""

import json
import logging
from datetime import datetime
from typing import Any

from tools.database.db_reader import GarminDBReader
from tools.reporting.report_template_renderer import ReportTemplateRenderer

logger = logging.getLogger(__name__)


class ReportGeneratorWorker:
    """Python Worker for report generation from section analyses."""

    def __init__(self, db_path: str = "data/database/garmin_performance.duckdb"):
        """
        Initialize report generator worker.

        Args:
            db_path: DuckDB database path
        """
        self.db_reader = GarminDBReader(db_path)
        self.renderer = ReportTemplateRenderer()

    def load_performance_data(self, activity_id: int) -> dict[str, Any] | None:
        """
        Load all performance data from DuckDB.

        Args:
            activity_id: Activity ID

        Returns:
            Complete performance data dict or None
        """
        logger.info("[1/4] Loading performance data from DuckDB...")

        import duckdb

        try:
            conn = duckdb.connect(str(self.db_reader.db_path), read_only=True)

            # Load basic info and metrics from activities table
            result = conn.execute(
                """
                SELECT
                    activity_name,
                    location_name,
                    total_distance_km,
                    total_time_seconds,
                    avg_pace_seconds_per_km,
                    avg_heart_rate,
                    avg_cadence,
                    avg_power,
                    weight_kg,
                    external_temp_c,
                    humidity,
                    wind_speed_ms,
                    gear_name
                FROM activities
                WHERE activity_id = ?
                """,
                [activity_id],
            ).fetchone()

            if not result:
                conn.close()
                logger.warning(
                    f"Warning: No performance data found in DuckDB for activity {activity_id}"
                )
                return None

            # Load form efficiency statistics
            form_eff = conn.execute(
                """
                SELECT
                    gct_average, gct_std, gct_rating,
                    vo_average, vo_std, vo_rating,
                    vr_average, vr_std, vr_rating
                FROM form_efficiency
                WHERE activity_id = ?
                """,
                [activity_id],
            ).fetchone()

            # Load performance trends (support both 3-phase and 4-phase)
            # Check which columns exist in the schema
            schema_check = conn.execute(
                "PRAGMA table_info('performance_trends')"
            ).fetchall()
            column_names = [row[1] for row in schema_check]
            has_new_schema = "run_avg_pace_seconds_per_km" in column_names
            has_old_schema = "main_avg_pace_seconds_per_km" in column_names

            if has_new_schema:
                # Use new schema (run/cooldown)
                perf_trends = conn.execute(
                    """
                    SELECT
                        pace_consistency,
                        hr_drift_percentage,
                        cadence_consistency,
                        fatigue_pattern,
                        warmup_avg_pace_seconds_per_km,
                        warmup_avg_hr,
                        run_avg_pace_seconds_per_km,
                        run_avg_hr,
                        recovery_avg_pace_seconds_per_km,
                        recovery_avg_hr,
                        cooldown_avg_pace_seconds_per_km,
                        cooldown_avg_hr
                    FROM performance_trends
                    WHERE activity_id = ?
                    """,
                    [activity_id],
                ).fetchone()
            elif has_old_schema:
                # Use old schema (main/finish) - map to new naming
                perf_trends = conn.execute(
                    """
                    SELECT
                        pace_consistency,
                        hr_drift_percentage,
                        cadence_consistency,
                        fatigue_pattern,
                        warmup_avg_pace_seconds_per_km,
                        warmup_avg_hr,
                        main_avg_pace_seconds_per_km,
                        main_avg_hr,
                        NULL,
                        NULL,
                        finish_avg_pace_seconds_per_km,
                        finish_avg_hr
                    FROM performance_trends
                    WHERE activity_id = ?
                    """,
                    [activity_id],
                ).fetchone()
            else:
                perf_trends = None

            # Load HR efficiency (for training type)
            hr_eff = conn.execute(
                """
                SELECT training_type
                FROM hr_efficiency
                WHERE activity_id = ?
                """,
                [activity_id],
            ).fetchone()

            conn.close()

            # Construct data structure
            data = {
                "activity_name": result[0],
                "location_name": result[1],
                "basic_metrics": {
                    "distance_km": result[2],
                    "duration_seconds": result[3],
                    "avg_pace_seconds_per_km": result[4],
                    "avg_heart_rate": result[5],
                    "avg_cadence": result[6] if result[6] is not None else 0,
                    "avg_power": result[7] if result[7] is not None else 0,
                },
                "weight_kg": result[8],
                "weather_data": {
                    "external_temp_c": result[9],
                    "humidity": result[10],
                    "wind_speed_ms": result[11],
                },
                "gear_name": result[12],
            }

            # Add form efficiency if available
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
                # Check if recovery data exists (4-phase) or not (3-phase)
                if perf_trends[8] is not None:
                    # 4-phase structure (interval training)
                    data["run_metrics"] = {
                        "avg_pace_seconds_per_km": perf_trends[6],
                        "avg_hr": perf_trends[7],
                        "pace_consistency": perf_trends[0],
                    }
                    data["recovery_metrics"] = {
                        "avg_pace_seconds_per_km": perf_trends[8],
                        "avg_hr": perf_trends[9],
                    }
                    data["cooldown_metrics"] = {
                        "avg_pace_seconds_per_km": perf_trends[10],
                        "avg_hr": perf_trends[11],
                        "fatigue_pattern": perf_trends[3],
                    }
                else:
                    # 3-phase structure (regular run)
                    # Map to new naming: run (was main), cooldown (was finish)
                    data["run_metrics"] = {
                        "avg_pace_seconds_per_km": perf_trends[6],
                        "avg_hr": perf_trends[7],
                        "pace_consistency": perf_trends[0],
                    }
                    data["cooldown_metrics"] = {
                        "avg_pace_seconds_per_km": perf_trends[10],
                        "avg_hr": perf_trends[11],
                        "fatigue_pattern": perf_trends[3],
                    }
                    # Legacy naming for backward compatibility
                    data["main_metrics"] = data["run_metrics"]
                    data["finish_metrics"] = data["cooldown_metrics"]

            # Add training type if available
            if hr_eff:
                data["training_type"] = hr_eff[0]

            return data

        except Exception as e:
            logger.error(f"Error loading performance data: {e}")
            return None

    def load_section_analyses(
        self, activity_id: int
    ) -> dict[str, dict[str, Any]] | None:
        """
        Load section analyses from DuckDB matching actual data structures.

        Actual structure in DuckDB:
        - efficiency: {"efficiency": "..."}
        - environment: {"environmental": "..."}
        - phase: {"warmup_evaluation": "...", "main_evaluation": "...", "finish_evaluation": "..."}
        - split: {"analyses": {...}}
        - summary: {"activity_type": "...", "summary": "...", "recommendations": "..."}

        Args:
            activity_id: Activity ID

        Returns:
            Section analyses dict or None
        """
        logger.info("[2/4] Loading section analyses from DuckDB...")

        analyses = {}

        # Load efficiency analysis
        efficiency_data = self.db_reader.get_section_analysis(activity_id, "efficiency")
        if efficiency_data:
            analyses["efficiency"] = efficiency_data.get("efficiency", {})
        else:
            logger.warning("Warning: efficiency section analysis missing")

        # Load environment analysis (key is "environmental" not "environment_analysis")
        environment_data = self.db_reader.get_section_analysis(
            activity_id, "environment"
        )
        if environment_data:
            analyses["environment_analysis"] = environment_data.get("environmental", {})
        else:
            logger.warning("Warning: environment section analysis missing")

        # Load phase analysis (support both 3-phase and 4-phase structures)
        phase_data = self.db_reader.get_section_analysis(activity_id, "phase")
        if phase_data:
            # Detect structure: 4-phase (interval) or 3-phase (regular)
            if "recovery_evaluation" in phase_data:
                # 4-phase structure (warmup/run/recovery/cooldown)
                analyses["phase_evaluation"] = {
                    "warmup": {"evaluation": phase_data.get("warmup_evaluation", "")},
                    "run": {"evaluation": phase_data.get("run_evaluation", "")},
                    "recovery": {
                        "evaluation": phase_data.get("recovery_evaluation", "")
                    },
                    "cooldown": {
                        "evaluation": phase_data.get("cooldown_evaluation", "")
                    },
                }
            elif "run_evaluation" in phase_data:
                # 3-phase structure with new naming (warmup/run/cooldown)
                analyses["phase_evaluation"] = {
                    "warmup": {"evaluation": phase_data.get("warmup_evaluation", "")},
                    "run": {"evaluation": phase_data.get("run_evaluation", "")},
                    "cooldown": {
                        "evaluation": phase_data.get("cooldown_evaluation", "")
                    },
                }
            else:
                # Legacy 3-phase structure (warmup/main/finish)
                analyses["phase_evaluation"] = {
                    "warmup": {"evaluation": phase_data.get("warmup_evaluation", "")},
                    "main": {"evaluation": phase_data.get("main_evaluation", "")},
                    "finish": {"evaluation": phase_data.get("finish_evaluation", "")},
                }
        else:
            logger.warning("Warning: phase section analysis missing")

        # Load split analysis (key is "analyses" not "split_analysis")
        split_data = self.db_reader.get_section_analysis(activity_id, "split")
        if split_data:
            analyses["split_analysis"] = split_data.get("analyses", {})
        else:
            logger.warning("Warning: split section analysis missing or empty")

        # Load summary analysis
        summary_data = self.db_reader.get_section_analysis(activity_id, "summary")
        if summary_data:
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

        import duckdb

        try:
            conn = duckdb.connect(str(self.db_reader.db_path), read_only=True)

            # Load splits data from splits table
            result = conn.execute(
                """
                SELECT
                    split_index,
                    distance,
                    pace_seconds_per_km,
                    heart_rate,
                    cadence,
                    power,
                    ground_contact_time,
                    vertical_oscillation,
                    vertical_ratio,
                    elevation_gain,
                    elevation_loss,
                    pace_str
                FROM splits
                WHERE activity_id = ?
                ORDER BY split_index
                """,
                [activity_id],
            ).fetchall()

            conn.close()

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
                        "pace_formatted": (
                            row[11] if row[11] else "N/A"
                        ),  # Use pace_str from DB
                        "heart_rate": row[3],
                        "cadence": row[4],
                        "power": row[5],
                        "ground_contact_time": row[6],
                        "vertical_oscillation": row[7],
                        "vertical_ratio": row[8],
                        "elevation_gain": row[9],
                        "elevation_loss": row[10],
                    }
                )

            return splits

        except Exception as e:
            logger.error(f"Error loading splits data: {e}")
            return None

    def generate_report(
        self, activity_id: int, date: str | None = None
    ) -> dict[str, Any]:
        """
        Generate final report from performance.json and section analyses.

        Args:
            activity_id: Activity ID
            date: Activity date (YYYY-MM-DD format)

        Returns:
            Report generation result with path
        """
        # Resolve date if not provided
        if not date:
            date = self.db_reader.get_activity_date(activity_id)
            if not date:
                raise ValueError(f"Could not resolve date for activity {activity_id}")

        # Load data
        performance_data = self.load_performance_data(activity_id)
        if not performance_data:
            raise ValueError(f"No performance data found for activity {activity_id}")

        section_analyses = self.load_section_analyses(activity_id)

        if not section_analyses:
            raise ValueError(
                f"No section analyses found for activity {activity_id}. Cannot generate report."
            )

        # Load splits data for split analysis基本データ表示
        splits_data = self.load_splits_data(activity_id)

        logger.info("[3/4] Generating report from section analyses...")

        # Format pace values for display
        def format_pace(pace_seconds_per_km):
            if pace_seconds_per_km is None or pace_seconds_per_km == 0:
                return "N/A"
            minutes = int(pace_seconds_per_km // 60)
            seconds = int(pace_seconds_per_km % 60)
            return f"{minutes}:{seconds:02d}"

        # Add formatted pace values
        if "warmup_metrics" in performance_data:
            performance_data["warmup_metrics"]["avg_pace_formatted"] = format_pace(
                performance_data["warmup_metrics"].get("avg_pace_seconds_per_km")
            )
        if "run_metrics" in performance_data:
            performance_data["run_metrics"]["avg_pace_formatted"] = format_pace(
                performance_data["run_metrics"].get("avg_pace_seconds_per_km")
            )
        if "recovery_metrics" in performance_data:
            performance_data["recovery_metrics"]["avg_pace_formatted"] = format_pace(
                performance_data["recovery_metrics"].get("avg_pace_seconds_per_km")
            )
        if "cooldown_metrics" in performance_data:
            performance_data["cooldown_metrics"]["avg_pace_formatted"] = format_pace(
                performance_data["cooldown_metrics"].get("avg_pace_seconds_per_km")
            )
        # Legacy support
        if "main_metrics" in performance_data:
            performance_data["main_metrics"]["avg_pace_formatted"] = format_pace(
                performance_data["main_metrics"].get("avg_pace_seconds_per_km")
            )
        if "finish_metrics" in performance_data:
            performance_data["finish_metrics"]["avg_pace_formatted"] = format_pace(
                performance_data["finish_metrics"].get("avg_pace_seconds_per_km")
            )

        # Prepare template context
        context = {
            "activity_id": str(activity_id),
            "date": date,
            "activity_name": performance_data.get("activity_name"),
            "location_name": performance_data.get("location_name"),
            "basic_metrics": performance_data.get("basic_metrics", {}),
            "weight_kg": performance_data.get("weight_kg"),
            "weather_data": performance_data.get("weather_data", {}),
            "gear_name": performance_data.get("gear_name"),
            "form_efficiency": performance_data.get("form_efficiency"),
            "performance_metrics": performance_data.get("performance_metrics"),
            "training_type": performance_data.get("training_type"),
            "warmup_metrics": performance_data.get("warmup_metrics"),
            "run_metrics": performance_data.get("run_metrics"),
            "recovery_metrics": performance_data.get("recovery_metrics"),
            "cooldown_metrics": performance_data.get("cooldown_metrics"),
            "main_metrics": performance_data.get("main_metrics"),  # Legacy
            "finish_metrics": performance_data.get("finish_metrics"),  # Legacy
            "splits": splits_data,
            "efficiency": section_analyses.get("efficiency"),
            "environment_analysis": section_analyses.get("environment_analysis"),
            "phase_evaluation": section_analyses.get("phase_evaluation"),
            "split_analysis": section_analyses.get("split_analysis"),
            "summary": section_analyses.get("summary"),
        }

        # Render report using Jinja2 template with all data
        report_content = self.renderer.render_report(**context)

        logger.info("[4/4] Saving report to result/individual/...")

        # Save report
        save_result = self.renderer.save_report(str(activity_id), date, report_content)

        return {
            "success": True,
            "activity_id": activity_id,
            "date": date,
            "report_path": save_result["path"],
            "timestamp": datetime.now().isoformat(),
        }


def main():
    """Main entry point for report generator worker."""
    import sys

    if len(sys.argv) < 2:
        print(
            "Usage: python -m tools.reporting.report_generator_worker <activity_id> [date]"
        )
        sys.exit(1)

    activity_id = int(sys.argv[1])
    date = sys.argv[2] if len(sys.argv) > 2 else None

    worker = ReportGeneratorWorker()
    result = worker.generate_report(activity_id, date)

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
