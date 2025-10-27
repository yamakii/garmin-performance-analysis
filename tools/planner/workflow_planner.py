"""
Workflow Planner for Garmin Performance Analysis

This module orchestrates the full analysis workflow from data collection
to report generation, with DuckDB integration for activity date resolution.
"""

import json
import logging
from datetime import datetime
from typing import Any

from tools.database.db_reader import GarminDBReader

logger = logging.getLogger(__name__)


class WorkflowPlanner:
    """
    Orchestrates the full analysis workflow.

    Workflow:
    1. Data collection (GarminIngestWorker)
    2. Data validation
    3. Section analyses (5 agents in parallel)
    4. Report generation
    """

    def __init__(self, db_path: str | None = None):
        """Initialize workflow planner with optional DuckDB path."""
        if db_path is None:
            from tools.utils.paths import get_default_db_path

            db_path = get_default_db_path()

        self.db_path = db_path
        self.db_reader = GarminDBReader(self.db_path)

    def execute_full_workflow(
        self,
        date: str,
        force_regenerate: bool = False,
    ) -> dict[str, Any]:
        """
        Execute the full analysis workflow.

        Args:
            date: Activity date YYYY-MM-DD format
            force_regenerate: Force regeneration of all data

        Returns:
            Workflow result with validation status and quality score

        Raises:
            ValueError: If no activity found for date
            ValueError: If multiple activities found (user must specify activity_id)
        """
        from tools.form_baseline.evaluator import evaluate_and_store
        from tools.ingest.garmin_worker import GarminIngestWorker

        logger.info(f"Starting workflow for date: {date}")

        worker = GarminIngestWorker(db_path=self.db_path)

        # Step 1: Data collection and DuckDB insertion (via save_data)
        logger.info(f"Processing activity by date: {date}")
        ingest_result = worker.process_activity_by_date(date)
        activity_id = ingest_result["activity_id"]
        date = ingest_result["date"]

        if ingest_result["status"] != "success":
            raise ValueError(
                f"Data collection failed: {ingest_result.get('error', 'Unknown error')}"
            )

        # Step 2: Form evaluation (NEW)
        logger.info(f"Evaluating form metrics for activity {activity_id}")
        form_evaluation_status = "not_evaluated"
        try:
            evaluation_result = evaluate_and_store(
                activity_id=activity_id,
                activity_date=date,
                db_path=str(self.db_path),
            )
            form_evaluation_status = "success"
            logger.info(
                f"Form evaluation complete: overall_score={evaluation_result['overall_score']:.1f}/5.0"
            )
        except FileNotFoundError as e:
            # Model file not found - expected during Phase 1 development
            logger.warning(f"Form evaluation skipped: {e}")
            form_evaluation_status = "model_not_found"
        except ValueError as e:
            # Missing splits data or other data issues
            logger.error(f"Form evaluation failed: {e}")
            form_evaluation_status = "failed"
        except Exception as e:
            # Unexpected errors should not break the workflow
            logger.error(f"Form evaluation unexpected error: {e}", exc_info=True)
            form_evaluation_status = "error"

        # Step 3: Data validation (precheck.json removed - using defaults)
        validation_status = "passed"
        quality_score = 1.0

        result = {
            "activity_id": activity_id,
            "date": date,
            "validation_status": validation_status,
            "quality_score": quality_score,
            "form_evaluation_status": form_evaluation_status,  # NEW
            "files": ingest_result["files"],
            "timestamp": datetime.now().isoformat(),
        }

        logger.info(
            f"Workflow completed: validation={validation_status}, "
            f"quality={quality_score}, form_evaluation={form_evaluation_status}"
        )
        return result


def main():
    """Main entry point for workflow planner."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m tools.planner.workflow_planner <date>")
        print("Example: python -m tools.planner.workflow_planner 2025-10-05")
        sys.exit(1)

    date = sys.argv[1]

    planner = WorkflowPlanner()
    result = planner.execute_full_workflow(date)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
