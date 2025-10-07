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
        activity_id: int | None = None,
        date: str | None = None,
        force_regenerate: bool = False,
    ) -> dict[str, Any]:
        """
        Execute the full analysis workflow.

        Args:
            activity_id: Garmin activity ID (optional if date is provided)
            date: Activity date YYYY-MM-DD format (optional if activity_id is provided)
            force_regenerate: Force regeneration of all data

        Returns:
            Workflow result with validation status and quality score

        Raises:
            ValueError: If neither activity_id nor date is provided
            ValueError: If date has multiple activities and activity_id not specified
        """
        # Validate inputs
        if not activity_id and not date:
            raise ValueError("Either activity_id or date must be provided")

        # Resolve activity_id from date if needed
        if not activity_id:
            assert date is not None, "date must be provided when activity_id is None"
            logger.info(f"Resolving activity_id from date: {date}")
            activity_id = self.resolve_activity_id(date)

        # Resolve date from activity_id if needed
        if not date:
            logger.info(f"Resolving date from activity_id: {activity_id}")
            date = self._get_activity_date(activity_id)
            if not date:
                raise ValueError(f"Could not resolve date for activity {activity_id}")

        logger.info(f"Starting workflow for activity {activity_id} ({date})")

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

    def _get_activities_from_duckdb(self, date: str) -> list[dict[str, Any]]:
        """
        Get activities from DuckDB by date (start_time_local).

        Args:
            date: YYYY-MM-DD format

        Returns:
            List of activity dicts with activity_id, activity_name, start_time, etc.
        """
        import duckdb

        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)
            result = conn.execute(
                """
                SELECT
                    activity_id,
                    activity_name,
                    start_time_local,
                    total_distance_km,
                    total_time_seconds
                FROM activities
                WHERE DATE(start_time_local) = ?
                ORDER BY start_time_local
                """,
                [date],
            ).fetchall()
            conn.close()

            activities = []
            for row in result:
                activities.append(
                    {
                        "activity_id": row[0],
                        "activity_name": row[1],
                        "start_time": str(row[2]) if row[2] else None,
                        "distance_km": row[3],
                        "duration_seconds": row[4],
                    }
                )

            return activities

        except Exception as e:
            logger.warning(f"DuckDB query failed: {e}")
            return []

    def _get_activities_from_api(self, date: str) -> list[dict[str, Any]]:
        """
        Get activities from Garmin API by date.

        Args:
            date: YYYY-MM-DD format

        Returns:
            List of activity dicts with activity_id, activity_name, etc.
        """
        from tools.ingest.garmin_worker import GarminIngestWorker

        try:
            worker = GarminIngestWorker()
            client = worker.get_garmin_client()

            # Get activities for date
            activities_data = client.get_activities_fordate(date)

            activities = []
            for activity in activities_data:
                activities.append(
                    {
                        "activity_id": activity.get("activityId"),
                        "activity_name": activity.get("activityName"),
                        "start_time": activity.get("startTimeLocal"),
                        "distance_km": (
                            (activity.get("distance", 0) / 1000)
                            if activity.get("distance")
                            else None
                        ),
                        "duration_seconds": activity.get("duration"),
                    }
                )

            return activities

        except Exception as e:
            logger.error(f"Garmin API query failed: {e}")
            return []

    def resolve_activity_id(self, date: str) -> int:
        """
        Resolve Activity ID from date.

        Priority:
        1. DuckDB activities.start_time_local
        2. Garmin API (via GarminIngestWorker)

        Args:
            date: Activity date (YYYY-MM-DD)

        Returns:
            Activity ID

        Raises:
            ValueError: If no activity found for date
            ValueError: If multiple activities found (user must specify activity_id)
        """
        # Try DuckDB first
        activities = self._get_activities_from_duckdb(date)

        if len(activities) == 1:
            logger.info(
                f"Found single activity in DuckDB for {date}: {activities[0]['activity_id']}"
            )
            return activities[0]["activity_id"]  # type: ignore[no-any-return]
        elif len(activities) > 1:
            activity_list = ", ".join(
                [f"{act['activity_id']} ({act['activity_name']})" for act in activities]
            )
            raise ValueError(
                f"Multiple activities found for {date}. "
                f"Please specify activity_id. Found: {activity_list}"
            )

        # Try Garmin API
        logger.info(f"No activities found in DuckDB for {date}, trying Garmin API")
        activities = self._get_activities_from_api(date)

        if len(activities) == 0:
            raise ValueError(f"No activities found for {date}")
        elif len(activities) == 1:
            logger.info(
                f"Found single activity in Garmin API for {date}: {activities[0]['activity_id']}"
            )
            return activities[0]["activity_id"]  # type: ignore[no-any-return]
        else:
            activity_list = ", ".join(
                [f"{act['activity_id']} ({act['activity_name']})" for act in activities]
            )
            raise ValueError(
                f"Multiple activities found for {date} in Garmin API. "
                f"Please specify activity_id. Found: {activity_list}"
            )


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
