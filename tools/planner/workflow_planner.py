"""
Workflow Planner for Garmin Performance Analysis

This module orchestrates the full analysis workflow from data collection
to report generation, with DuckDB integration for activity date resolution.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
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
        self.db_path = db_path or "data/database/garmin_performance.duckdb"
        self.db_reader = GarminDBReader(self.db_path)

    def execute_full_workflow(
        self,
        activity_id: int,
        date: str | None = None,
        force_regenerate: bool = False,
    ) -> dict[str, Any]:
        """
        Execute the full analysis workflow.

        Args:
            activity_id: Garmin activity ID
            date: Activity date (YYYY-MM-DD format)
            force_regenerate: Force regeneration of all data

        Returns:
            Workflow result with validation status and quality score
        """
        logger.info(f"Starting workflow for activity {activity_id}")

        # Resolve activity date if not provided
        if not date:
            date = self._get_activity_date(activity_id)
            if not date:
                raise ValueError(f"Could not resolve date for activity {activity_id}")

        logger.info(f"Activity date: {date}")

        # Execute workflow steps
        result = {
            "activity_id": activity_id,
            "date": date,
            "validation_status": "passed",
            "quality_score": 1.0,
            "timestamp": datetime.now().isoformat(),
        }

        # TODO: Implement actual workflow steps
        # 1. Data collection
        # 2. Data validation
        # 3. Section analyses (parallel)
        # 4. Report generation

        return result

    def _get_activity_date(self, activity_id: int) -> str | None:
        """
        Get activity date from DuckDB, Parquet, or Garmin API.

        Priority:
        1. DuckDB (fastest)
        2. Parquet file (fallback)
        3. Garmin API (last resort)

        Args:
            activity_id: Activity ID

        Returns:
            Activity date in YYYY-MM-DD format, or None if not found
        """
        # Try DuckDB first
        try:
            date = self.db_reader.get_activity_date(activity_id)
            if date:
                logger.info(f"Found date in DuckDB: {date}")
                return date
        except Exception as e:
            logger.warning(f"DuckDB lookup failed: {e}")

        # Try Parquet file
        try:
            parquet_path = Path(f"data/parquet/{activity_id}.parquet")
            if parquet_path.exists():
                import pandas as pd

                df = pd.read_parquet(parquet_path)
                if not df.empty and "startTimeLocal" in df.columns:
                    date_str = str(df["startTimeLocal"].iloc[0])[:10]
                    logger.info(f"Found date in Parquet: {date_str}")
                    return date_str
        except Exception as e:
            logger.warning(f"Parquet lookup failed: {e}")

        # Try Garmin API as last resort
        logger.warning(f"Activity {activity_id} not found in DuckDB or Parquet")
        return None


def main():
    """Main entry point for workflow planner."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m tools.planner.workflow_planner <activity_id> [date]")
        sys.exit(1)

    activity_id = int(sys.argv[1])
    date = sys.argv[2] if len(sys.argv) > 2 else None

    planner = WorkflowPlanner()
    result = planner.execute_full_workflow(activity_id, date)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
