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
from typing import Any, cast

import pandas as pd
from garminconnect import Garmin

logger = logging.getLogger(__name__)


class GarminIngestWorker:
    """Data ingestion worker with cache-first strategy."""

    # Singleton Garmin client (reuse authentication)
    _garmin_client: Garmin | None = None

    def __init__(self):
        """Initialize GarminIngestWorker."""
        self.project_root = Path(__file__).parent.parent.parent
        self.raw_dir = self.project_root / "data" / "raw"
        self.parquet_dir = self.project_root / "data" / "parquet"
        self.performance_dir = self.project_root / "data" / "performance"
        self.precheck_dir = self.project_root / "data" / "precheck"

        # Create directories
        for directory in [
            self.raw_dir,
            self.parquet_dir,
            self.performance_dir,
            self.precheck_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)

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
        raw_data = {
            "activity": client.get_activity_data(activity_id),
            "splits": client.get_activity_splits(activity_id),
            "weather": client.get_activity_weather(activity_id),
            "gear": client.get_activity_gear(activity_id),
            "hr_zones": client.get_activity_hr_in_timezones(activity_id),
        }

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

            record = {
                "split_number": idx,
                "distance_km": distance_km,
                "duration_seconds": duration_seconds,
                "avg_pace_seconds_per_km": avg_pace,
                "avg_heart_rate": lap.get("averageHR"),
                "avg_cadence": lap.get("averageRunCadence"),
                "avg_power": lap.get("avgPower"),
                "ground_contact_time_ms": lap.get("groundContactTime"),
                "vertical_oscillation_cm": lap.get("verticalOscillation"),
                "vertical_ratio_percent": lap.get("verticalRatio"),
                "elevation_gain_m": elevation_gain,
                "elevation_loss_m": lap.get("elevationLoss", 0),
                "max_elevation_m": lap.get("maxElevation"),
                "min_elevation_m": lap.get("minElevation"),
                "terrain_type": terrain_type,
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

        # 8. Lactate threshold (from raw activity data)
        lactate_threshold = {
            "lactate_threshold_hr": activity.get("lactateThresholdHeartRate"),
            "lactate_threshold_speed": activity.get("lactateThresholdSpeed"),
        }

        # 9. Form efficiency summary (Phase 1)
        form_efficiency_summary = self._calculate_form_efficiency_summary(df)

        # 10. HR efficiency analysis (Phase 1)
        hr_efficiency_analysis = self._calculate_hr_efficiency_analysis(df, hr_zones)

        # 11. Performance trends (Phase 2)
        performance_trends = self._calculate_performance_trends(df)

        return {
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
        Calculate performance trends (Phase 2 optimization).

        Returns:
            Phase-based analysis and consistency metrics
        """
        if df.empty or len(df) < 3:
            return {}

        # Split into phases (warmup: first 20%, main: middle 60%, finish: last 20%)
        total_splits = len(df)
        warmup_end = max(1, int(total_splits * 0.2))
        finish_start = max(warmup_end + 1, int(total_splits * 0.8))

        warmup_df = df.iloc[:warmup_end]
        main_df = df.iloc[warmup_end:finish_start]
        finish_df = df.iloc[finish_start:]

        # Calculate phase metrics
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

        # Pace consistency (coefficient of variation)
        pace_consistency = (
            df["avg_pace_seconds_per_km"].std() / df["avg_pace_seconds_per_km"].mean()
            if df["avg_pace_seconds_per_km"].mean() > 0
            else 0
        )

        # HR drift (warmup to finish)
        hr_drift_percentage = (
            (finish_phase["avg_hr"] - warmup_phase["avg_hr"])
            / warmup_phase["avg_hr"]
            * 100
            if warmup_phase["avg_hr"] > 0
            else 0
        )

        # Fatigue pattern
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

        return {
            "raw_file": str(self.raw_dir / f"{activity_id}_raw.json"),
            "parquet_file": str(parquet_file),
            "performance_file": str(performance_file),
            "precheck_file": str(precheck_file),
        }

    def process_activity(self, activity_id: int, date: str) -> dict[str, Any]:
        """
        Process activity through full pipeline.

        Pipeline:
        1. collect_data() - Cache-first data collection
        2. create_parquet_dataset() - Transform to DataFrame
        3. _calculate_split_metrics() - Generate performance.json
        4. save_data() - Save all outputs

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

        # Step 4: Save data
        file_paths = self.save_data(activity_id, raw_data, df, performance_data)

        return {
            "activity_id": activity_id,
            "date": date,
            "files": file_paths,
            "status": "success",
        }
