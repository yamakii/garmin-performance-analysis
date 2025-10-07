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
        Load performance data from DuckDB.

        Args:
            activity_id: Activity ID

        Returns:
            Performance data dict or None
        """
        logger.info("[1/4] Loading performance data from DuckDB...")

        # Load basic metrics for overview section
        basic_metrics = self.db_reader.get_performance_section(
            activity_id, "basic_metrics"
        )

        if not basic_metrics:
            logger.warning(
                f"Warning: No performance data found in DuckDB for activity {activity_id}"
            )
            return None

        return {"basic_metrics": basic_metrics}

    def load_section_analyses(
        self, activity_id: int
    ) -> dict[str, dict[str, Any]] | None:
        """
        Load section analyses from DuckDB matching agent output structures.

        Expected structure (from agent definitions):
        - Efficiency: {"efficiency": {"form_efficiency": {}, "hr_efficiency": {}}}
        - Environment: {"environment_analysis": {"weather_conditions": {}, ...}}
        - Phase: {"phase_evaluation": {"warmup": {}, "main": {}, "finish": {}, "overall": {}}}
        - Split: {"split_analysis": {"splits": [], "patterns": {}}}
        - Summary: {"summary": {"activity_type": {}, "overall_rating": {}, ...}}

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

        # Load environment analysis
        environment_data = self.db_reader.get_section_analysis(
            activity_id, "environment"
        )
        if environment_data:
            analyses["environment_analysis"] = environment_data.get(
                "environment_analysis", {}
            )
        else:
            logger.warning("Warning: environment section analysis missing")

        # Load phase analysis
        phase_data = self.db_reader.get_section_analysis(activity_id, "phase")
        if phase_data:
            analyses["phase_evaluation"] = phase_data.get("phase_evaluation", {})
        else:
            logger.warning("Warning: phase section analysis missing")

        # Load split analysis
        split_data = self.db_reader.get_section_analysis(activity_id, "split")
        if split_data:
            analyses["split_analysis"] = split_data.get("split_analysis", {})
        else:
            logger.warning("Warning: split section analysis missing or empty")

        # Load summary analysis
        summary_data = self.db_reader.get_section_analysis(activity_id, "summary")
        if summary_data:
            analyses["summary"] = summary_data.get("summary", {})
        else:
            logger.warning("Warning: summary section analysis missing")

        if not analyses:
            logger.warning("Warning: No section analyses found in DuckDB")
            return None

        return analyses

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

        logger.info("[3/4] Generating report from section analyses...")

        # Extract basic_metrics from performance_data
        basic_metrics = performance_data.get("basic_metrics", {})

        # Render report using Jinja2 template with JSON data
        report_content = self.renderer.render_report(
            activity_id=str(activity_id),
            date=date,
            basic_metrics=basic_metrics,
            section_analyses=section_analyses,
        )

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
