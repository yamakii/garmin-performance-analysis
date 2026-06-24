"""
DuckDB Writer for Garmin Performance Data

Provides write operations to DuckDB for inserting performance data.
"""

import json
import logging
from datetime import UTC, datetime

from garmin_mcp.database.connection import get_db_path, get_write_connection

logger = logging.getLogger(__name__)


def _body_comp_row(date: str, weight_data: dict) -> dict | None:
    """Build a normalized body_composition row dict from raw weight data.

    Extracts the first ``dateWeightList`` entry and converts gram-based fields
    (weight / muscleMass / boneMass) to kilograms. Shared by
    ``GarminDBWriter.insert_body_composition`` and the backfill script so the
    table is the single source of truth for body composition.

    Args:
        date: Date in YYYY-MM-DD format.
        weight_data: Raw weight data dict from Garmin API.

    Returns:
        Row dict with keys ``date, weight_kg, body_fat_percentage,
        muscle_mass_kg, bone_mass_kg, bmi, hydration_percentage,
        measurement_source`` or ``None`` if ``dateWeightList`` is empty.
    """
    date_weight_list = weight_data.get("dateWeightList", [])
    if not date_weight_list:
        return None

    data = date_weight_list[0]

    weight_kg = data.get("weight", 0) / 1000.0 if data.get("weight") else None
    muscle_mass_kg = (
        data.get("muscleMass", 0) / 1000.0 if data.get("muscleMass") else None
    )
    bone_mass_kg = data.get("boneMass", 0) / 1000.0 if data.get("boneMass") else None

    return {
        "date": date,
        "weight_kg": weight_kg,
        "body_fat_percentage": data.get("bodyFat"),
        "muscle_mass_kg": muscle_mass_kg,
        "bone_mass_kg": bone_mass_kg,
        "bmi": data.get("bmi"),
        "hydration_percentage": data.get("bodyWater"),
        "measurement_source": data.get("sourceType", "INDEX_SCALE"),
    }


def _wellness_row(date: str, wellness_data: dict) -> dict | None:
    """Build a normalized daily_wellness row from merged wellness data.

    Maps the merged shape produced by
    :func:`garmin_mcp.ingest.raw_data_fetcher.collect_wellness_data` (keys
    ``stats``, ``hrv``, ``sleep``, ``training_readiness``) onto the
    ``daily_wellness`` columns. Every sub-source is null-safe: a missing /
    empty section leaves its fields ``None`` (e.g. a device-off day with only
    a resting HR).

    Args:
        date: Date in ``YYYY-MM-DD`` format.
        wellness_data: Merged wellness dict (any subset of the four sections).

    Returns:
        Row dict keyed by the ``daily_wellness`` columns, or ``None`` when no
        metric at all could be extracted (all sections empty).
    """
    stats = wellness_data.get("stats") or {}
    hrv = wellness_data.get("hrv") or {}
    sleep = wellness_data.get("sleep") or {}
    readiness_raw = wellness_data.get("training_readiness") or []

    # training_readiness is a list of entries; take the first if present.
    if isinstance(readiness_raw, list):
        readiness = readiness_raw[0] if readiness_raw else {}
    else:
        readiness = readiness_raw or {}

    # HRV: overnight average, status, and baseline band.
    hrv_summary = hrv.get("hrvSummary") or {}
    hrv_overnight_ms = hrv_summary.get("lastNightAvg") or hrv.get("lastNightAvg")
    hrv_status = hrv_summary.get("status") or hrv.get("status")
    hrv_baseline = hrv_summary.get("baseline") or hrv.get("baseline") or {}
    hrv_baseline_low = hrv_baseline.get("lowUpper")
    hrv_baseline_high = hrv_baseline.get("balancedUpper")

    # Sleep: nested under dailySleepDTO in the raw payload, with a flat
    # fallback for already-flattened test fixtures.
    sleep_dto = sleep.get("dailySleepDTO") or {}
    sleep_seconds = sleep_dto.get("sleepTimeSeconds") or sleep.get("sleepTimeSeconds")
    sleep_scores = sleep_dto.get("sleepScores") or {}
    sleep_overall = sleep_scores.get("overall") or {}
    sleep_score = sleep_overall.get("value") or sleep.get("sleepScore")

    training_readiness = readiness.get("score")

    resting_hr = stats.get("restingHeartRate")
    body_battery_high = stats.get("bodyBatteryHighestValue")
    body_battery_low = stats.get("bodyBatteryLowestValue")
    stress_avg = stats.get("averageStressLevel")

    row = {
        "date": date,
        "resting_hr": resting_hr,
        "hrv_overnight_ms": hrv_overnight_ms,
        "hrv_status": hrv_status,
        "hrv_baseline_low": hrv_baseline_low,
        "hrv_baseline_high": hrv_baseline_high,
        "sleep_seconds": sleep_seconds,
        "sleep_score": sleep_score,
        "training_readiness": training_readiness,
        "body_battery_high": body_battery_high,
        "body_battery_low": body_battery_low,
        "stress_avg": stress_avg,
        "source": "garmin",
    }

    # If no metric could be extracted at all, treat the day as empty.
    metric_keys = [k for k in row if k not in ("date", "source")]
    if all(row[k] is None for k in metric_keys):
        return None

    return row


class GarminDBWriter:
    """Write operations to DuckDB for Garmin performance data."""

    def __init__(self, db_path: str | None = None):
        """Initialize DuckDB writer with database path."""
        self.db_path = get_db_path(db_path)
        self._ensure_tables()
        self._run_migrations()

    def _ensure_tables(self):
        """Create the base DuckDB schema (the 15 core tables).

        This method owns the *base* schema only. It is the first step of
        ``__init__`` and is immediately followed by ``_run_migrations()``,
        which applies incremental migrations (column additions, the
        athlete-centric tables, index drops, etc.).

        Creates (15 base tables):
        - activities: Base activity metadata (19 columns)
        - splits: Split-by-split metrics (28 columns, NO FK)
        - form_efficiency: Form efficiency summary (GCT, VO, VR, NO FK)
        - heart_rate_zones: HR zone data (5 rows per activity, NO FK)
        - hr_efficiency: HR efficiency analysis (NO FK)
        - performance_trends: Performance trends (4-phase, NO FK)
        - vo2_max: VO2 max estimation (NO FK)
        - lactate_threshold: Lactate threshold metrics (NO FK)
        - body_composition: Body composition measurements (independent table)
        - section_analyses: Section analysis data (NO FK)
        - form_evaluations: Form evaluation results (NO FK)
        - form_baseline_history: Baseline trend history (independent table)
        - time_series_metrics: Second-by-second metrics (26 metrics)
        - training_plans: Training plan metadata (versioned)
        - planned_workouts: Individual workout definitions

        Tables owned exclusively by migrations (NOT created here):
        - athlete_profile / athlete_goals / season_retrospectives /
          weekly_reviews and their sequences -> migrations/add_athlete_tables.py
          (schema version 7). See issue #342 for the single-source-of-truth
          rationale.

        Change Log:
        - 2025-11-01: Removed FK constraints from 9 child tables
          Reason: Single data source + bulk writes + LEFT JOINs only
          Data integrity enforced at application layer
        - 2026-06-19 (#342): Moved athlete-centric table DDL out of this method;
          it is now owned solely by migrations/add_athlete_tables.py to remove
          duplicate DDL.

        Note: ``CREATE TABLE IF NOT EXISTS`` keeps this method idempotent, so
        re-instantiating ``GarminDBWriter`` on an existing database is a no-op.
        """
        with get_write_connection(self.db_path) as conn:
            # Create activities table (matches inserters/activities.py - 19 columns)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS activities (
                activity_id BIGINT PRIMARY KEY,
                activity_date DATE NOT NULL,
                activity_name VARCHAR,
                start_time_local TIMESTAMP,
                start_time_gmt TIMESTAMP,
                location_name VARCHAR,
                total_distance_km DOUBLE,
                total_time_seconds INTEGER,
                avg_speed_ms DOUBLE,
                avg_pace_seconds_per_km DOUBLE,
                avg_heart_rate INTEGER,
                max_heart_rate INTEGER,
                temp_celsius DOUBLE,
                relative_humidity_percent DOUBLE,
                wind_speed_kmh DOUBLE,
                wind_direction VARCHAR,
                gear_type VARCHAR,
                gear_model VARCHAR,
                base_weight_kg DOUBLE
            )
        """)

            # Create splits table (from inserters/splits.py) with time range columns
            conn.execute("""
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
                    max_heart_rate INTEGER,
                    max_cadence DOUBLE,
                    max_power DOUBLE,
                    normalized_power DOUBLE,
                    average_speed DOUBLE,
                    grade_adjusted_speed DOUBLE,
                    PRIMARY KEY (activity_id, split_index)
                    -- FK constraint removed (2025-11-01): Single data source + bulk writes only
                )
            """)

            # Create form_efficiency table (from inserters/form_efficiency.py)
            conn.execute("""
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
                    vr_evaluation VARCHAR
                    -- FK constraint removed (2025-11-01): Data integrity enforced at application layer
                )
            """)

            # Create heart_rate_zones table (from inserters/heart_rate_zones.py)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS heart_rate_zones (
                    activity_id BIGINT,
                    zone_number INTEGER,
                    zone_low_boundary INTEGER,
                    zone_high_boundary INTEGER,
                    time_in_zone_seconds DOUBLE,
                    zone_percentage DOUBLE,
                    PRIMARY KEY (activity_id, zone_number)
                    -- FK constraint removed (2025-11-01): Data integrity enforced at application layer
                )
            """)

            # Create hr_efficiency table (from inserters/hr_efficiency.py)
            conn.execute("""
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
                    zone5_percentage DOUBLE
                    -- FK constraint removed (2025-11-01): Data integrity enforced at application layer
                )
            """)

            # Create performance_trends table with 4-phase schema (from inserters/performance_trends.py)
            conn.execute("""
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
                    cooldown_evaluation VARCHAR
                    -- FK constraint removed (2025-11-01): Data integrity enforced at application layer
                )
            """)

            # Create vo2_max table (from inserters/vo2_max.py)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS vo2_max (
                    activity_id BIGINT PRIMARY KEY,
                    precise_value DOUBLE,
                    value DOUBLE,
                    date DATE,
                    category INTEGER
                    -- FK constraint removed (2025-11-01): Data integrity enforced at application layer
                )
            """)

            # Create lactate_threshold table (from inserters/lactate_threshold.py)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS lactate_threshold (
                    activity_id BIGINT PRIMARY KEY,
                    heart_rate INTEGER,
                    speed_mps DOUBLE,
                    date_hr TIMESTAMP,
                    functional_threshold_power INTEGER,
                    power_to_weight DOUBLE,
                    weight DOUBLE,
                    date_power TIMESTAMP
                    -- FK constraint removed (2025-11-01): Data integrity enforced at application layer
                )
            """)

            # Create body_composition table (from inserters/body_composition.py)
            conn.execute("""
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
            """)
            # One row per day: enables idempotent date-keyed upsert (INSERT OR
            # REPLACE) so cache backfill never duplicates a date.
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "idx_body_composition_date ON body_composition(date)"
            )

            # Create daily_wellness table (RHR / HRV / sleep / readiness /
            # body battery / stress). Keyed by date for idempotent upserts.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_wellness (
                    wellness_id INTEGER PRIMARY KEY,
                    date DATE NOT NULL,
                    resting_hr INTEGER,
                    hrv_overnight_ms DOUBLE,
                    hrv_status VARCHAR,
                    hrv_baseline_low DOUBLE,
                    hrv_baseline_high DOUBLE,
                    sleep_seconds INTEGER,
                    sleep_score INTEGER,
                    training_readiness INTEGER,
                    body_battery_high INTEGER,
                    body_battery_low INTEGER,
                    stress_avg INTEGER,
                    source VARCHAR
                )
            """)
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "idx_daily_wellness_date ON daily_wellness(date)"
            )

            # form_baselines table removed - replaced by form_baseline_history

            # Create form_baseline_history table (for trend analysis)
            conn.execute("""
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

                    power_a FLOAT,
                    power_b FLOAT,
                    power_rmse FLOAT,

                    period_start DATE NOT NULL,
                    period_end DATE NOT NULL,
                    trained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                    n_samples INTEGER,
                    rmse FLOAT,
                    speed_range_min FLOAT,
                    speed_range_max FLOAT,

                    UNIQUE(user_id, condition_group, metric, period_start, period_end)
                )
            """)

            # Create form_evaluations table
            conn.execute("""
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

                    cadence_expected DOUBLE,
                    cadence_delta_pct DOUBLE,
                    cadence_star_rating VARCHAR,
                    cadence_score DOUBLE,
                    cadence_needs_improvement BOOLEAN,
                    cadence_evaluation_text VARCHAR,

                    overall_score FLOAT,
                    overall_star_rating VARCHAR,

                    power_avg_w FLOAT,
                    power_wkg FLOAT,
                    speed_actual_mps FLOAT,
                    speed_expected_mps FLOAT,
                    power_efficiency_score FLOAT,
                    power_efficiency_rating VARCHAR,
                    power_efficiency_needs_improvement BOOLEAN,
                    integrated_score FLOAT,
                    training_mode VARCHAR,

                    evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    -- FK constraint removed (2025-11-01): Data integrity enforced at application layer
                )
            """)

            # Create section_analyses table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS section_analyses (
                    analysis_id INTEGER PRIMARY KEY,
                    activity_id BIGINT NOT NULL,
                    activity_date DATE NOT NULL,
                    section_type VARCHAR NOT NULL,
                    analysis_data VARCHAR,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    agent_name VARCHAR,
                    agent_version VARCHAR
                    -- FK constraint removed (2025-11-01): Data integrity enforced at application layer
                )
            """)

            # Create time_series_metrics table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS time_series_metrics (
                    activity_id BIGINT NOT NULL,
                    seq_no INTEGER NOT NULL,
                    timestamp_s INTEGER NOT NULL,
                    sum_moving_duration DOUBLE,
                    sum_duration DOUBLE,
                    sum_elapsed_duration DOUBLE,
                    sum_distance DOUBLE,
                    sum_accumulated_power DOUBLE,
                    heart_rate DOUBLE,
                    speed DOUBLE,
                    grade_adjusted_speed DOUBLE,
                    cadence DOUBLE,
                    cadence_single_foot DOUBLE,
                    cadence_total DOUBLE,
                    power DOUBLE,
                    ground_contact_time DOUBLE,
                    vertical_oscillation DOUBLE,
                    vertical_ratio DOUBLE,
                    stride_length DOUBLE,
                    vertical_speed DOUBLE,
                    elevation DOUBLE,
                    air_temperature DOUBLE,
                    latitude DOUBLE,
                    longitude DOUBLE,
                    available_stamina DOUBLE,
                    potential_stamina DOUBLE,
                    body_battery DOUBLE,
                    performance_condition DOUBLE,
                    PRIMARY KEY (activity_id, seq_no)
                )
            """)

            # Create training_plans table (from inserters/training_plans.py)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS training_plans (
                    plan_id VARCHAR,
                    version INTEGER DEFAULT 1,
                    goal_type VARCHAR NOT NULL,
                    target_race_date DATE,
                    target_time_seconds INTEGER,
                    vdot DOUBLE NOT NULL,
                    pace_zones_json VARCHAR NOT NULL,
                    total_weeks INTEGER NOT NULL,
                    start_date DATE NOT NULL,
                    weekly_volume_start_km DOUBLE NOT NULL,
                    weekly_volume_peak_km DOUBLE NOT NULL,
                    runs_per_week INTEGER NOT NULL,
                    frequency_progression_json VARCHAR,
                    personalization_notes VARCHAR,
                    status VARCHAR DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create planned_workouts table (from inserters/training_plans.py)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS planned_workouts (
                    workout_id VARCHAR PRIMARY KEY,
                    plan_id VARCHAR NOT NULL,
                    version INTEGER DEFAULT 1,
                    week_number INTEGER NOT NULL,
                    day_of_week INTEGER NOT NULL,
                    workout_date DATE,
                    workout_type VARCHAR NOT NULL,
                    description_ja VARCHAR,
                    target_distance_km DOUBLE,
                    target_duration_minutes DOUBLE,
                    target_pace_low DOUBLE,
                    target_pace_high DOUBLE,
                    target_hr_low INTEGER,
                    target_hr_high INTEGER,
                    intervals_json VARCHAR,
                    phase VARCHAR NOT NULL,
                    garmin_workout_id BIGINT,
                    uploaded_at TIMESTAMP,
                    actual_activity_id BIGINT,
                    adherence_score DOUBLE,
                    completed_at TIMESTAMP
                )
            """)

            # Create strength_sessions table (mirrors
            # migrations/add_strength_sessions.py; strength training is stored
            # at summary granularity, kept out of ``activities`` to avoid
            # polluting run aggregations -- issue #450).
            conn.execute("""
                CREATE TABLE IF NOT EXISTS strength_sessions (
                    activity_id BIGINT PRIMARY KEY,
                    activity_date DATE,
                    start_time_local TIMESTAMP,
                    activity_name VARCHAR,
                    active_duration_seconds INTEGER,
                    elapsed_duration_seconds INTEGER,
                    avg_heart_rate INTEGER,
                    max_heart_rate INTEGER,
                    calories INTEGER,
                    active_sets INTEGER,
                    total_sets INTEGER,
                    category_counts JSON,
                    ingested_at TIMESTAMP
                )
            """)

            # Create indexes for time_series_metrics
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_time_series_activity "
                "ON time_series_metrics(activity_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_time_series_timestamp "
                "ON time_series_metrics(activity_id, timestamp_s)"
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
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_activity_section
                ON section_analyses(activity_id, section_type)
            """)

            # NOTE: The athlete-centric tables (athlete_profile, athlete_goals,
            # season_retrospectives, weekly_reviews) and their sequences are
            # owned exclusively by migrations/add_athlete_tables.py (schema
            # version 7), which the migration runner applies right after this
            # method during __init__. They are intentionally NOT created here to
            # keep a single source of truth for that DDL (see issue #342).

    def _run_migrations(self) -> None:
        """Run pending database migrations after table creation."""
        from garmin_mcp.database.migrations.backup import backup_if_pending
        from garmin_mcp.database.migrations.runner import MigrationRunner

        # Back up the real production DB before applying pending migrations.
        # A copy failure raises RuntimeError and intentionally aborts init so
        # that no migration runs without a safety net.
        backup_if_pending(self.db_path)

        runner = MigrationRunner(self.db_path)
        applied = runner.run_pending()
        if applied:
            logger.info("Applied %d migration(s): %s", len(applied), applied)

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
            with get_write_connection(self.db_path) as conn:
                # Start transaction
                conn.begin()

                try:
                    # UPSERT Step 1: Get next analysis_id from sequence (thread-safe)
                    # Note: ON CONFLICT時は使用されず、既存のanalysis_idが保持される
                    row = conn.execute(
                        "SELECT nextval('seq_section_analyses_id')"
                    ).fetchone()
                    assert row is not None
                    next_analysis_id = row[0]

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
                    logger.info(
                        f"Upserted {section_type} analysis for activity {activity_id} (replaced existing if any)"
                    )
                    return True

                except Exception as e:
                    # Rollback on error
                    conn.rollback()
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
            row = _body_comp_row(date, weight_data)
            if row is None:
                logger.warning(f"No weight data found for {date}")
                return False

            with get_write_connection(self.db_path) as conn:
                # The table has two unique constraints (measurement_id PK and the
                # unique date index), so DuckDB cannot infer a single conflict
                # target for ON CONFLICT. Delete any existing row for this date
                # first, then insert — making the operation a date-level upsert.
                conn.execute(
                    "DELETE FROM body_composition WHERE date = ?", [row["date"]]
                )

                max_id_result = conn.execute(
                    "SELECT COALESCE(MAX(measurement_id), 0) FROM body_composition"
                ).fetchone()
                next_measurement_id = max_id_result[0] + 1 if max_id_result else 1

                conn.execute(
                    """
                    INSERT INTO body_composition
                    (measurement_id, date, weight_kg, body_fat_percentage, muscle_mass_kg,
                     bone_mass_kg, bmi, hydration_percentage, measurement_source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    [
                        next_measurement_id,
                        row["date"],
                        row["weight_kg"],
                        row["body_fat_percentage"],
                        row["muscle_mass_kg"],
                        row["bone_mass_kg"],
                        row["bmi"],
                        row["hydration_percentage"],
                        row["measurement_source"],
                    ],
                )

            logger.info(f"Inserted body composition data for {date}")
            return True
        except Exception as e:
            logger.error(f"Error inserting body composition data: {e}")
            return False

    def insert_daily_wellness(self, date: str, wellness_data: dict) -> bool:
        """Insert (date-level upsert) daily wellness data.

        Builds a normalized row via :func:`_wellness_row` and upserts it by
        ``date``. Because the table has both a PRIMARY KEY (``wellness_id``)
        and a UNIQUE index (``date``), DuckDB cannot infer a single conflict
        target, so existing rows for the date are deleted first and a fresh
        row inserted — an INSERT OR REPLACE keyed on date.

        Args:
            date: Date in ``YYYY-MM-DD`` format.
            wellness_data: Merged wellness dict from
                :func:`collect_wellness_data`.

        Returns:
            True on success, False when there is no wellness data to store.
        """
        try:
            row = _wellness_row(date, wellness_data)
            if row is None:
                logger.warning(f"No wellness data found for {date}")
                return False

            with get_write_connection(self.db_path) as conn:
                conn.execute("DELETE FROM daily_wellness WHERE date = ?", [row["date"]])

                max_id_result = conn.execute(
                    "SELECT COALESCE(MAX(wellness_id), 0) FROM daily_wellness"
                ).fetchone()
                next_wellness_id = max_id_result[0] + 1 if max_id_result else 1

                conn.execute(
                    """
                    INSERT INTO daily_wellness
                    (wellness_id, date, resting_hr, hrv_overnight_ms, hrv_status,
                     hrv_baseline_low, hrv_baseline_high, sleep_seconds, sleep_score,
                     training_readiness, body_battery_high, body_battery_low,
                     stress_avg, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    [
                        next_wellness_id,
                        row["date"],
                        row["resting_hr"],
                        row["hrv_overnight_ms"],
                        row["hrv_status"],
                        row["hrv_baseline_low"],
                        row["hrv_baseline_high"],
                        row["sleep_seconds"],
                        row["sleep_score"],
                        row["training_readiness"],
                        row["body_battery_high"],
                        row["body_battery_low"],
                        row["stress_avg"],
                        row["source"],
                    ],
                )

            logger.info(f"Inserted daily wellness data for {date}")
            return True
        except Exception as e:
            logger.error(f"Error inserting daily wellness data: {e}")
            return False
