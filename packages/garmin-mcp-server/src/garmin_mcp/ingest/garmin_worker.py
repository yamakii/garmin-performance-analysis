"""
GarminIngestWorker - Data collection and processing pipeline

Thin orchestrator that delegates to:
- api_client: Garmin Connect API authentication
- raw_data_fetcher: Cache-first raw data collection
- duckdb_saver: DuckDB insertion with transaction batching
"""

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

import numpy as np
import pandas as pd
from garminconnect import Garmin

from garmin_mcp.ingest.api_client import get_garmin_client
from garmin_mcp.ingest.duckdb_saver import save_data as _save_data
from garmin_mcp.ingest.raw_data_fetcher import (
    collect_body_composition_data,
    collect_data,
    load_from_cache,
)

__all__ = ["GarminIngestWorker", "convert_numpy_types"]

if TYPE_CHECKING:
    from garmin_mcp.database.db_reader import GarminDBReader

logger = logging.getLogger(__name__)


def convert_numpy_types(obj: Any) -> Any:
    """
    Convert numpy types to Python native types for JSON serialization.

    NaN values are converted to None (null in JSON) to comply with JSON spec.

    Args:
        obj: Object to convert (can be dict, list, numpy type, etc.)

    Returns:
        Object with numpy types converted to Python types
    """
    if isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        # Convert NaN to None (null in JSON) - JSON spec doesn't allow NaN literals
        if np.isnan(obj):
            return None
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif obj is None or pd.isna(obj):
        return None
    else:
        return obj


class GarminIngestWorker:
    """Orchestrator for Garmin data collection and processing pipeline.

    Delegates to specialized modules:
    - api_client: Authentication singleton
    - raw_data_fetcher: Cache-first data collection
    - duckdb_saver: Transaction-batched DB insertion
    """

    _garmin_client: Garmin | None = None

    def __init__(self, db_path: str | None = None):
        """Initialize GarminIngestWorker.

        Args:
            db_path: Optional DuckDB path for activity date lookup
        """
        from garmin_mcp.utils.paths import (
            get_default_db_path,
            get_project_root,
            get_raw_dir,
            get_weight_raw_dir,
        )

        self.project_root = get_project_root()
        self.raw_dir = get_raw_dir()
        self.weight_raw_dir = get_weight_raw_dir()

        # Create directories
        for directory in [
            self.raw_dir,
            self.weight_raw_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)

        # DB path: Resolve to concrete path if None
        if db_path is None:
            db_path = get_default_db_path()
        self._db_path = db_path

        # DB reader for activity date lookup
        self._db_reader: GarminDBReader | None = None

    @classmethod
    def get_garmin_client(cls) -> Garmin:
        """Get singleton Garmin client (reuse authentication).

        Delegates to api_client module for thread-safe singleton.

        Returns:
            Authenticated Garmin client
        """
        return get_garmin_client()

    def get_activity_date(self, activity_id: int) -> str | None:
        """Get activity date from DuckDB.

        Args:
            activity_id: Activity ID

        Returns:
            Activity date (YYYY-MM-DD) or None if not found
        """
        if self._db_reader is None:
            from garmin_mcp.database.db_reader import GarminDBReader

            self._db_reader = GarminDBReader(db_path=self._db_path)

        result = self._db_reader.get_activity_date(activity_id)
        return cast(str | None, result) if result else None

    def _check_duckdb_cache(self, activity_id: int) -> dict[str, Any] | None:
        """Check if activity data exists in DuckDB.

        Args:
            activity_id: Activity ID to check

        Returns:
            Complete performance data dict if all sections exist, None otherwise
        """
        if self._db_reader is None:
            return None

        # TODO: Implement DuckDB cache checking with normalized schema
        logger.debug(
            f"Activity {activity_id}: DuckDB cache checking not implemented "
            "for normalized schema"
        )
        return None

    def load_from_cache(
        self, activity_id: int, skip_files: set[str] | None = None
    ) -> dict[str, Any] | None:
        """Load cached raw_data from directory structure.

        Delegates to raw_data_fetcher.load_from_cache().
        """
        return load_from_cache(self.raw_dir, activity_id, skip_files)

    def collect_data(
        self, activity_id: int, force_refetch: list[str] | None = None
    ) -> dict[str, Any]:
        """Collect activity data with per-API cache-first strategy.

        Delegates to raw_data_fetcher.collect_data().
        """
        return collect_data(self.raw_dir, activity_id, force_refetch)

    def collect_body_composition_data(self, date: str) -> dict[str, Any] | None:
        """Collect body composition data with cache-first strategy.

        Delegates to raw_data_fetcher.collect_body_composition_data().
        """
        return collect_body_composition_data(self.weight_raw_dir, date)

    def _calculate_form_efficiency_summary(self, df: pd.DataFrame) -> dict[str, Any]:
        """Calculate form efficiency summary (legacy method).

        Returns:
            Form metrics with statistics and ratings
        """
        if df.empty:
            return {}

        gct_stats = {
            "average": df["ground_contact_time_ms"].mean(),
            "min": df["ground_contact_time_ms"].min(),
            "max": df["ground_contact_time_ms"].max(),
            "std": df["ground_contact_time_ms"].std(),
        }

        vo_stats = {
            "average": df["vertical_oscillation_cm"].mean(),
            "min": df["vertical_oscillation_cm"].min(),
            "max": df["vertical_oscillation_cm"].max(),
            "std": df["vertical_oscillation_cm"].std(),
        }

        vr_stats = {
            "average": df["vertical_ratio_percent"].mean(),
            "min": df["vertical_ratio_percent"].min(),
            "max": df["vertical_ratio_percent"].max(),
            "std": df["vertical_ratio_percent"].std(),
        }

        gct_rating = "★★★★★" if gct_stats["average"] < 240 else "★★★☆☆"
        vo_rating = "★★★★★" if vo_stats["average"] < 8.0 else "★★★☆☆"
        vr_rating = "★★★★★" if vr_stats["average"] < 8.5 else "★★★☆☆"

        return {
            "gct_stats": gct_stats,
            "gct_rating": gct_rating,
            "vo_stats": vo_stats,
            "vo_rating": vo_rating,
            "vr_stats": vr_stats,
            "vr_rating": vr_rating,
            "evaluation": "優秀な接地時間、効率的な地面反力利用",
        }

    def _calculate_hr_efficiency_analysis(
        self,
        df: pd.DataFrame,
        hr_zones: list[dict[str, Any]],
        training_effect_label: str | None = None,
    ) -> dict[str, Any]:
        """Calculate HR efficiency analysis (legacy method).

        Args:
            df: Performance DataFrame
            hr_zones: List of {zoneNumber, secsInZone, zoneLowBoundary}
            training_effect_label: Garmin's trainingEffectLabel

        Returns:
            HR zone distribution and training type classification
        """
        if df.empty:
            return {}

        avg_hr = df["avg_heart_rate"].mean()

        # Primary: Use Garmin's trainingEffectLabel
        training_type = None
        if training_effect_label:
            training_type = training_effect_label.lower()

        # Fallback: HR threshold-based classification
        if not training_type:
            zone_boundaries = {}
            for zone in hr_zones:
                zone_num = zone.get("zoneNumber")
                if zone_num:
                    zone_boundaries[zone_num] = zone.get("zoneLowBoundary", 0)

            z1_high = zone_boundaries.get(2, 120)
            z2_high = zone_boundaries.get(3, 140)
            z3_high = zone_boundaries.get(4, 160)

            if avg_hr <= z1_high:
                training_type = "aerobic_base"
            elif avg_hr <= z2_high:
                training_type = "tempo_run"
            elif avg_hr <= z3_high:
                training_type = "threshold_work"
            else:
                training_type = "mixed_effort"

        # Calculate zone percentages
        total_time = sum(zone.get("secsInZone", 0) for zone in hr_zones)
        zone_percentages = {}

        if total_time > 0:
            for zone in hr_zones:
                zone_num = zone.get("zoneNumber")
                secs_in_zone = zone.get("secsInZone", 0)

                if zone_num:
                    percentage = (secs_in_zone / total_time) * 100
                    zone_percentages[f"zone{zone_num}_percentage"] = round(
                        percentage, 2
                    )

        return {
            "avg_heart_rate": avg_hr,
            "training_type": training_type,
            "hr_stability": "優秀" if df["avg_heart_rate"].std() < 5 else "変動あり",
            "description": "適切な心拍ゾーンで実施",
            **zone_percentages,
        }

    def _calculate_performance_trends(self, df: pd.DataFrame) -> dict[str, Any]:
        """Calculate performance trends with 4-phase support (legacy method).

        Returns:
            Phase-based analysis and consistency metrics
        """
        if df.empty or len(df) < 3:
            return {}

        if "role_phase" not in df.columns:
            return {}

        warmup_df = df[df["role_phase"] == "warmup"]
        run_df = df[df["role_phase"] == "run"]
        recovery_df = df[df["role_phase"] == "recovery"]
        cooldown_df = df[df["role_phase"] == "cooldown"]

        warmup_phase = {
            "splits": warmup_df["split_number"].tolist() if not warmup_df.empty else [],
            "avg_pace": (
                warmup_df["avg_pace_seconds_per_km"].mean()
                if not warmup_df.empty
                else None
            ),
            "avg_hr": (
                warmup_df["avg_heart_rate"].mean() if not warmup_df.empty else None
            ),
        }

        run_phase = {
            "splits": run_df["split_number"].tolist() if not run_df.empty else [],
            "avg_pace": (
                run_df["avg_pace_seconds_per_km"].mean() if not run_df.empty else None
            ),
            "avg_hr": run_df["avg_heart_rate"].mean() if not run_df.empty else None,
        }

        recovery_phase = {
            "splits": (
                recovery_df["split_number"].tolist() if not recovery_df.empty else []
            ),
            "avg_pace": (
                recovery_df["avg_pace_seconds_per_km"].mean()
                if not recovery_df.empty
                else None
            ),
            "avg_hr": (
                recovery_df["avg_heart_rate"].mean() if not recovery_df.empty else None
            ),
        }

        cooldown_phase = {
            "splits": (
                cooldown_df["split_number"].tolist() if not cooldown_df.empty else []
            ),
            "avg_pace": (
                cooldown_df["avg_pace_seconds_per_km"].mean()
                if not cooldown_df.empty
                else None
            ),
            "avg_hr": (
                cooldown_df["avg_heart_rate"].mean() if not cooldown_df.empty else None
            ),
        }

        if not run_df.empty:
            pace_consistency = (
                run_df["avg_pace_seconds_per_km"].std()
                / run_df["avg_pace_seconds_per_km"].mean()
                if run_df["avg_pace_seconds_per_km"].mean() > 0
                else 0
            )
        else:
            pace_consistency = 0

        warmup_hr_val = warmup_phase.get("avg_hr")
        cooldown_hr_val = cooldown_phase.get("avg_hr")
        if (
            warmup_hr_val is not None
            and cooldown_hr_val is not None
            and isinstance(warmup_hr_val, int | float)
            and isinstance(cooldown_hr_val, int | float)
        ):
            hr_drift_percentage = (
                (float(cooldown_hr_val) - float(warmup_hr_val))
                / float(warmup_hr_val)
                * 100
            )
        else:
            hr_drift_percentage = 0

        if hr_drift_percentage < 5:
            fatigue_pattern = "適切な疲労管理"
        elif hr_drift_percentage < 10:
            fatigue_pattern = "軽度の疲労蓄積"
        else:
            fatigue_pattern = "顕著な疲労蓄積"

        return {
            "warmup_phase": warmup_phase,
            "run_phase": run_phase,
            "recovery_phase": recovery_phase,
            "cooldown_phase": cooldown_phase,
            "pace_consistency": pace_consistency,
            "hr_drift_percentage": hr_drift_percentage,
            "cadence_consistency": (
                "高い安定性" if df["avg_cadence"].std() < 5 else "変動あり"
            ),
            "fatigue_pattern": fatigue_pattern,
        }

    def _should_insert_table(self, table_name: str, tables: list[str] | None) -> bool:
        """Check if a table should be inserted into DuckDB.

        Delegates to duckdb_saver.should_insert_table().
        """
        from garmin_mcp.ingest.duckdb_saver import should_insert_table

        return should_insert_table(table_name, tables)

    def save_data(
        self,
        activity_id: int,
        raw_data: dict[str, Any],
        activity_date: str | None = None,
        tables: list[str] | None = None,
        base_weight_kg: float | None = None,
    ) -> dict[str, Any]:
        """Save all processed data to DuckDB.

        Delegates to duckdb_saver.save_data().
        """
        return _save_data(
            activity_id=activity_id,
            raw_data=raw_data,
            db_path=self._db_path,
            raw_dir=self.raw_dir,
            activity_date=activity_date,
            tables=tables,
            base_weight_kg=base_weight_kg,
        )

    def _calculate_median_weight(self, date: str) -> dict[str, Any] | None:
        """Calculate median weight from past 7 days including target date.

        Args:
            date: Date in YYYY-MM-DD format

        Returns:
            Dict with median weight data or None
        """
        target_date = datetime.strptime(date, "%Y-%m-%d")
        weights: list[float] = []
        bmi_values: list[float] = []
        body_fat_values: list[float] = []
        body_water_values: list[float] = []
        bone_mass_values: list[float] = []
        muscle_mass_values: list[float] = []

        # First, try to get data for the target date
        target_raw_data = self.collect_body_composition_data(date)
        if not target_raw_data or not target_raw_data.get("dateWeightList"):
            logger.warning(
                f"No body composition data found for {date}, "
                "skipping past 7 days lookup"
            )
            return None

        # Target date has data, collect from it
        target_data = target_raw_data["dateWeightList"][0]
        if target_data.get("weight"):
            weights.append(target_data["weight"] / 1000.0)
        if target_data.get("bmi"):
            bmi_values.append(target_data["bmi"])
        if target_data.get("bodyFat"):
            body_fat_values.append(target_data["bodyFat"])
        if target_data.get("bodyWater"):
            body_water_values.append(target_data["bodyWater"])
        if target_data.get("boneMass"):
            bone_mass_values.append(target_data["boneMass"] / 1000.0)
        if target_data.get("muscleMass"):
            muscle_mass_values.append(target_data["muscleMass"] / 1000.0)

        # Now collect from past 6 days (total 7 days with target date)
        for i in range(1, 7):
            check_date = target_date - timedelta(days=i)
            check_date_str = check_date.strftime("%Y-%m-%d")

            raw_data = self.collect_body_composition_data(check_date_str)
            if raw_data and raw_data.get("dateWeightList"):
                data = raw_data["dateWeightList"][0]

                if data.get("weight"):
                    weights.append(data["weight"] / 1000.0)
                if data.get("bmi"):
                    bmi_values.append(data["bmi"])
                if data.get("bodyFat"):
                    body_fat_values.append(data["bodyFat"])
                if data.get("bodyWater"):
                    body_water_values.append(data["bodyWater"])
                if data.get("boneMass"):
                    bone_mass_values.append(data["boneMass"] / 1000.0)
                if data.get("muscleMass"):
                    muscle_mass_values.append(data["muscleMass"] / 1000.0)

        if not weights:
            logger.warning(f"No weight data found in past 7 days for {date}")
            return None

        return {
            "date": date,
            "weight_kg": float(np.median(weights)),
            "bmi": float(np.median(bmi_values)) if bmi_values else None,
            "body_fat_percentage": (
                float(np.median(body_fat_values)) if body_fat_values else None
            ),
            "muscle_mass_kg": (
                float(np.median(muscle_mass_values)) if muscle_mass_values else None
            ),
            "bone_mass_kg": (
                float(np.median(bone_mass_values)) if bone_mass_values else None
            ),
            "hydration_percentage": (
                float(np.median(body_water_values)) if body_water_values else None
            ),
            "source": "7DAY_MEDIAN",
            "sample_count": len(weights),
        }

    def process_body_composition(self, date: str) -> dict[str, Any]:
        """Process body composition data - save direct measurements only.

        Args:
            date: Date in YYYY-MM-DD format

        Returns:
            Result dict with status
        """
        logger.info(f"Processing body composition data for {date}")

        raw_data = self.collect_body_composition_data(date)

        if not raw_data or not raw_data.get("dateWeightList"):
            logger.warning(f"No body composition data found for {date}")
            return {
                "date": date,
                "status": "no_data",
                "message": f"No body composition data found for {date}",
            }

        from garmin_mcp.database.db_writer import GarminDBWriter

        writer = (
            GarminDBWriter(db_path=self._db_path) if self._db_path else GarminDBWriter()
        )
        success = writer.insert_body_composition(date=date, weight_data=raw_data)

        if success:
            weight_kg = raw_data["dateWeightList"][0].get("weight", 0) / 1000.0
            logger.info(
                f"Successfully processed body composition data for {date}: "
                f"{weight_kg:.3f} kg"
            )
            return {
                "date": date,
                "status": "success",
                "message": f"Body composition data inserted for {date} (direct measurement)",
                "weight_kg": weight_kg,
                "source": "direct_measurement",
            }
        else:
            logger.error(f"Failed to insert body composition data for {date}")
            return {
                "date": date,
                "status": "error",
                "message": f"Failed to insert body composition data for {date}",
            }

    def process_activity(
        self,
        activity_id: int,
        date: str,
        force_refetch: list[str] | None = None,
        tables: list[str] | None = None,
    ) -> dict[str, Any]:
        """Process activity through cache-first pipeline.

        Pipeline:
        1. Check DuckDB cache -> return if complete
        2. Collect data (cache-first with optional force_refetch)
        3. Calculate 7-day median weight for W/kg
        4. Insert into DuckDB via save_data()

        Args:
            activity_id: Activity ID
            date: Activity date (YYYY-MM-DD)
            force_refetch: List of API file names to force refetch
            tables: List of tables to regenerate

        Returns:
            Result dict with file paths
        """
        logger.info(f"Processing activity {activity_id} ({date})")

        # Step 0: Check DuckDB cache first
        cache_exists = self._check_duckdb_cache(activity_id)

        if cache_exists is not None:
            logger.info(
                f"Activity {activity_id}: Using complete data from DuckDB cache"
            )
            return {
                "activity_id": activity_id,
                "date": date,
                "status": "success",
                "source": "duckdb_cache",
            }

        # Step 1: Collect data (cache-first with optional force_refetch)
        raw_data = self.collect_data(activity_id, force_refetch=force_refetch)

        # Step 2: Calculate 7-day median weight for W/kg
        median_weight_data = self._calculate_median_weight(date)
        weight_kg = median_weight_data["weight_kg"] if median_weight_data else None

        # Step 3: Save data and insert into DuckDB
        file_paths = self.save_data(
            activity_id,
            raw_data,
            activity_date=date,
            tables=tables,
            base_weight_kg=weight_kg,
        )

        return {
            "activity_id": activity_id,
            "date": date,
            "files": file_paths,
            "weight_kg": weight_kg,
            "status": "success",
        }

    def _resolve_activity_id_from_duckdb(self, date: str) -> int | None:
        """Resolve activity ID from DuckDB by date.

        Args:
            date: Activity date (YYYY-MM-DD)

        Returns:
            Activity ID if found in DuckDB, None otherwise
        """
        if self._db_reader is None:
            return None

        return self._db_reader.query_activity_by_date(date)

    def _resolve_activity_id_from_api(self, date: str) -> int:
        """Resolve activity ID from Garmin API by date.

        Args:
            date: Activity date (YYYY-MM-DD)

        Returns:
            Activity ID from API

        Raises:
            ValueError: If no activity found for date
            ValueError: If multiple activities found
        """
        client = self.get_garmin_client()
        api_response = client.get_activities_fordate(date)

        activities_data = api_response.get("ActivitiesForDay", {}).get("payload", [])

        if len(activities_data) == 0:
            raise ValueError(f"No activities found for {date}")
        elif len(activities_data) > 1:
            activity_list = ", ".join(
                [
                    f"{act.get('activityId')} ({act.get('activityName')})"
                    for act in activities_data
                ]
            )
            raise ValueError(
                f"Multiple activities found for {date}. "
                f"Please specify activity_id. Found: {activity_list}"
            )

        activity_id = int(activities_data[0].get("activityId", 0))
        logger.info(f"Found single activity for {date}: {activity_id}")
        return activity_id

    def process_activity_by_date(self, date: str) -> dict[str, Any]:
        """Process activity by date (resolve activity_id from DuckDB or API).

        Args:
            date: Activity date (YYYY-MM-DD)

        Returns:
            Result dict with activity_id and file paths

        Raises:
            ValueError: If no activity found for date
            ValueError: If multiple activities found
        """
        logger.info(f"Resolving activity for date {date}")

        # Try DuckDB first (cache-first strategy)
        activity_id = self._resolve_activity_id_from_duckdb(date)

        if activity_id is not None:
            logger.info(f"Found activity in DuckDB for {date}: {activity_id}")
        else:
            logger.info(f"Activity not found in DuckDB, querying API for {date}")
            activity_id = self._resolve_activity_id_from_api(date)

        return self.process_activity(activity_id, date)
