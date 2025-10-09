"""
GarminIngestWorker - Data collection and processing pipeline

Implements cache-first strategy:
1. Check raw file cache (data/raw/)
2. If missing, fetch from Garmin Connect API
3. Transform to performance.json and parquet
"""

import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import numpy as np
import pandas as pd
from garminconnect import Garmin

if TYPE_CHECKING:
    from tools.database.db_reader import GarminDBReader

logger = logging.getLogger(__name__)


def convert_numpy_types(obj: Any) -> Any:
    """
    Convert numpy types to Python native types for JSON serialization.

    Preserves NaN for compatibility with existing data.

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
        # Preserve NaN as float('nan') for compatibility
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif obj is None:
        # Explicit None → None
        return None
    elif pd.isna(obj):
        # pandas NaN → float('nan') to preserve NaN in JSON
        return float("nan")
    else:
        return obj


class GarminIngestWorker:
    """Data ingestion worker with cache-first strategy."""

    # Singleton Garmin client (reuse authentication)
    _garmin_client: Garmin | None = None

    def __init__(self, db_path: str | None = None):
        """Initialize GarminIngestWorker.

        Args:
            db_path: Optional DuckDB path for activity date lookup
        """
        self.project_root = Path(__file__).parent.parent.parent
        self.raw_dir = self.project_root / "data" / "raw"
        self.parquet_dir = self.project_root / "data" / "parquet"
        self.performance_dir = self.project_root / "data" / "performance"
        self.precheck_dir = self.project_root / "data" / "precheck"
        self.weight_cache_dir = self.project_root / "data" / "weight_cache" / "raw"

        # Create directories
        for directory in [
            self.raw_dir,
            self.parquet_dir,
            self.performance_dir,
            self.precheck_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)

        # DB reader for activity date lookup
        self._db_reader: GarminDBReader | None = None
        self._db_path = db_path

    @classmethod
    def get_garmin_client(cls) -> Garmin:
        """
        Get singleton Garmin client (reuse authentication).

        Reads credentials from environment variables:
        - GARMIN_EMAIL
        - GARMIN_PASSWORD

        Returns:
            Authenticated Garmin client

        Raises:
            ValueError: If credentials not found in environment
        """
        if cls._garmin_client is None:
            email = os.getenv("GARMIN_EMAIL")
            password = os.getenv("GARMIN_PASSWORD")

            if not email or not password:
                raise ValueError(
                    "Garmin credentials not found. "
                    "Set GARMIN_EMAIL and GARMIN_PASSWORD environment variables."
                )

            logger.info(f"Authenticating with Garmin Connect as {email}")
            cls._garmin_client = Garmin(email, password)
            cls._garmin_client.login()
            logger.info("Garmin authentication successful")

        return cls._garmin_client

    def get_activity_date(self, activity_id: int) -> str | None:
        """
        Get activity date from DuckDB.

        Args:
            activity_id: Activity ID

        Returns:
            Activity date (YYYY-MM-DD) or None if not found
        """
        if self._db_reader is None:
            from tools.database.db_reader import GarminDBReader

            self._db_reader = GarminDBReader(
                db_path=self._db_path or "data/database/garmin_performance.duckdb"
            )

        result = self._db_reader.get_activity_date(activity_id)
        return cast(str | None, result) if result else None

    def collect_data(self, activity_id: int) -> dict[str, Any]:
        """
        Collect activity data with cache-first strategy.

        Cache priority:
        1. Check data/raw/{activity_id}_raw.json
        2. If missing, fetch from Garmin Connect API

        Args:
            activity_id: Activity ID

        Returns:
            Raw data dict with keys: activity, splits, weather, gear, hr_zones, etc.
        """
        # Check cache first
        raw_file = self.raw_dir / f"{activity_id}_raw.json"
        if raw_file.exists():
            logger.info(f"Using cached data for activity {activity_id}")
            with open(raw_file, encoding="utf-8") as f:
                return cast(dict[str, Any], json.load(f))

        # Fetch from Garmin Connect API
        logger.info(f"Fetching activity {activity_id} from Garmin Connect API")
        client = self.get_garmin_client()

        # Collect all data components
        activity_data = client.get_activity_details(activity_id)

        raw_data = {
            "activity": activity_data,
            "splits": client.get_activity_splits(activity_id),
            "weather": client.get_activity_weather(activity_id),
            "gear": client.get_activity_gear(activity_id),
            "hr_zones": client.get_activity_hr_in_timezones(activity_id),
        }

        # Add optional fields from activity data if available
        # Extract training effect from activity.summaryDTO
        summary = activity_data.get("summaryDTO", {}) if activity_data else {}
        if summary:
            raw_data["training_effect"] = {
                "aerobicTrainingEffect": summary.get("trainingEffect"),
                "anaerobicTrainingEffect": summary.get("anaerobicTrainingEffect"),
                "aerobicTrainingEffectMessage": summary.get(
                    "aerobicTrainingEffectMessage"
                ),
                "anaerobicTrainingEffectMessage": summary.get(
                    "anaerobicTrainingEffectMessage"
                ),
                "trainingEffectLabel": summary.get("trainingEffectLabel"),
            }

            # Extract activity date for VO2 max API call
            start_time_local = summary.get("startTimeLocal", "")
            if start_time_local:
                # Extract date from "2025-10-05T19:05:50.0" -> "2025-10-05"
                activity_date = start_time_local.split("T")[0]

                # Fetch VO2 max data from get_max_metrics(date)
                try:
                    max_metrics = client.get_max_metrics(activity_date)
                    generic_metrics = max_metrics.get("generic", {})
                    raw_data["vo2_max"] = {
                        "vo2MaxValue": generic_metrics.get("vo2MaxValue"),
                        "vo2MaxPreciseValue": generic_metrics.get("vo2MaxPreciseValue"),
                        "calendarDate": generic_metrics.get("calendarDate"),
                    }
                except Exception as e:
                    logger.warning(f"Failed to fetch VO2 max data: {e}")
                    raw_data["vo2_max"] = []
            else:
                raw_data["vo2_max"] = []
        else:
            raw_data["vo2_max"] = []

        # Fetch lactate threshold data from get_lactate_threshold(latest=True)
        try:
            lactate_threshold_data = client.get_lactate_threshold(latest=True)
            raw_data["lactate_threshold"] = lactate_threshold_data
        except Exception as e:
            logger.warning(f"Failed to fetch lactate threshold data: {e}")
            raw_data["lactate_threshold"] = {
                "speed_and_heart_rate": None,
                "power": None,
            }

        # Weight data (requires separate weight cache manager)
        # For now, set to None - will be populated by weight_cache_manager if available
        raw_data["weight"] = None

        # Save to cache
        with open(raw_file, "w", encoding="utf-8") as f:
            json.dump(raw_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Cached raw data to {raw_file}")
        return raw_data

    def create_parquet_dataset(self, raw_data: dict[str, Any]) -> pd.DataFrame:
        """
        Create parquet-ready DataFrame from raw lapDTOs.

        Args:
            raw_data: Raw data dict with 'splits' key containing lapDTOs

        Returns:
            DataFrame with 15 columns per split
        """
        lap_dtos = raw_data.get("splits", {}).get("lapDTOs", [])
        if not lap_dtos:
            logger.warning("No lapDTOs found in splits data")
            return pd.DataFrame()

        records = []
        for idx, lap in enumerate(lap_dtos, start=1):
            # Calculate pace (seconds per km)
            distance_km = lap.get("distance", 0) / 1000
            duration_seconds = lap.get("duration", 0)
            avg_pace = duration_seconds / distance_km if distance_km > 0 else 0

            # Classify terrain based on elevation gain
            elevation_gain = lap.get("elevationGain", 0)
            if elevation_gain < 5:
                terrain_type = "平坦"
            elif elevation_gain < 15:
                terrain_type = "起伏"
            elif elevation_gain < 30:
                terrain_type = "丘陵"
            else:
                terrain_type = "山岳"

            # Map intensityType to role_phase
            intensity_type = lap.get("intensityType", "ACTIVE")
            role_phase_map = {
                "WARMUP": "warmup",
                "INTERVAL": "run",
                "ACTIVE": "run",
                "RECOVERY": "recovery",
                "REST": "recovery",
                "COOLDOWN": "cooldown",
            }
            role_phase = role_phase_map.get(intensity_type, "run")

            record = {
                "split_number": idx,
                "distance_km": distance_km,
                "duration_seconds": duration_seconds,
                "avg_pace_seconds_per_km": avg_pace,
                "avg_heart_rate": lap.get("averageHR"),
                "avg_cadence": lap.get("averageRunCadence"),
                "avg_power": lap.get("averagePower"),  # Fixed: avgPower → averagePower
                "ground_contact_time_ms": lap.get("groundContactTime"),
                "vertical_oscillation_cm": lap.get("verticalOscillation"),
                "vertical_ratio_percent": lap.get("verticalRatio"),
                "elevation_gain_m": elevation_gain,
                "elevation_loss_m": lap.get("elevationLoss", 0),
                "max_elevation_m": lap.get("maxElevation"),
                "min_elevation_m": lap.get("minElevation"),
                "terrain_type": terrain_type,
                "role_phase": role_phase,
            }
            records.append(record)

        return pd.DataFrame(records)

    def _calculate_split_metrics(
        self, df: pd.DataFrame, raw_data: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Calculate 11 performance.json sections from DataFrame.

        Sections:
        1. basic_metrics
        2. heart_rate_zones
        3. split_metrics
        4. efficiency_metrics
        5. training_effect
        6. power_to_weight
        7. vo2_max
        8. lactate_threshold
        9. form_efficiency_summary (Phase 1)
        10. hr_efficiency_analysis (Phase 1)
        11. performance_trends (Phase 2)

        Args:
            df: Parquet DataFrame
            raw_data: Raw data dict

        Returns:
            Performance metrics dict
        """
        if df.empty:
            return {}

        activity = raw_data.get("activity", {})
        hr_zones = raw_data.get("hr_zones", {})

        # 1. Basic metrics
        basic_metrics = {
            "distance_km": df["distance_km"].sum(),
            "duration_seconds": df["duration_seconds"].sum(),
            "avg_pace_seconds_per_km": df["avg_pace_seconds_per_km"].mean(),
            "avg_heart_rate": df["avg_heart_rate"].mean(),
            "avg_cadence": df["avg_cadence"].mean(),
            "avg_power": df["avg_power"].mean(),
        }

        # 2. Heart rate zones (from raw data)
        # hr_zones format: list of {zoneNumber, secsInZone, zoneLowBoundary}
        heart_rate_zones = {}
        for zone in hr_zones:
            zone_num = zone.get("zoneNumber")
            if zone_num:
                heart_rate_zones[f"zone{zone_num}"] = {
                    "low": zone.get("zoneLowBoundary"),
                    "secs_in_zone": zone.get("secsInZone"),
                }

        # 3. Split metrics (full DataFrame as list of dicts)
        split_metrics = df.to_dict(orient="records")

        # 4. Efficiency metrics
        efficiency_metrics = {
            "cadence_stability": df["avg_cadence"].std(),
            "pace_variability": df["avg_pace_seconds_per_km"].std(),
            "power_efficiency": (
                df["avg_power"].mean() / basic_metrics["avg_heart_rate"]
                if basic_metrics["avg_heart_rate"] > 0
                else 0
            ),
        }

        # 5. Training effect (from raw activity data)
        training_effect = {
            "aerobic_te": activity.get("aerobicTrainingEffect"),
            "anaerobic_te": activity.get("anaerobicTrainingEffect"),
        }

        # 6. Power to weight (assume 70kg default)
        power_to_weight = {
            "watts_per_kg": (
                basic_metrics["avg_power"] / 70 if basic_metrics["avg_power"] else 0
            )
        }

        # 7. VO2 max (from raw activity data)
        vo2_max = {"vo2_max": activity.get("vO2MaxValue")}

        # 8. Lactate threshold (from raw data)
        lactate_threshold = raw_data.get("lactate_threshold", {})

        # 9. Form efficiency summary (Phase 1)
        form_efficiency_summary = self._calculate_form_efficiency_summary(df)

        # 10. HR efficiency analysis (Phase 1)
        hr_efficiency_analysis = self._calculate_hr_efficiency_analysis(df, hr_zones)

        # 11. Performance trends (Phase 2)
        performance_trends = self._calculate_performance_trends(df)

        performance_data = {
            "basic_metrics": basic_metrics,
            "heart_rate_zones": heart_rate_zones,
            "split_metrics": split_metrics,
            "efficiency_metrics": efficiency_metrics,
            "training_effect": training_effect,
            "power_to_weight": power_to_weight,
            "vo2_max": vo2_max,
            "lactate_threshold": lactate_threshold,
            "form_efficiency_summary": form_efficiency_summary,
            "hr_efficiency_analysis": hr_efficiency_analysis,
            "performance_trends": performance_trends,
        }

        # Convert numpy types to Python types for JSON serialization
        return convert_numpy_types(performance_data)  # type: ignore[no-any-return]

    def _calculate_form_efficiency_summary(self, df: pd.DataFrame) -> dict[str, Any]:
        """
        Calculate form efficiency summary (Phase 1 optimization).

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

        # Rating evaluation (simplified)
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
        self, df: pd.DataFrame, hr_zones: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Calculate HR efficiency analysis (Phase 1 optimization).

        Args:
            df: Performance DataFrame
            hr_zones: List of {zoneNumber, secsInZone, zoneLowBoundary}

        Returns:
            HR zone distribution and training type classification
        """
        if df.empty:
            return {}

        # Simplified zone distribution (would need time in zones data)
        avg_hr = df["avg_heart_rate"].mean()

        # Extract zone boundaries from hr_zones list
        zone_boundaries = {}
        for zone in hr_zones:
            zone_num = zone.get("zoneNumber")
            if zone_num:
                zone_boundaries[zone_num] = zone.get("zoneLowBoundary", 0)

        # Default thresholds if zones not available
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

        return {
            "avg_heart_rate": avg_hr,
            "training_type": training_type,
            "hr_stability": "優秀" if df["avg_heart_rate"].std() < 5 else "変動あり",
            "description": "適切な心拍ゾーンで実施",
        }

    def _calculate_performance_trends(self, df: pd.DataFrame) -> dict[str, Any]:
        """
        Calculate performance trends with 4-phase support (Phase 3 optimization).

        Phases:
        - warmup: ウォームアップ
        - run: メイン走行（高強度）
        - recovery: 回復ジョグ（インターバル休憩）
        - cooldown: クールダウン

        Returns:
            Phase-based analysis and consistency metrics
        """
        if df.empty or len(df) < 3:
            return {}

        # Check if role_phase column exists
        if "role_phase" not in df.columns:
            # Fallback to old 3-phase logic
            return self._calculate_performance_trends_legacy(df)

        # Split into 4 phases based on role_phase
        warmup_df = df[df["role_phase"] == "warmup"]
        run_df = df[df["role_phase"] == "run"]
        recovery_df = df[df["role_phase"] == "recovery"]
        cooldown_df = df[df["role_phase"] == "cooldown"]

        # Calculate phase metrics
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

        # Pace consistency for run phase only (excluding recovery)
        if not run_df.empty:
            pace_consistency = (
                run_df["avg_pace_seconds_per_km"].std()
                / run_df["avg_pace_seconds_per_km"].mean()
                if run_df["avg_pace_seconds_per_km"].mean() > 0
                else 0
            )
        else:
            pace_consistency = 0

        # HR drift (warmup to cooldown)
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

        # Fatigue pattern
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

    def _calculate_performance_trends_legacy(self, df: pd.DataFrame) -> dict[str, Any]:
        """
        Legacy 3-phase calculation for backward compatibility.

        Returns:
            Phase-based analysis with warmup/main/finish
        """
        total_splits = len(df)
        warmup_end = max(1, int(total_splits * 0.2))
        finish_start = max(warmup_end + 1, int(total_splits * 0.8))

        warmup_df = df.iloc[:warmup_end]
        main_df = df.iloc[warmup_end:finish_start]
        finish_df = df.iloc[finish_start:]

        warmup_phase = {
            "splits": list(range(1, warmup_end + 1)),
            "avg_pace": warmup_df["avg_pace_seconds_per_km"].mean(),
            "avg_hr": warmup_df["avg_heart_rate"].mean(),
        }

        main_phase = {
            "splits": list(range(warmup_end + 1, finish_start + 1)),
            "avg_pace": main_df["avg_pace_seconds_per_km"].mean(),
            "avg_hr": main_df["avg_heart_rate"].mean(),
        }

        finish_phase = {
            "splits": list(range(finish_start + 1, total_splits + 1)),
            "avg_pace": finish_df["avg_pace_seconds_per_km"].mean(),
            "avg_hr": finish_df["avg_heart_rate"].mean(),
        }

        pace_consistency = (
            df["avg_pace_seconds_per_km"].std() / df["avg_pace_seconds_per_km"].mean()
            if df["avg_pace_seconds_per_km"].mean() > 0
            else 0
        )

        hr_drift_percentage = (
            (finish_phase["avg_hr"] - warmup_phase["avg_hr"])
            / warmup_phase["avg_hr"]
            * 100
            if warmup_phase["avg_hr"] > 0
            else 0
        )

        if hr_drift_percentage < 5:
            fatigue_pattern = "適切な疲労管理"
        elif hr_drift_percentage < 10:
            fatigue_pattern = "軽度の疲労蓄積"
        else:
            fatigue_pattern = "顕著な疲労蓄積"

        return {
            "warmup_phase": warmup_phase,
            "main_phase": main_phase,
            "finish_phase": finish_phase,
            "pace_consistency": pace_consistency,
            "hr_drift_percentage": hr_drift_percentage,
            "cadence_consistency": (
                "高い安定性" if df["avg_cadence"].std() < 5 else "変動あり"
            ),
            "fatigue_pattern": fatigue_pattern,
        }

    def save_data(
        self,
        activity_id: int,
        raw_data: dict[str, Any],
        df: pd.DataFrame,
        performance_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Save all processed data to files.

        Files created:
        - data/raw/{activity_id}_raw.json (already created in collect_data)
        - data/parquet/{activity_id}.parquet
        - data/performance/{activity_id}.json
        - data/precheck/{activity_id}.json

        Args:
            activity_id: Activity ID
            raw_data: Raw data dict
            df: Parquet DataFrame
            performance_data: Performance metrics

        Returns:
            File paths dict
        """
        # Save parquet
        parquet_file = self.parquet_dir / f"{activity_id}.parquet"
        df.to_parquet(parquet_file, index=False)
        logger.info(f"Saved parquet to {parquet_file}")

        # Save performance.json
        performance_file = self.performance_dir / f"{activity_id}.json"
        with open(performance_file, "w", encoding="utf-8") as f:
            json.dump(performance_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved performance data to {performance_file}")

        # Save precheck.json (basic validation data)
        precheck_data = {
            "activity_id": activity_id,
            "total_splits": len(df),
            "has_hr_data": bool(
                df["avg_heart_rate"].notna().all()
                if "avg_heart_rate" in df.columns
                else False
            ),
            "has_power_data": bool(
                df["avg_power"].notna().all() if "avg_power" in df.columns else False
            ),
            "has_form_data": bool(
                df["ground_contact_time_ms"].notna().all()
                if "ground_contact_time_ms" in df.columns
                else False
            ),
        }
        precheck_file = self.precheck_dir / f"{activity_id}.json"
        with open(precheck_file, "w", encoding="utf-8") as f:
            json.dump(precheck_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved precheck data to {precheck_file}")

        # Insert splits into DuckDB
        from tools.database.inserters.splits import insert_splits

        splits_success = insert_splits(
            performance_file=str(performance_file),
            activity_id=activity_id,
        )
        if splits_success:
            logger.info(f"Inserted splits to DuckDB for activity {activity_id}")
        else:
            logger.warning(
                f"Failed to insert splits to DuckDB for activity {activity_id}"
            )

        # Insert form_efficiency into DuckDB
        from tools.database.inserters.form_efficiency import insert_form_efficiency

        form_eff_success = insert_form_efficiency(
            performance_file=str(performance_file),
            activity_id=activity_id,
        )
        if form_eff_success:
            logger.info(
                f"Inserted form_efficiency to DuckDB for activity {activity_id}"
            )
        else:
            logger.warning(
                f"Failed to insert form_efficiency to DuckDB for activity {activity_id}"
            )

        # Insert heart_rate_zones into DuckDB
        from tools.database.inserters.heart_rate_zones import insert_heart_rate_zones

        hr_zones_success = insert_heart_rate_zones(
            performance_file=str(performance_file),
            activity_id=activity_id,
        )
        if hr_zones_success:
            logger.info(
                f"Inserted heart_rate_zones to DuckDB for activity {activity_id}"
            )
        else:
            logger.warning(
                f"Failed to insert heart_rate_zones to DuckDB for activity {activity_id}"
            )

        # Insert hr_efficiency into DuckDB
        from tools.database.inserters.hr_efficiency import insert_hr_efficiency

        hr_eff_success = insert_hr_efficiency(
            performance_file=str(performance_file),
            activity_id=activity_id,
        )
        if hr_eff_success:
            logger.info(f"Inserted hr_efficiency to DuckDB for activity {activity_id}")
        else:
            logger.warning(
                f"Failed to insert hr_efficiency to DuckDB for activity {activity_id}"
            )

        # Insert performance_trends into DuckDB
        from tools.database.inserters.performance_trends import (
            insert_performance_trends,
        )

        perf_trends_success = insert_performance_trends(
            performance_file=str(performance_file),
            activity_id=activity_id,
        )
        if perf_trends_success:
            logger.info(
                f"Inserted performance_trends to DuckDB for activity {activity_id}"
            )
        else:
            logger.warning(
                f"Failed to insert performance_trends to DuckDB for activity {activity_id}"
            )

        # Insert lactate_threshold into DuckDB
        from tools.database.inserters.lactate_threshold import insert_lactate_threshold

        lt_success = insert_lactate_threshold(
            performance_file=str(performance_file),
            activity_id=activity_id,
        )
        if lt_success:
            logger.info(
                f"Inserted lactate_threshold to DuckDB for activity {activity_id}"
            )
        else:
            logger.warning(
                f"Failed to insert lactate_threshold to DuckDB for activity {activity_id}"
            )

        # Insert vo2_max into DuckDB
        from tools.database.inserters.vo2_max import insert_vo2_max

        vo2_success = insert_vo2_max(
            performance_file=str(performance_file),
            activity_id=activity_id,
        )
        if vo2_success:
            logger.info(f"Inserted vo2_max to DuckDB for activity {activity_id}")
        else:
            logger.warning(
                f"Failed to insert vo2_max to DuckDB for activity {activity_id}"
            )

        return {
            "raw_file": str(self.raw_dir / f"{activity_id}_raw.json"),
            "parquet_file": str(parquet_file),
            "performance_file": str(performance_file),
            "precheck_file": str(precheck_file),
        }

    def collect_body_composition_data(self, date: str) -> dict[str, Any] | None:
        """
        Collect body composition data with cache-first strategy.

        Cache priority:
        1. Check data/weight_cache/raw/weight_{date}_raw.json
        2. If missing, fetch from Garmin Connect API

        Args:
            date: Date in YYYY-MM-DD format

        Returns:
            Raw weight data dict or None if no data available
        """
        # Check cache first
        weight_file = self.weight_cache_dir / f"weight_{date}_raw.json"
        if weight_file.exists():
            logger.info(f"Using cached body composition data for {date}")
            with open(weight_file, encoding="utf-8") as f:
                return cast(dict[str, Any], json.load(f))

        # Fetch from Garmin Connect API
        logger.info(
            f"Fetching body composition data for {date} from Garmin Connect API"
        )
        try:
            client = self.get_garmin_client()
            # Use get_daily_weigh_ins for single date
            weight_data = client.get_daily_weigh_ins(date)

            if not weight_data or not weight_data.get("dateWeightList"):
                logger.warning(f"No body composition data found for {date}")
                return None

            # Save to cache
            weight_file.parent.mkdir(parents=True, exist_ok=True)
            with open(weight_file, "w", encoding="utf-8") as f:
                json.dump(weight_data, f, indent=2, ensure_ascii=False)

            logger.info(f"Cached body composition data to {weight_file}")
            return weight_data  # type: ignore[no-any-return]

        except Exception as e:
            logger.error(f"Error fetching body composition data for {date}: {e}")
            return None

    def _calculate_median_weight(self, date: str) -> dict[str, Any] | None:
        """
        Calculate median weight from past 7 days including target date.

        Args:
            date: Date in YYYY-MM-DD format

        Returns:
            Dict with median weight data or None
        """
        from datetime import datetime, timedelta

        import numpy as np

        target_date = datetime.strptime(date, "%Y-%m-%d")
        weights = []
        bmi_values = []
        body_fat_values = []
        body_water_values = []
        bone_mass_values = []
        muscle_mass_values = []

        # Collect data from past 7 days (including target date)
        for i in range(7):
            check_date = target_date - timedelta(days=i)
            check_date_str = check_date.strftime("%Y-%m-%d")

            raw_data = self.collect_body_composition_data(check_date_str)
            if raw_data and raw_data.get("dateWeightList"):
                data = raw_data["dateWeightList"][0]

                # Collect weight (convert to kg)
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

        # Calculate medians
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
        """
        Process body composition data - save direct measurements only.

        Pipeline:
        1. Collect body composition data (cache-first)
        2. Insert direct measurements into body_composition table

        Note: Weight median calculation (for W/kg) is done during activity processing
        and stored in activities table, NOT in body_composition table.

        Args:
            date: Date in YYYY-MM-DD format

        Returns:
            Result dict with status
        """
        logger.info(f"Processing body composition data for {date}")

        # Step 1: Collect body composition data (cache-first)
        raw_data = self.collect_body_composition_data(date)

        if not raw_data or not raw_data.get("dateWeightList"):
            logger.warning(f"No body composition data found for {date}")
            return {
                "date": date,
                "status": "no_data",
                "message": f"No body composition data found for {date}",
            }

        # Step 2: Insert direct measurements into DuckDB
        from tools.database.db_writer import GarminDBWriter

        writer = (
            GarminDBWriter(db_path=self._db_path) if self._db_path else GarminDBWriter()
        )
        success = writer.insert_body_composition(date=date, weight_data=raw_data)

        if success:
            # Extract weight for return value
            weight_kg = raw_data["dateWeightList"][0].get("weight", 0) / 1000.0
            logger.info(
                f"Successfully processed body composition data for {date}: {weight_kg:.3f} kg"
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

    def process_activity(self, activity_id: int, date: str) -> dict[str, Any]:
        """
        Process activity through full pipeline.

        Pipeline:
        1. collect_data() - Cache-first data collection
        2. create_parquet_dataset() - Transform to DataFrame
        3. _calculate_split_metrics() - Generate performance.json
        4. Calculate 7-day median weight for W/kg
        5. save_data() - Save all outputs
        6. Insert into DuckDB with weight data

        Args:
            activity_id: Activity ID
            date: Activity date (YYYY-MM-DD)

        Returns:
            Result dict with file paths
        """
        logger.info(f"Processing activity {activity_id} ({date})")

        # Step 1: Collect data (cache-first)
        raw_data = self.collect_data(activity_id)

        # Step 2: Create parquet dataset
        df = self.create_parquet_dataset(raw_data)

        # Step 3: Calculate metrics
        performance_data = self._calculate_split_metrics(df, raw_data)

        # Step 4: Calculate 7-day median weight for W/kg
        median_weight_data = self._calculate_median_weight(date)
        weight_kg = median_weight_data["weight_kg"] if median_weight_data else None

        # Step 5: Save data
        file_paths = self.save_data(activity_id, raw_data, df, performance_data)

        # Step 6: Insert into DuckDB activities table with weight data
        from tools.database.db_writer import GarminDBWriter

        writer = (
            GarminDBWriter(db_path=self._db_path) if self._db_path else GarminDBWriter()
        )
        basic_metrics = performance_data.get("basic_metrics", {})

        # Extract activity metadata from nested structure
        activity_dict = raw_data.get("activity", {})

        writer.insert_activity(
            activity_id=activity_id,
            activity_date=date,
            activity_name=activity_dict.get("activityName"),
            location_name=activity_dict.get("locationName"),
            weight_kg=weight_kg,
            weight_source="statistical_7d_median" if weight_kg else None,
            weight_method="median" if weight_kg else None,
            distance_km=basic_metrics.get("distance_km"),
            duration_seconds=basic_metrics.get("duration_seconds"),
            avg_pace_seconds_per_km=basic_metrics.get("avg_pace_seconds_per_km"),
            avg_heart_rate=basic_metrics.get("avg_heart_rate"),
        )

        return {
            "activity_id": activity_id,
            "date": date,
            "files": file_paths,
            "weight_kg": weight_kg,
            "status": "success",
        }

    def process_activity_by_date(self, date: str) -> dict[str, Any]:
        """
        Process activity by date (resolve activity_id from Garmin API).

        Args:
            date: Activity date (YYYY-MM-DD)

        Returns:
            Result dict with activity_id and file paths

        Raises:
            ValueError: If no activity found for date
            ValueError: If multiple activities found (user must specify activity_id)
        """
        logger.info(f"Resolving activity for date {date}")

        # Get activities for date from Garmin API
        client = self.get_garmin_client()
        api_response = client.get_activities_fordate(date)

        # Extract activities from nested structure
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

        # Single activity found
        activity_id = activities_data[0].get("activityId")
        logger.info(f"Found single activity for {date}: {activity_id}")

        # Process the activity
        return self.process_activity(activity_id, date)
