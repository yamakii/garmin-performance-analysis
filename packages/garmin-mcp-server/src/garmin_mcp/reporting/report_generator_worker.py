"""
Report Generator Worker

Reads performance data from DuckDB and generates final Markdown report.
Python Worker for report generation from section analyses.
"""

import json
import logging
from datetime import datetime
from typing import Any

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.reporting.components.chart_generator import ChartGenerator
from garmin_mcp.reporting.components.data_loader import ReportDataLoader
from garmin_mcp.reporting.components.formatting import (
    extract_phase_ratings,
    format_pace,
    get_activity_type_display,
    get_training_type_category,
)
from garmin_mcp.reporting.components.insight_generator import InsightGenerator
from garmin_mcp.reporting.components.physiological_calculator import (
    PhysiologicalCalculator,
)
from garmin_mcp.reporting.components.workout_comparator import (
    WorkoutComparator,
)
from garmin_mcp.reporting.quality_gate import QualityGate
from garmin_mcp.reporting.report_template_renderer import ReportTemplateRenderer

logger = logging.getLogger(__name__)


class ReportGeneratorWorker:
    """Python Worker for report generation from section analyses."""

    def __init__(self, db_path: str | None = None):
        """
        Initialize report generator worker.

        Args:
            db_path: DuckDB database path (default: uses environment variable)
        """
        if db_path is None:
            from garmin_mcp.utils.paths import get_default_db_path

            db_path = get_default_db_path()

        self.db_reader = GarminDBReader(db_path)
        self.renderer = ReportTemplateRenderer()

        # Initialize component instances
        self._data_loader = ReportDataLoader(self.db_reader)
        self._chart_generator = ChartGenerator(self.db_reader)
        self._physiological_calculator = PhysiologicalCalculator(self.db_reader)
        self._workout_comparator = WorkoutComparator(self.db_reader)
        self._insight_generator = InsightGenerator()

    # =========================================================================
    # Delegating methods (backward-compatible thin wrappers)
    # =========================================================================

    def load_performance_data(self, activity_id: int) -> dict[str, Any] | None:
        """Load all performance data from DuckDB. Delegates to ReportDataLoader."""
        return self._data_loader.load_performance_data(
            activity_id,
            comparator=self._workout_comparator,
            physiological_calculator=self._physiological_calculator,
            chart_generator=self._chart_generator,
            insight_generator=self._insight_generator,
        )

    def load_section_analyses(
        self, activity_id: int, performance_data: dict[str, Any] | None = None
    ) -> dict[str, dict[str, Any]] | None:
        """Load section analyses from DuckDB. Delegates to ReportDataLoader."""
        return self._data_loader.load_section_analyses(
            activity_id,
            performance_data=performance_data,
            physiological_calculator=self._physiological_calculator,
        )

    def load_splits_data(self, activity_id: int) -> list[dict[str, Any]] | None:
        """Load splits data from splits table. Delegates to ReportDataLoader."""
        return self._data_loader.load_splits_data(activity_id)

    def _load_splits(self, activity_id: int) -> list[dict[str, Any]]:
        """Load splits from DuckDB. Delegates to ReportDataLoader."""
        return self._data_loader.load_splits(activity_id)

    def _generate_mermaid_data(
        self, splits: list[dict[str, Any]] | None
    ) -> dict[str, Any] | None:
        """Generate Mermaid graph data from splits. Delegates to ChartGenerator."""
        return self._chart_generator.generate_mermaid_data(splits)

    def _generate_mermaid_analysis(
        self, splits: list[dict[str, Any]], training_type_category: str
    ) -> str | None:
        """Generate Work/Recovery transition analysis. Delegates to ChartGenerator."""
        return self._chart_generator.generate_mermaid_analysis(
            splits, training_type_category
        )

    def _generate_hr_zone_pie_data(self, activity_id: int) -> str | None:
        """Generate Mermaid pie chart data. Delegates to ChartGenerator."""
        return self._chart_generator.generate_hr_zone_pie_data(activity_id)

    def _calculate_physiological_indicators(
        self,
        training_type_category: str,
        vo2_max_data: dict[str, Any] | None,
        lactate_threshold_data: dict[str, Any] | None,
        run_metrics: dict[str, Any],
        hr_zone_times: list[tuple[int, float]] | None = None,
    ) -> dict[str, Any]:
        """Calculate physiological indicators. Delegates to PhysiologicalCalculator."""
        return self._physiological_calculator.calculate_physiological_indicators(
            training_type_category,
            vo2_max_data,
            lactate_threshold_data,
            run_metrics,
            hr_zone_times,
        )

    def _calculate_run_phase_power_stride(
        self, activity_id: int
    ) -> dict[str, float | None]:
        """Calculate run phase power/stride. Delegates to PhysiologicalCalculator."""
        return self._physiological_calculator.calculate_run_phase_power_stride(
            activity_id
        )

    def _calculate_power_stride_baselines(
        self,
        activity_id: int,
        similar_workouts: dict[str, Any] | None = None,
        training_type: str | None = None,
    ) -> dict[str, float | None]:
        """Calculate baselines. Delegates to PhysiologicalCalculator."""
        return self._physiological_calculator.calculate_power_stride_baselines(
            activity_id, similar_workouts, training_type
        )

    def _calculate_pace_corrected_form_efficiency(
        self,
        avg_pace_seconds_per_km: float,
        form_eff: dict[str, Any],
        run_power: float | None = None,
        run_stride: float | None = None,
        baseline_power: float | None = None,
        baseline_stride: float | None = None,
    ) -> dict[str, Any]:
        """Calculate pace-corrected form efficiency. Delegates to PhysiologicalCalculator."""
        return self._physiological_calculator.calculate_pace_corrected_form_efficiency(
            avg_pace_seconds_per_km,
            form_eff,
            run_power,
            run_stride,
            baseline_power,
            baseline_stride,
        )

    def _build_form_efficiency_table(
        self, pace_corrected_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Build form efficiency table. Delegates to PhysiologicalCalculator."""
        return self._physiological_calculator.build_form_efficiency_table(
            pace_corrected_data
        )

    def _get_comparison_pace(
        self, performance_data: dict[str, Any]
    ) -> tuple[float, str]:
        """Get comparison pace. Delegates to WorkoutComparator."""
        return self._workout_comparator.get_comparison_pace(performance_data)

    def _get_evaluation_target_text(self, training_type_category: str) -> str:
        """Get evaluation target text. Delegates to WorkoutComparator."""
        return self._workout_comparator.get_evaluation_target_text(
            training_type_category
        )

    def _load_similar_workouts(
        self, activity_id: int, current_metrics: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Load similar workouts. Delegates to WorkoutComparator."""
        return self._workout_comparator.load_similar_workouts(
            activity_id, current_metrics
        )

    def _generate_comparison_insights(
        self, activity_id: int, performance_data: dict[str, Any]
    ) -> list[str]:
        """Generate comparison insights. Delegates to WorkoutComparator."""
        return self._workout_comparator.generate_comparison_insights(
            activity_id, performance_data
        )

    def _generate_workout_insight(
        self, similar_workouts: dict[str, Any], training_type: str
    ) -> str:
        """Generate workout insight. Delegates to InsightGenerator."""
        return self._insight_generator.generate_workout_insight(
            similar_workouts, training_type
        )

    def _extract_numeric_change(self, change_text: str) -> float:
        """Extract numeric change. Delegates to InsightGenerator."""
        return self._insight_generator.extract_numeric_change(change_text)

    def _extract_numeric_value(self, value_text: str) -> float | None:
        """Extract numeric value. Delegates to InsightGenerator."""
        return self._insight_generator.extract_numeric_value(value_text)

    def _generate_reference_info(
        self,
        vo2_max_data: dict[str, Any] | None,
        lactate_threshold_data: dict[str, Any] | None,
        training_type: str = "aerobic_base",
    ) -> str:
        """Generate reference info. Delegates to InsightGenerator."""
        return self._insight_generator.generate_reference_info(
            vo2_max_data, lactate_threshold_data, training_type
        )

    def _format_pace(self, pace_seconds_per_km: float) -> str:
        """Format pace as MM:SS/km. Delegates to formatting module."""
        return format_pace(pace_seconds_per_km)

    def _get_activity_type_display(self, training_type: str) -> dict[str, str]:
        """Get activity type display. Delegates to formatting module."""
        return get_activity_type_display(training_type)

    def _get_training_type_category(self, training_type: str) -> str:
        """Get training type category. Delegates to formatting module."""
        return get_training_type_category(training_type)

    def _extract_phase_ratings(
        self, section_analyses: dict[str, Any]
    ) -> dict[str, Any]:
        """Extract phase ratings. Delegates to formatting module."""
        return extract_phase_ratings(section_analyses)

    # =========================================================================
    # Core methods (remain in this class)
    # =========================================================================

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

        section_analyses = self.load_section_analyses(activity_id, performance_data)

        # Load form evaluations (Phase 5: Unified Form Evaluation System)
        form_evaluation = self.db_reader.get_form_evaluations(activity_id)

        if not section_analyses:
            raise ValueError(
                f"No section analyses found for activity {activity_id}. Cannot generate report."
            )

        # Load splits data for split analysis
        splits_data = self.load_splits_data(activity_id)

        # Extract phase evaluation ratings for header display
        phase_ratings = self._extract_phase_ratings(section_analyses)

        # Generate workout comparison insights if summary exists
        if "summary" in section_analyses and section_analyses["summary"]:
            try:
                insights = self._generate_comparison_insights(
                    activity_id, performance_data
                )

                if insights and "key_strengths" in section_analyses["summary"]:
                    section_analyses["summary"]["key_strengths"] = (
                        insights + section_analyses["summary"]["key_strengths"]
                    )
            except Exception as e:
                logger.warning(f"Could not generate workout insights: {e}")

        logger.info("[3/4] Generating report from section analyses...")

        # Format pace values for display
        def _format_pace_display(pace_seconds_per_km: float | None) -> str:
            if pace_seconds_per_km is None or pace_seconds_per_km == 0:
                return "N/A"
            minutes = int(pace_seconds_per_km // 60)
            seconds = int(pace_seconds_per_km % 60)
            return f"{minutes}:{seconds:02d}"

        # Add formatted pace values
        if "warmup_metrics" in performance_data:
            performance_data["warmup_metrics"]["avg_pace_formatted"] = (
                _format_pace_display(
                    performance_data["warmup_metrics"].get("avg_pace_seconds_per_km")
                )
            )
        if "run_metrics" in performance_data:
            performance_data["run_metrics"]["avg_pace_formatted"] = (
                _format_pace_display(
                    performance_data["run_metrics"].get("avg_pace_seconds_per_km")
                )
            )
        if "recovery_metrics" in performance_data:
            performance_data["recovery_metrics"]["avg_pace_formatted"] = (
                _format_pace_display(
                    performance_data["recovery_metrics"].get("avg_pace_seconds_per_km")
                )
            )
        if "cooldown_metrics" in performance_data:
            performance_data["cooldown_metrics"]["avg_pace_formatted"] = (
                _format_pace_display(
                    performance_data["cooldown_metrics"].get("avg_pace_seconds_per_km")
                )
            )
        # Generate heart rate zone pie chart data
        hr_zone_pie_data = self._generate_hr_zone_pie_data(activity_id)

        # Extract split highlights
        split_analysis_data = section_analyses.get("split_analysis", {})
        highlights_list = split_analysis_data.get("highlights", "N/A")

        # Generate interval graph analysis (for interval workouts only)
        training_type = performance_data.get("training_type", "aerobic_base")
        training_type_category = self._get_training_type_category(training_type)
        interval_graph_analysis = None
        if training_type_category == "interval_sprint" and splits_data:
            interval_graph_analysis = self._generate_mermaid_analysis(
                splits_data, training_type_category
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
            "form_evaluation": form_evaluation,
            "performance_metrics": performance_data.get("performance_metrics"),
            "training_type": performance_data.get("training_type"),
            "training_type_category": training_type_category,
            "activity_type": self._get_activity_type_display(
                performance_data.get("training_type", "aerobic_base")
            ),
            "warmup_metrics": performance_data.get("warmup_metrics"),
            "run_metrics": performance_data.get("run_metrics"),
            "recovery_metrics": performance_data.get("recovery_metrics"),
            "cooldown_metrics": performance_data.get("cooldown_metrics"),
            "splits": splits_data,
            "efficiency": section_analyses.get("efficiency"),
            "environment_analysis": section_analyses.get("environment_analysis"),
            "phase_evaluation": section_analyses.get("phase_evaluation"),
            "split_analysis": section_analyses.get("split_analysis"),
            "summary": section_analyses.get("summary"),
            "similar_workouts": performance_data.get("similar_workouts"),
            "mermaid_data": performance_data.get("mermaid_data"),
            "interval_graph_analysis": interval_graph_analysis,
            "heart_rate_zone_pie_data": hr_zone_pie_data,
            "highlights_list": highlights_list,
            "reference_info": performance_data.get("reference_info"),
            "vo2_max_data": performance_data.get("vo2_max_data"),
            "lactate_threshold_data": performance_data.get("lactate_threshold_data"),
            "show_physiological": training_type_category
            in ["tempo_threshold", "interval_sprint"],
            "vo2_max_utilization": performance_data.get("vo2_max_utilization"),
            "vo2_max_utilization_eval": performance_data.get(
                "vo2_max_utilization_eval"
            ),
            "threshold_pace_formatted": performance_data.get(
                "threshold_pace_formatted"
            ),
            "threshold_pace_comparison": performance_data.get(
                "threshold_pace_comparison"
            ),
            "ftp_percentage": performance_data.get("ftp_percentage"),
            "work_avg_power": performance_data.get("work_avg_power"),
            "power_zone_name": performance_data.get("power_zone_name"),
            "vo2_max_expected_effect": performance_data.get("vo2_max_expected_effect"),
            "threshold_expected_effect": performance_data.get(
                "threshold_expected_effect"
            ),
            **phase_ratings,
        }

        # Advisory quality gate validation
        quality_gate = QualityGate()
        quality_result = quality_gate.validate(section_analyses)
        if not quality_result.passed:
            logger.warning(
                "QualityGate: %d warning(s) detected for activity %s",
                len(quality_result.warnings),
                activity_id,
            )

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
            "quality_warnings": [
                {"check": w.check_name, "message": w.message}
                for w in quality_result.warnings
            ],
        }


def main() -> None:
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
