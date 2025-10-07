"""
DuckDB Writer for Garmin Performance Data

Provides write operations to DuckDB for inserting performance data.
"""

import json
import logging
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)


class GarminDBWriter:
    """Write operations to DuckDB for Garmin performance data."""

    def __init__(self, db_path: str = "data/database/garmin_performance.duckdb"):
        """Initialize DuckDB writer with database path."""
        self.db_path = Path(db_path)
        self._ensure_tables()

    def _ensure_tables(self):
        """Ensure required tables exist."""
        conn = duckdb.connect(str(self.db_path))

        # Create activities table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS activities (
                activity_id BIGINT PRIMARY KEY,
                activity_date DATE NOT NULL,
                activity_name VARCHAR,
                location_name VARCHAR,
                activity_type VARCHAR,
                distance_km DOUBLE,
                duration_seconds DOUBLE,
                avg_pace_seconds_per_km DOUBLE,
                avg_heart_rate DOUBLE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Create performance_data table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS performance_data (
                activity_id BIGINT PRIMARY KEY,
                activity_date DATE NOT NULL,
                basic_metrics JSON,
                heart_rate_zones JSON,
                hr_efficiency_analysis JSON,
                form_efficiency_summary JSON,
                performance_trends JSON,
                split_metrics JSON,
                efficiency_metrics JSON,
                training_effect JSON,
                power_to_weight JSON,
                lactate_threshold JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
            )
        """
        )

        # Create section_analyses table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS section_analyses (
                id INTEGER PRIMARY KEY,
                activity_id BIGINT NOT NULL,
                activity_date DATE NOT NULL,
                section_type VARCHAR NOT NULL,
                analysis_data JSON NOT NULL,
                analyst VARCHAR,
                version VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (activity_id) REFERENCES activities(activity_id),
                UNIQUE (activity_id, section_type)
            )
        """
        )

        conn.close()

    def insert_activity(
        self,
        activity_id: int,
        activity_date: str,
        activity_name: str | None = None,
        location_name: str | None = None,
        activity_type: str | None = None,
        **kwargs,
    ) -> bool:
        """
        Insert activity metadata.

        Args:
            activity_id: Activity ID
            activity_date: Activity date (YYYY-MM-DD)
            activity_name: Activity name
            location_name: Location name
            activity_type: Activity type
            **kwargs: Additional metrics

        Returns:
            True if successful
        """
        try:
            conn = duckdb.connect(str(self.db_path))

            conn.execute(
                """
                INSERT OR REPLACE INTO activities
                (activity_id, activity_date, activity_name, location_name, activity_type,
                 distance_km, duration_seconds, avg_pace_seconds_per_km, avg_heart_rate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                [
                    activity_id,
                    activity_date,
                    activity_name,
                    location_name,
                    activity_type,
                    kwargs.get("distance_km"),
                    kwargs.get("duration_seconds"),
                    kwargs.get("avg_pace_seconds_per_km"),
                    kwargs.get("avg_heart_rate"),
                ],
            )

            conn.close()
            logger.info(f"Inserted activity {activity_id} metadata")
            return True
        except Exception as e:
            logger.error(f"Error inserting activity: {e}")
            return False

    def insert_performance_data(
        self, activity_id: int, activity_date: str, performance_data: dict
    ) -> bool:
        """
        Insert performance data from performance.json.

        Args:
            activity_id: Activity ID
            activity_date: Activity date (YYYY-MM-DD)
            performance_data: Performance data dict

        Returns:
            True if successful
        """
        try:
            conn = duckdb.connect(str(self.db_path))

            # Extract sections
            basic_metrics = json.dumps(performance_data.get("basic_metrics", {}))
            heart_rate_zones = json.dumps(performance_data.get("heart_rate_zones", {}))
            hr_efficiency = json.dumps(
                performance_data.get("hr_efficiency_analysis", {})
            )
            form_efficiency = json.dumps(
                performance_data.get("form_efficiency_summary", {})
            )
            performance_trends = json.dumps(
                performance_data.get("performance_trends", {})
            )
            split_metrics = json.dumps(performance_data.get("split_metrics", {}))
            efficiency_metrics = json.dumps(
                performance_data.get("efficiency_metrics", {})
            )
            training_effect = json.dumps(performance_data.get("training_effect", {}))
            power_to_weight = json.dumps(performance_data.get("power_to_weight", {}))
            lactate_threshold = json.dumps(
                performance_data.get("lactate_threshold", {})
            )

            conn.execute(
                """
                INSERT OR REPLACE INTO performance_data
                (activity_id, activity_date, basic_metrics, heart_rate_zones,
                 hr_efficiency_analysis, form_efficiency_summary, performance_trends,
                 split_metrics, efficiency_metrics, training_effect, power_to_weight,
                 lactate_threshold)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                [
                    activity_id,
                    activity_date,
                    basic_metrics,
                    heart_rate_zones,
                    hr_efficiency,
                    form_efficiency,
                    performance_trends,
                    split_metrics,
                    efficiency_metrics,
                    training_effect,
                    power_to_weight,
                    lactate_threshold,
                ],
            )

            conn.close()
            logger.info(f"Inserted performance data for activity {activity_id}")
            return True
        except Exception as e:
            logger.error(f"Error inserting performance data: {e}")
            return False

    def insert_section_analysis(
        self,
        activity_id: int,
        activity_date: str,
        section_type: str,
        analysis_data: dict,
    ) -> bool:
        """
        Insert section analysis data.

        Args:
            activity_id: Activity ID
            activity_date: Activity date (YYYY-MM-DD)
            section_type: Section type (efficiency, environment, phase, split, summary)
            analysis_data: Analysis data dict

        Returns:
            True if successful
        """
        try:
            conn = duckdb.connect(str(self.db_path))

            # Extract metadata
            metadata = analysis_data.get("metadata", {})
            analyst = metadata.get("analyst")
            version = metadata.get("version")

            conn.execute(
                """
                INSERT OR REPLACE INTO section_analyses
                (activity_id, activity_date, section_type, analysis_data, analyst, version)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                [
                    activity_id,
                    activity_date,
                    section_type,
                    json.dumps(analysis_data),
                    analyst,
                    version,
                ],
            )

            conn.close()
            logger.info(f"Inserted {section_type} analysis for activity {activity_id}")
            return True
        except Exception as e:
            logger.error(f"Error inserting section analysis: {e}")
            return False
