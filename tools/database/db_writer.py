"""
DuckDB Writer for Garmin Performance Data

Provides write operations to DuckDB for inserting performance data.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)


class GarminDBWriter:
    """Write operations to DuckDB for Garmin performance data."""

    def __init__(self, db_path: str | None = None):
        """Initialize DuckDB writer with database path."""
        if db_path is None:
            from tools.utils.paths import get_database_dir

            db_path = str(get_database_dir() / "garmin_performance.duckdb")

        self.db_path = Path(db_path)
        self._ensure_tables()

    def _ensure_tables(self):
        """Ensure required tables exist with normalized schema.

        Creates:
        - activities: Base activity metadata (36 columns)
        - splits: Split-by-split metrics (foreign key to activities)
        - form_efficiency: Form efficiency summary (GCT, VO, VR)
        - heart_rate_zones: HR zone data (5 rows per activity)
        - hr_efficiency: HR efficiency analysis
        - performance_trends: Performance trends (4-phase: warmup/run/recovery/cooldown)
        - vo2_max: VO2 max estimation
        - lactate_threshold: Lactate threshold metrics
        - body_composition: Body composition measurements (weight, BMI, body fat %)
        - section_analyses: Section analysis data

        Note: Schemas match those defined in individual inserters to ensure compatibility.
        """
        conn = duckdb.connect(str(self.db_path))

        # Create activities table with production schema (36 columns)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS activities (
                activity_id BIGINT PRIMARY KEY,
                date DATE NOT NULL,
                activity_name VARCHAR,
                start_time_local TIMESTAMP,
                start_time_gmt TIMESTAMP,
                total_time_seconds INTEGER,
                total_distance_km DOUBLE,
                avg_pace_seconds_per_km DOUBLE,
                avg_heart_rate INTEGER,
                max_heart_rate INTEGER,
                avg_cadence INTEGER,
                avg_power INTEGER,
                normalized_power INTEGER,
                cadence_stability DOUBLE,
                power_efficiency DOUBLE,
                pace_variability DOUBLE,
                aerobic_te DOUBLE,
                anaerobic_te DOUBLE,
                training_effect_source VARCHAR,
                power_to_weight DOUBLE,
                weight_kg DOUBLE,
                weight_source VARCHAR,
                weight_method VARCHAR,
                stability_score DOUBLE,
                external_temp_c DOUBLE,
                external_temp_f DOUBLE,
                humidity INTEGER,
                wind_speed_ms DOUBLE,
                wind_direction_compass VARCHAR,
                gear_name VARCHAR,
                gear_type VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_elevation_gain DOUBLE,
                total_elevation_loss DOUBLE,
                location_name VARCHAR
            )
        """
        )

        # Create splits table (from inserters/splits.py) with time range columns
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS splits (
                activity_id BIGINT,
                split_index INTEGER,
                distance DOUBLE,
                duration_seconds DOUBLE,
                start_time_gmt VARCHAR,
                start_time_s INTEGER,
                end_time_s INTEGER,
                intensity_type VARCHAR,
                role_phase VARCHAR,
                pace_str VARCHAR,
                pace_seconds_per_km DOUBLE,
                heart_rate INTEGER,
                hr_zone VARCHAR,
                cadence DOUBLE,
                cadence_rating VARCHAR,
                power DOUBLE,
                power_efficiency VARCHAR,
                stride_length DOUBLE,
                ground_contact_time DOUBLE,
                vertical_oscillation DOUBLE,
                vertical_ratio DOUBLE,
                elevation_gain DOUBLE,
                elevation_loss DOUBLE,
                terrain_type VARCHAR,
                environmental_conditions VARCHAR,
                wind_impact VARCHAR,
                temp_impact VARCHAR,
                environmental_impact VARCHAR,
                PRIMARY KEY (activity_id, split_index),
                FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
            )
        """
        )

        # Create form_efficiency table (from inserters/form_efficiency.py)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS form_efficiency (
                activity_id BIGINT PRIMARY KEY,
                gct_average DOUBLE,
                gct_min DOUBLE,
                gct_max DOUBLE,
                gct_std DOUBLE,
                gct_variability DOUBLE,
                gct_rating VARCHAR,
                gct_evaluation VARCHAR,
                vo_average DOUBLE,
                vo_min DOUBLE,
                vo_max DOUBLE,
                vo_std DOUBLE,
                vo_trend VARCHAR,
                vo_rating VARCHAR,
                vo_evaluation VARCHAR,
                vr_average DOUBLE,
                vr_min DOUBLE,
                vr_max DOUBLE,
                vr_std DOUBLE,
                vr_rating VARCHAR,
                vr_evaluation VARCHAR,
                FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
            )
        """
        )

        # Create heart_rate_zones table (from inserters/heart_rate_zones.py)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS heart_rate_zones (
                activity_id BIGINT,
                zone_number INTEGER,
                zone_low_boundary INTEGER,
                zone_high_boundary INTEGER,
                time_in_zone_seconds DOUBLE,
                zone_percentage DOUBLE,
                PRIMARY KEY (activity_id, zone_number),
                FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
            )
        """
        )

        # Create hr_efficiency table (from inserters/hr_efficiency.py)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hr_efficiency (
                activity_id BIGINT PRIMARY KEY,
                primary_zone VARCHAR,
                zone_distribution_rating VARCHAR,
                hr_stability VARCHAR,
                aerobic_efficiency VARCHAR,
                training_quality VARCHAR,
                zone2_focus BOOLEAN,
                zone4_threshold_work BOOLEAN,
                training_type VARCHAR,
                zone1_percentage DOUBLE,
                zone2_percentage DOUBLE,
                zone3_percentage DOUBLE,
                zone4_percentage DOUBLE,
                zone5_percentage DOUBLE,
                FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
            )
        """
        )

        # Create performance_trends table with 4-phase schema (from inserters/performance_trends.py)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS performance_trends (
                activity_id BIGINT PRIMARY KEY,
                pace_consistency DOUBLE,
                hr_drift_percentage DOUBLE,
                cadence_consistency VARCHAR,
                fatigue_pattern VARCHAR,
                warmup_splits VARCHAR,
                warmup_avg_pace_seconds_per_km DOUBLE,
                warmup_avg_pace_str VARCHAR,
                warmup_avg_hr DOUBLE,
                warmup_avg_cadence DOUBLE,
                warmup_avg_power DOUBLE,
                warmup_evaluation VARCHAR,
                run_splits VARCHAR,
                run_avg_pace_seconds_per_km DOUBLE,
                run_avg_pace_str VARCHAR,
                run_avg_hr DOUBLE,
                run_avg_cadence DOUBLE,
                run_avg_power DOUBLE,
                run_evaluation VARCHAR,
                recovery_splits VARCHAR,
                recovery_avg_pace_seconds_per_km DOUBLE,
                recovery_avg_pace_str VARCHAR,
                recovery_avg_hr DOUBLE,
                recovery_avg_cadence DOUBLE,
                recovery_avg_power DOUBLE,
                recovery_evaluation VARCHAR,
                cooldown_splits VARCHAR,
                cooldown_avg_pace_seconds_per_km DOUBLE,
                cooldown_avg_pace_str VARCHAR,
                cooldown_avg_hr DOUBLE,
                cooldown_avg_cadence DOUBLE,
                cooldown_avg_power DOUBLE,
                cooldown_evaluation VARCHAR,
                FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
            )
        """
        )

        # Create vo2_max table (from inserters/vo2_max.py)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vo2_max (
                activity_id BIGINT PRIMARY KEY,
                precise_value DOUBLE,
                value DOUBLE,
                date DATE,
                category INTEGER,
                FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
            )
        """
        )

        # Create lactate_threshold table (from inserters/lactate_threshold.py)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lactate_threshold (
                activity_id BIGINT PRIMARY KEY,
                heart_rate INTEGER,
                speed_mps DOUBLE,
                date_hr TIMESTAMP,
                functional_threshold_power INTEGER,
                power_to_weight DOUBLE,
                weight DOUBLE,
                date_power TIMESTAMP,
                FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
            )
        """
        )

        # Create body_composition table (from inserters/body_composition.py)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS body_composition (
                measurement_id INTEGER PRIMARY KEY,
                date DATE NOT NULL,
                weight_kg DOUBLE,
                body_fat_percentage DOUBLE,
                muscle_mass_kg DOUBLE,
                bone_mass_kg DOUBLE,
                bmi DOUBLE,
                hydration_percentage DOUBLE,
                measurement_source VARCHAR
            )
        """
        )

        # form_baselines table removed - replaced by form_baseline_history

        # Create form_baseline_history table (for trend analysis)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS form_baseline_history (
                history_id INTEGER PRIMARY KEY,
                user_id VARCHAR DEFAULT 'default',
                condition_group VARCHAR DEFAULT 'flat_road',
                metric VARCHAR,
                model_type VARCHAR,

                coef_alpha FLOAT,
                coef_d FLOAT,
                coef_a FLOAT,
                coef_b FLOAT,

                period_start DATE NOT NULL,
                period_end DATE NOT NULL,
                trained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                n_samples INTEGER,
                rmse FLOAT,
                speed_range_min FLOAT,
                speed_range_max FLOAT,

                UNIQUE(user_id, condition_group, metric, period_start, period_end)
            )
        """
        )

        # Create form_evaluations table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS form_evaluations (
                eval_id INTEGER PRIMARY KEY,
                activity_id BIGINT UNIQUE,

                gct_ms_expected FLOAT,
                vo_cm_expected FLOAT,
                vr_pct_expected FLOAT,

                gct_ms_actual FLOAT,
                vo_cm_actual FLOAT,
                vr_pct_actual FLOAT,

                gct_delta_pct FLOAT,
                vo_delta_cm FLOAT,
                vr_delta_pct FLOAT,

                gct_penalty FLOAT,
                gct_star_rating VARCHAR,
                gct_score FLOAT,
                gct_needs_improvement BOOLEAN,
                gct_evaluation_text TEXT,

                vo_penalty FLOAT,
                vo_star_rating VARCHAR,
                vo_score FLOAT,
                vo_needs_improvement BOOLEAN,
                vo_evaluation_text TEXT,

                vr_penalty FLOAT,
                vr_star_rating VARCHAR,
                vr_score FLOAT,
                vr_needs_improvement BOOLEAN,
                vr_evaluation_text TEXT,

                cadence_actual FLOAT,
                cadence_minimum INTEGER DEFAULT 180,
                cadence_achieved BOOLEAN,

                overall_score FLOAT,
                overall_star_rating VARCHAR,

                evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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

        # Create sequence for form_evaluations if it doesn't exist
        try:
            conn.execute("SELECT nextval('form_evaluations_seq')")
        except Exception:
            # Sequence doesn't exist, create it
            max_id_result = conn.execute(
                "SELECT COALESCE(MAX(eval_id), 0) FROM form_evaluations"
            ).fetchone()
            start_value = max_id_result[0] + 1 if max_id_result else 1
            conn.execute(
                f"CREATE SEQUENCE IF NOT EXISTS form_evaluations_seq START {start_value}"
            )

        # Create sequence for form_baseline_history if it doesn't exist
        try:
            conn.execute("SELECT nextval('form_baseline_history_seq')")
        except Exception:
            # Sequence doesn't exist, create it
            max_id_result = conn.execute(
                "SELECT COALESCE(MAX(history_id), 0) FROM form_baseline_history"
            ).fetchone()
            start_value = max_id_result[0] + 1 if max_id_result else 1
            conn.execute(
                f"CREATE SEQUENCE IF NOT EXISTS form_baseline_history_seq START {start_value}"
            )

        # Create sequence for section_analyses if it doesn't exist
        try:
            conn.execute("SELECT nextval('seq_section_analyses_id')")
        except Exception:
            # Sequence doesn't exist, create it
            # Get max existing analysis_id to start sequence from there
            max_id_result = conn.execute(
                "SELECT COALESCE(MAX(analysis_id), 0) FROM section_analyses"
            ).fetchone()
            start_value = max_id_result[0] + 1 if max_id_result else 1
            conn.execute(
                f"CREATE SEQUENCE IF NOT EXISTS seq_section_analyses_id START {start_value}"
            )

        # Create UNIQUE index on (activity_id, section_type) if it doesn't exist
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_activity_section
            ON section_analyses(activity_id, section_type)
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
        Insert activity metadata into production schema (36 columns).

        Args:
            activity_id: Activity ID
            activity_date: Activity date (YYYY-MM-DD)
            activity_name: Activity name
            location_name: Location name
            activity_type: Activity type
            weight_kg: Weight in kg (7-day median for W/kg calculation)
            weight_source: Weight data source (e.g., "statistical_7d_median")
            weight_method: Weight calculation method (e.g., "median")
            **kwargs: Additional metrics (distance_km, duration_seconds, etc.)

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
        REMOVED: This method is deprecated and no longer needed.

        The performance_data JSON table has been replaced with normalized tables.
        Use individual inserter functions directly:
        - insert_splits()
        - insert_form_efficiency()
        - insert_heart_rate_zones()
        - insert_hr_efficiency()
        - insert_performance_trends()
        - insert_vo2_max()
        - insert_lactate_threshold()

        These are called automatically by GarminIngestWorker.save_data().
        """
        raise NotImplementedError(
            "insert_performance_data() has been removed. "
            "Use individual inserter functions (insert_splits, insert_form_efficiency, etc.) "
            "which are called automatically by GarminIngestWorker.save_data()."
        )

    def insert_section_analysis(
        self,
        activity_id: int,
        activity_date: str,
        section_type: str,
        analysis_data: dict,
        agent_name: str | None = None,
        agent_version: str = "1.0",
    ) -> bool:
        """
        Insert or replace section analysis data with auto-generated metadata.

        UPSERT logic: Deletes existing record for (activity_id, section_type)
        before inserting new data to maintain 1:1 relationship.

        Args:
            activity_id: Activity ID
            activity_date: Activity date (YYYY-MM-DD)
            section_type: Section type (efficiency, environment, phase, split, summary)
            analysis_data: Analysis data dict (metadata will be auto-added if not present)
            agent_name: Optional agent name (defaults to {section_type}-section-analyst)
            agent_version: Agent version (defaults to "1.0")

        Returns:
            True if successful
        """
        try:
            conn = duckdb.connect(str(self.db_path))

            # Start transaction
            conn.begin()

            try:
                # UPSERT Step 1: Get next analysis_id from sequence (thread-safe)
                # Note: ON CONFLICT時は使用されず、既存のanalysis_idが保持される
                next_analysis_id = conn.execute(
                    "SELECT nextval('seq_section_analyses_id')"
                ).fetchone()[0]

                # Auto-generate metadata if not present
                if "metadata" not in analysis_data:
                    # Determine agent name from section_type
                    if agent_name is None:
                        agent_name = f"{section_type}-section-analyst"

                    # Generate metadata
                    metadata = {
                        "activity_id": str(activity_id),
                        "date": activity_date,
                        "analyst": agent_name,
                        "version": agent_version,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }

                    # Add metadata to analysis_data
                    analysis_data_with_metadata = {
                        "metadata": metadata,
                        **analysis_data,
                    }
                else:
                    # Use existing metadata
                    analysis_data_with_metadata = analysis_data
                    metadata = analysis_data["metadata"]
                    agent_name = metadata.get("analyst", agent_name)
                    agent_version = metadata.get("version", agent_version)

                # UPSERT Step 2: Insert or Update using ON CONFLICT
                conn.execute(
                    """
                    INSERT INTO section_analyses
                    (analysis_id, activity_id, activity_date, section_type, analysis_data, agent_name, agent_version)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (activity_id, section_type)
                    DO UPDATE SET
                        analysis_data = EXCLUDED.analysis_data,
                        agent_name = EXCLUDED.agent_name,
                        agent_version = EXCLUDED.agent_version
                """,
                    [
                        next_analysis_id,
                        activity_id,
                        activity_date,
                        section_type,
                        json.dumps(analysis_data_with_metadata),
                        agent_name,
                        agent_version,
                    ],
                )

                # Commit transaction
                conn.commit()
                conn.close()
                logger.info(
                    f"Upserted {section_type} analysis for activity {activity_id} (replaced existing if any)"
                )
                return True

            except Exception as e:
                # Rollback on error
                conn.rollback()
                conn.close()
                raise e

        except Exception as e:
            logger.error(f"Error upserting section analysis: {e}")
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

            # Schema cleanup: Remove device-unprovided metabolic fields
            for column in [
                "basal_metabolic_rate",
                "active_metabolic_rate",
                "metabolic_age",
                "visceral_fat_rating",
                "physique_rating",
            ]:
                try:
                    conn.execute(f"ALTER TABLE body_composition DROP COLUMN {column}")
                except Exception:
                    pass  # Column already removed or never existed

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
                 bone_mass_kg, bmi, hydration_percentage, measurement_source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    data.get("sourceType", "INDEX_SCALE"),
                ],
            )

            conn.close()
            logger.info(f"Inserted body composition data for {date}")
            return True
        except Exception as e:
            logger.error(f"Error inserting body composition data: {e}")
            return False
