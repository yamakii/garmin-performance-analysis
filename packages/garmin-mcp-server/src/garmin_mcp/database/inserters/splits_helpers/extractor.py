"""Raw splits.json data extraction."""

import json
import logging
from pathlib import Path

from garmin_mcp.database.inserters.splits_helpers.phase_mapping import PhaseMapper
from garmin_mcp.database.inserters.splits_helpers.terrain import TerrainClassifier

logger = logging.getLogger(__name__)


class SplitsExtractor:
    """Extract split metrics from raw splits.json files."""

    @staticmethod
    def extract_splits_from_raw(raw_splits_file: str) -> list[dict] | None:
        """
        Extract split metrics from raw splits.json.

        Args:
            raw_splits_file: Path to splits.json

        Returns:
            List of split dictionaries matching performance.json split_metrics structure
        """
        splits_path = Path(raw_splits_file)
        if not splits_path.exists():
            logger.error(f"Splits file not found: {raw_splits_file}")
            return None

        with open(splits_path, encoding="utf-8") as f:
            splits_data = json.load(f)

        lap_dtos = splits_data.get("lapDTOs", [])
        if not lap_dtos:
            logger.error("No lapDTOs found in splits.json")
            return None

        splits = []
        cumulative_time = 0

        for lap in lap_dtos:
            lap_index = lap.get("lapIndex")
            if lap_index is None:
                continue

            # Distance (convert m to km)
            distance_m = lap.get("distance", 0)
            distance_km = distance_m / 1000.0 if distance_m else None

            # Duration
            duration_seconds = lap.get("duration")

            # Time range
            start_time_gmt = lap.get("startTimeGMT")
            start_time_s = cumulative_time
            if duration_seconds:
                end_time_s = cumulative_time + round(duration_seconds)
                cumulative_time = end_time_s
            else:
                end_time_s = None

            # Pace (seconds per km)
            if distance_km and distance_km > 0 and duration_seconds:
                pace_seconds_per_km = duration_seconds / distance_km
            else:
                pace_seconds_per_km = None

            # Format pace string
            if pace_seconds_per_km:
                minutes = int(pace_seconds_per_km // 60)
                seconds = int(pace_seconds_per_km % 60)
                pace_str = f"{minutes}:{seconds:02d}"
            else:
                pace_str = None

            # Intensity type and role phase
            intensity_type = lap.get("intensityType")
            role_phase = PhaseMapper.map_intensity_to_phase(intensity_type)

            # HR
            avg_hr = lap.get("averageHR")

            # Cadence
            avg_cadence = lap.get("averageRunCadence")

            # Power
            avg_power = lap.get("averagePower")

            # Form metrics
            gct = lap.get("groundContactTime")
            vo = lap.get("verticalOscillation")
            vr = lap.get("verticalRatio")

            # Elevation
            elevation_gain = lap.get("elevationGain", 0)
            elevation_loss = lap.get("elevationLoss", 0)
            terrain_type = TerrainClassifier.classify_terrain(
                elevation_gain, elevation_loss
            )

            # NEW FIELDS (Phase 1): Add 7 missing performance metrics
            stride_length = lap.get("strideLength")  # cm
            max_hr = lap.get("maxHR")  # bpm
            max_cadence = lap.get("maxRunCadence")  # spm
            max_power = lap.get("maxPower")  # W
            normalized_power = lap.get("normalizedPower")  # W
            average_speed = lap.get("averageSpeed")  # m/s
            grade_adjusted_speed = lap.get("avgGradeAdjustedSpeed")  # m/s

            split_dict = {
                "split_number": lap_index,
                "distance_km": distance_km,
                "duration_seconds": duration_seconds,
                "start_time_gmt": start_time_gmt,
                "start_time_s": start_time_s,
                "end_time_s": end_time_s,
                "intensity_type": intensity_type,
                "role_phase": role_phase,
                "pace_str": pace_str,
                "pace_seconds_per_km": pace_seconds_per_km,
                "avg_heart_rate": avg_hr,
                "avg_cadence": avg_cadence,
                "avg_power": avg_power,
                "ground_contact_time_ms": gct,
                "vertical_oscillation_cm": vo,
                "vertical_ratio_percent": vr,
                "elevation_gain_m": elevation_gain,
                "elevation_loss_m": elevation_loss,
                "terrain_type": terrain_type,
                # NEW FIELDS (Phase 1): 7 missing performance metrics
                "stride_length_cm": stride_length,
                "max_heart_rate": max_hr,
                "max_cadence": max_cadence,
                "max_power": max_power,
                "normalized_power": normalized_power,
                "average_speed_mps": average_speed,
                "grade_adjusted_speed_mps": grade_adjusted_speed,
            }

            splits.append(split_dict)

        return splits
