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
                analysis_id INTEGER PRIMARY KEY,
                activity_id BIGINT NOT NULL,
                activity_date DATE NOT NULL,
                section_type VARCHAR NOT NULL,
                analysis_data VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                agent_name VARCHAR,
                agent_version VARCHAR,
                FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
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
        weight_kg: float | None = None,
        weight_source: str | None = None,
        weight_method: str | None = None,
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
            weight_kg: Weight in kg (7-day median for W/kg calculation)
            weight_source: Weight data source (e.g., "statistical_7d_median")
            weight_method: Weight calculation method (e.g., "median")
            **kwargs: Additional metrics

        Returns:
            True if successful
        """
        try:
            conn = duckdb.connect(str(self.db_path))

            conn.execute(
                """
                INSERT OR REPLACE INTO activities
                (activity_id, date, activity_name, location_name,
                 total_distance_km, total_time_seconds, avg_pace_seconds_per_km, avg_heart_rate,
                 weight_kg, weight_source, weight_method)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                [
                    activity_id,
                    activity_date,
                    activity_name,
                    location_name,
                    kwargs.get("distance_km"),
                    kwargs.get("duration_seconds"),
                    kwargs.get("avg_pace_seconds_per_km"),
                    kwargs.get("avg_heart_rate"),
                    weight_kg,
                    weight_source,
                    weight_method,
                ],
            )

            conn.close()
            logger.info(
                f"Inserted activity {activity_id} metadata (weight: {weight_kg:.3f} kg)"
                if weight_kg
                else f"Inserted activity {activity_id} metadata"
            )
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

            # Get next analysis_id
            max_id_result = conn.execute(
                "SELECT COALESCE(MAX(analysis_id), 0) FROM section_analyses"
            ).fetchone()
            next_analysis_id = max_id_result[0] + 1 if max_id_result else 1

            # Extract metadata
            metadata = analysis_data.get("metadata", {})
            agent_name = metadata.get("analyst")  # 'analyst' field maps to 'agent_name'
            agent_version = metadata.get(
                "version"
            )  # 'version' field maps to 'agent_version'

            conn.execute(
                """
                INSERT INTO section_analyses
                (analysis_id, activity_id, activity_date, section_type, analysis_data, agent_name, agent_version)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                [
                    next_analysis_id,
                    activity_id,
                    activity_date,
                    section_type,
                    json.dumps(analysis_data),
                    agent_name,
                    agent_version,
                ],
            )

            conn.close()
            logger.info(f"Inserted {section_type} analysis for activity {activity_id}")
            return True
        except Exception as e:
            logger.error(f"Error inserting section analysis: {e}")
            return False

    def insert_body_composition(self, date: str, weight_data: dict) -> bool:
        """
        Insert body composition data from weight_cache raw data.

        Args:
            date: Date in YYYY-MM-DD format
            weight_data: Raw weight data dict from Garmin API

        Returns:
            True if successful
        """
        try:
            conn = duckdb.connect(str(self.db_path))

            # Extract data from dateWeightList (first entry)
            date_weight_list = weight_data.get("dateWeightList", [])
            if not date_weight_list:
                logger.warning(f"No weight data found for {date}")
                return False

            data = date_weight_list[0]

            # Get next measurement_id
            max_id_result = conn.execute(
                "SELECT COALESCE(MAX(measurement_id), 0) FROM body_composition"
            ).fetchone()
            next_measurement_id = max_id_result[0] + 1 if max_id_result else 1

            # Convert grams to kg for consistency
            weight_kg = data.get("weight", 0) / 1000.0 if data.get("weight") else None
            muscle_mass_kg = (
                data.get("muscleMass", 0) / 1000.0 if data.get("muscleMass") else None
            )
            bone_mass_kg = (
                data.get("boneMass", 0) / 1000.0 if data.get("boneMass") else None
            )

            conn.execute(
                """
                INSERT OR REPLACE INTO body_composition
                (measurement_id, date, weight_kg, body_fat_percentage, muscle_mass_kg,
                 bone_mass_kg, bmi, hydration_percentage, basal_metabolic_rate,
                 active_metabolic_rate, metabolic_age, visceral_fat_rating,
                 physique_rating, measurement_source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                [
                    next_measurement_id,
                    date,
                    weight_kg,
                    data.get("bodyFat"),
                    muscle_mass_kg,
                    bone_mass_kg,
                    data.get("bmi"),
                    data.get("bodyWater"),
                    None,  # basal_metabolic_rate not in raw data
                    None,  # active_metabolic_rate not in raw data
                    data.get("metabolicAge"),
                    data.get("visceralFat"),
                    data.get("physiqueRating"),
                    data.get("sourceType", "INDEX_SCALE"),
                ],
            )

            conn.close()
            logger.info(f"Inserted body composition data for {date}")
            return True
        except Exception as e:
            logger.error(f"Error inserting body composition data: {e}")
            return False
