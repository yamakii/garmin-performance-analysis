"""Raw data fetching with cache-first strategy.

Handles per-API file caching for Garmin Connect data:
- activity_details.json, splits.json, weather.json, gear.json
- hr_zones.json, vo2_max.json, lactate_threshold.json
- weight/{date}.json (body composition)
"""

import json
import logging
from pathlib import Path
from typing import Any, cast

from garmin_mcp.ingest.api_client import get_garmin_client

logger = logging.getLogger(__name__)


class RawDataExtractor:
    """Extract data from raw_data formats.

    Based on Phase 1 investigation:
    - Both old and new formats have activity.summaryDTO.trainingEffect
    - Format detection and legacy support are unnecessary
    """

    def extract_training_effect(self, activity_data: dict) -> dict:
        """Extract training effect from activity data.

        Args:
            activity_data: Activity data dict with summaryDTO

        Returns:
            Dict with aerobicTrainingEffect and anaerobicTrainingEffect
            Empty dict if not found
        """
        summary = activity_data.get("summaryDTO", {})
        if summary:
            result = {}
            if "trainingEffect" in summary:
                result["aerobicTrainingEffect"] = summary["trainingEffect"]
            if "anaerobicTrainingEffect" in summary:
                result["anaerobicTrainingEffect"] = summary["anaerobicTrainingEffect"]
            return result

        return {}

    def extract_from_raw_data(self, raw_data: dict) -> dict:
        """Extract all data from raw_data dict.

        Args:
            raw_data: Raw data with activity key

        Returns:
            Dict with extracted data sections
        """
        result = {}

        # Extract from activity key
        activity = raw_data.get("activity", {})
        if activity:
            te = self.extract_training_effect(activity)
            if te:
                result["training_effect"] = te

        return result


SUPPORTED_API_FILES = {
    "activity_details",
    "splits",
    "weather",
    "gear",
    "hr_zones",
    "vo2_max",
    "lactate_threshold",
}


def load_from_cache(
    raw_dir: Path, activity_id: int, skip_files: set[str] | None = None
) -> dict[str, Any] | None:
    """Load cached raw_data from directory structure.

    Args:
        raw_dir: Base raw data directory
        activity_id: Activity ID
        skip_files: Set of file names to skip loading (for force refetch).
                   Example: {'activity_details', 'weather'}

    Returns:
        Partial or complete raw_data dict. Returns None only if required files
        are missing (and not in skip_files).
    """
    activity_dir = raw_dir / "activity" / str(activity_id)

    if not activity_dir.exists():
        return None

    skip_files = skip_files or set()

    # Required API files
    required_files = [
        ("activity.json", "activity_basic"),
        ("splits.json", "splits"),
        ("weather.json", "weather"),
        ("gear.json", "gear"),
        ("hr_zones.json", "hr_zones"),
        ("vo2_max.json", "vo2_max"),
        ("lactate_threshold.json", "lactate_threshold"),
    ]

    # Check all required files exist (except skipped ones)
    for file_name, _ in required_files:
        skip_key = file_name.replace(".json", "").replace("_", "_")
        if skip_key not in skip_files and not (activity_dir / file_name).exists():
            logger.warning(f"Missing required file: {file_name}")
            return None

    # Load all files (except skipped ones)
    raw_data: dict[str, Any] = {}

    try:
        # Load activity.json (basic info with summaryDTO)
        if (activity_dir / "activity.json").exists():
            with open(activity_dir / "activity.json", encoding="utf-8") as f:
                raw_data["activity_basic"] = json.load(f)

        # Load activity_details.json (chart data) if exists and not skipped
        if (
            "activity_details" not in skip_files
            and (activity_dir / "activity_details.json").exists()
        ):
            with open(activity_dir / "activity_details.json", encoding="utf-8") as f:
                raw_data["activity"] = json.load(f)

        # Load other files (skip if in skip_files)
        file_mappings = [
            ("splits", "splits.json", "splits"),
            ("weather", "weather.json", "weather"),
            ("gear", "gear.json", "gear"),
            ("hr_zones", "hr_zones.json", "hr_zones"),
            ("vo2_max", "vo2_max.json", "vo2_max"),
            ("lactate_threshold", "lactate_threshold.json", "lactate_threshold"),
        ]

        for skip_key, file_name, data_key in file_mappings:
            if skip_key not in skip_files and (activity_dir / file_name).exists():
                with open(activity_dir / file_name, encoding="utf-8") as f:
                    raw_data[data_key] = json.load(f)

        # Extract training_effect from activity_basic.summaryDTO
        activity_basic = raw_data.get("activity_basic", {})
        summary = activity_basic.get("summaryDTO", {})

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

        # Weight data (not stored in cache)
        raw_data["weight"] = None

        logger.info(f"Loaded cached data for activity {activity_id}")
        return raw_data

    except Exception as e:
        logger.error(f"Failed to load cached data for activity {activity_id}: {e}")
        return None


def _fetch_and_cache_json(
    client: Any,
    fetch_func: Any,
    cache_file: Path,
    data_key: str,
    raw_data: dict[str, Any],
    activity_id: int,
    **fetch_kwargs: Any,
) -> None:
    """Fetch data from API and cache to JSON file.

    Args:
        client: Garmin client (unused, kept for API consistency)
        fetch_func: Callable to fetch data
        cache_file: Path to cache file
        data_key: Key in raw_data dict
        raw_data: Raw data dict to update
        activity_id: Activity ID for logging
        **fetch_kwargs: Additional kwargs for fetch_func
    """
    try:
        data = fetch_func(**fetch_kwargs)
        raw_data[data_key] = data
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Cached {data_key} to {cache_file}")
    except Exception as e:
        logger.error(f"Failed to fetch {data_key} for activity {activity_id}: {e}")
        raw_data[data_key] = None


def collect_data(
    raw_dir: Path, activity_id: int, force_refetch: list[str] | None = None
) -> dict[str, Any]:
    """Collect activity data with per-API cache-first strategy.

    **IMPORTANT**: This function ONLY handles raw_data caching, NOT DuckDB caching.

    Cache priority:
    1. Check old format: data/raw/{activity_id}_raw.json (backward compatibility)
    2. Check new format: data/raw/activity/{activity_id}/{api_name}.json
    3. If missing, fetch from Garmin Connect API and save to new format

    Args:
        raw_dir: Base raw data directory
        activity_id: Activity ID
        force_refetch: List of API file names to force refetch.

    Returns:
        Raw data dict with keys: activity, splits, weather, gear, hr_zones, etc.
    """
    # Backward compatibility: Check old format cache first
    old_cache_file = raw_dir / f"{activity_id}_raw.json"
    if old_cache_file.exists():
        logger.info(f"Using old format cached data for activity {activity_id}")
        with open(old_cache_file, encoding="utf-8") as f:
            return cast(dict[str, Any], json.load(f))

    # Normalize force_refetch parameter
    force_refetch_set = set(force_refetch) if force_refetch else set()

    # Validate force_refetch parameter
    if force_refetch_set:
        unsupported = force_refetch_set - SUPPORTED_API_FILES
        if unsupported:
            raise ValueError(
                f"Unsupported force_refetch files: {unsupported}. "
                f"Supported values: {sorted(SUPPORTED_API_FILES)}"
            )

    # Try to load from new cache format
    cached_data = load_from_cache(raw_dir, activity_id, skip_files=force_refetch_set)
    if cached_data is not None and not force_refetch_set:
        # Full cache hit (no force refetch)
        return cached_data

    # Partial cache hit or force refetch - start with cached data
    raw_data = cached_data if cached_data else {}

    # Cache miss - fetch from API
    logger.info(f"Fetching activity {activity_id} from Garmin Connect API")
    client = get_garmin_client()

    # Create activity directory
    activity_dir = raw_dir / "activity" / str(activity_id)
    activity_dir.mkdir(parents=True, exist_ok=True)

    # 0. Activity basic info
    _collect_activity_basic(client, activity_dir, raw_data, activity_id)

    # 1. Activity details (chart data with dynamic maxchart)
    _collect_activity_details(
        client, activity_dir, raw_data, activity_id, force_refetch_set
    )

    # 2-5. Standard API endpoints
    _collect_standard_apis(
        client, activity_dir, raw_data, activity_id, force_refetch_set
    )

    # 6. VO2 max (requires activity date)
    _collect_vo2_max(client, activity_dir, raw_data, activity_id, force_refetch_set)

    # 7. Lactate threshold
    _collect_lactate_threshold(
        client, activity_dir, raw_data, activity_id, force_refetch_set
    )

    # Extract training_effect from activity_basic.summaryDTO if available
    activity_basic = raw_data.get("activity_basic", {})
    summary = activity_basic.get("summaryDTO", {}) if activity_basic else {}
    if summary:
        raw_data["training_effect"] = {
            "aerobicTrainingEffect": summary.get("trainingEffect"),
            "anaerobicTrainingEffect": summary.get("anaerobicTrainingEffect"),
            "aerobicTrainingEffectMessage": summary.get("aerobicTrainingEffectMessage"),
            "anaerobicTrainingEffectMessage": summary.get(
                "anaerobicTrainingEffectMessage"
            ),
            "trainingEffectLabel": summary.get("trainingEffectLabel"),
        }

    # Weight data (requires separate weight cache manager)
    raw_data["weight"] = None

    logger.info(f"Completed data collection for activity {activity_id}")
    return raw_data


def _collect_activity_basic(
    client: Any,
    activity_dir: Path,
    raw_data: dict[str, Any],
    activity_id: int,
) -> None:
    """Collect activity basic info (summaryDTO)."""
    activity_basic_file = activity_dir / "activity.json"
    if activity_basic_file.exists() and "activity_basic" not in raw_data:
        logger.info(f"Using cached activity basic info for {activity_id}")
        with open(activity_basic_file, encoding="utf-8") as f:
            raw_data["activity_basic"] = json.load(f)
    elif "activity_basic" not in raw_data:
        try:
            activity_basic = client.get_activity(str(activity_id))
            raw_data["activity_basic"] = activity_basic
            with open(activity_basic_file, "w", encoding="utf-8") as f:
                json.dump(activity_basic, f, ensure_ascii=False, indent=2)
            logger.info(f"Cached activity basic info to {activity_basic_file}")
        except Exception as e:
            logger.error(f"Failed to fetch activity basic info: {e}")
            raw_data["activity_basic"] = None


def _collect_activity_details(
    client: Any,
    activity_dir: Path,
    raw_data: dict[str, Any],
    activity_id: int,
    force_refetch_set: set[str],
) -> None:
    """Collect activity details (chart data with dynamic maxchart)."""
    activity_file = activity_dir / "activity_details.json"
    if (
        activity_file.exists()
        and "activity_details" not in force_refetch_set
        and "activity" not in raw_data
    ):
        logger.info(f"Using cached activity_details for {activity_id}")
        with open(activity_file, encoding="utf-8") as f:
            raw_data["activity"] = json.load(f)
    elif "activity" not in raw_data or "activity_details" in force_refetch_set:
        try:
            # Calculate maxchart dynamically from activity duration
            activity_basic = raw_data.get("activity_basic", {})
            summary = activity_basic.get("summaryDTO", {})
            duration_seconds = summary.get("duration", 0)

            # maxchart = duration * 1.5 (buffer), constrained to [2000, 10000]
            calculated_maxchart = int(duration_seconds * 1.5)
            maxchart = max(2000, min(calculated_maxchart, 10000))

            logger.info(
                f"Activity duration: {duration_seconds}s "
                f"({duration_seconds/60:.1f}min), using maxchart={maxchart}"
            )

            activity_data = client.get_activity_details(activity_id, maxchart=maxchart)
            raw_data["activity"] = activity_data
            with open(activity_file, "w", encoding="utf-8") as f:
                json.dump(activity_data, f, ensure_ascii=False, indent=2)
            logger.info(f"Cached activity_details to {activity_file}")
        except Exception as e:
            logger.error(f"Failed to fetch activity_details: {e}")
            raw_data["activity"] = None


def _collect_standard_apis(
    client: Any,
    activity_dir: Path,
    raw_data: dict[str, Any],
    activity_id: int,
    force_refetch_set: set[str],
) -> None:
    """Collect splits, weather, gear, hr_zones."""
    standard_apis = [
        ("splits", "splits.json", "splits", client.get_activity_splits),
        ("weather", "weather.json", "weather", client.get_activity_weather),
        ("gear", "gear.json", "gear", client.get_activity_gear),
        (
            "hr_zones",
            "hr_zones.json",
            "hr_zones",
            client.get_activity_hr_in_timezones,
        ),
    ]

    for api_name, file_name, data_key, fetch_func in standard_apis:
        cache_file = activity_dir / file_name
        if (
            cache_file.exists()
            and api_name not in force_refetch_set
            and data_key not in raw_data
        ):
            logger.info(f"Using cached {api_name} for {activity_id}")
            with open(cache_file, encoding="utf-8") as f:
                raw_data[data_key] = json.load(f)
        elif data_key not in raw_data or api_name in force_refetch_set:
            try:
                data = fetch_func(activity_id)
                raw_data[data_key] = data
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                logger.info(f"Cached {api_name} to {cache_file}")
            except Exception as e:
                logger.error(f"Failed to fetch {api_name}: {e}")
                raw_data[data_key] = None


def _collect_vo2_max(
    client: Any,
    activity_dir: Path,
    raw_data: dict[str, Any],
    activity_id: int,
    force_refetch_set: set[str],
) -> None:
    """Collect VO2 max data (requires activity date)."""
    vo2_max_file = activity_dir / "vo2_max.json"
    if (
        vo2_max_file.exists()
        and "vo2_max" not in force_refetch_set
        and "vo2_max" not in raw_data
    ):
        logger.info(f"Using cached vo2_max for {activity_id}")
        with open(vo2_max_file, encoding="utf-8") as f:
            raw_data["vo2_max"] = json.load(f)
    elif "vo2_max" not in raw_data or "vo2_max" in force_refetch_set:
        # Extract activity date from activity.summaryDTO
        activity_data = raw_data.get("activity", {})
        summary = activity_data.get("summaryDTO", {}) if activity_data else {}
        start_time_local = summary.get("startTimeLocal", "")

        # Fallback to activity_basic if activity not available
        if not start_time_local:
            activity_basic = raw_data.get("activity_basic", {})
            summary = activity_basic.get("summaryDTO", {}) if activity_basic else {}
            start_time_local = summary.get("startTimeLocal", "")

        if start_time_local:
            activity_date = start_time_local.split("T")[0]
            try:
                max_metrics = client.get_max_metrics(activity_date)
                generic_metrics = max_metrics.get("generic", {})
                vo2_max_data = {
                    "vo2MaxValue": generic_metrics.get("vo2MaxValue"),
                    "vo2MaxPreciseValue": generic_metrics.get("vo2MaxPreciseValue"),
                    "calendarDate": generic_metrics.get("calendarDate"),
                }
                raw_data["vo2_max"] = vo2_max_data
                with open(vo2_max_file, "w", encoding="utf-8") as f:
                    json.dump(vo2_max_data, f, ensure_ascii=False, indent=2)
                logger.info(f"Cached vo2_max to {vo2_max_file}")
            except Exception as e:
                logger.warning(f"Failed to fetch VO2 max data: {e}")
                raw_data["vo2_max"] = {}
                with open(vo2_max_file, "w", encoding="utf-8") as f:
                    json.dump({}, f, ensure_ascii=False, indent=2)
        else:
            raw_data["vo2_max"] = {}
            with open(vo2_max_file, "w", encoding="utf-8") as f:
                json.dump({}, f, ensure_ascii=False, indent=2)


def _collect_lactate_threshold(
    client: Any,
    activity_dir: Path,
    raw_data: dict[str, Any],
    activity_id: int,
    force_refetch_set: set[str],
) -> None:
    """Collect lactate threshold data."""
    lactate_file = activity_dir / "lactate_threshold.json"
    if (
        lactate_file.exists()
        and "lactate_threshold" not in force_refetch_set
        and "lactate_threshold" not in raw_data
    ):
        logger.info(f"Using cached lactate_threshold for {activity_id}")
        with open(lactate_file, encoding="utf-8") as f:
            raw_data["lactate_threshold"] = json.load(f)
    elif (
        "lactate_threshold" not in raw_data or "lactate_threshold" in force_refetch_set
    ):
        try:
            lactate_threshold_data = client.get_lactate_threshold(latest=True)
            raw_data["lactate_threshold"] = lactate_threshold_data
            with open(lactate_file, "w", encoding="utf-8") as f:
                json.dump(lactate_threshold_data, f, ensure_ascii=False, indent=2)
            logger.info(f"Cached lactate_threshold to {lactate_file}")
        except Exception as e:
            logger.warning(f"Failed to fetch lactate threshold data: {e}")
            default_lactate = {
                "speed_and_heart_rate": None,
                "power": None,
            }
            raw_data["lactate_threshold"] = default_lactate
            with open(lactate_file, "w", encoding="utf-8") as f:
                json.dump(default_lactate, f, ensure_ascii=False, indent=2)


def collect_body_composition_data(
    weight_raw_dir: Path, date: str
) -> dict[str, Any] | None:
    """Collect body composition data with cache-first strategy.

    Cache priority:
    1. Check data/raw/weight/{date}.json
    2. If missing, fetch from Garmin Connect API

    Args:
        weight_raw_dir: Weight raw data directory
        date: Date in YYYY-MM-DD format

    Returns:
        Raw weight data dict or None if no data available
    """
    # Check cache first
    weight_file = weight_raw_dir / f"{date}.json"
    if weight_file.exists():
        with open(weight_file, encoding="utf-8") as f:
            cached_data = json.load(f)
            # Empty dict indicates no data available (marker file)
            if not cached_data:
                logger.debug(f"Empty marker file found for {date}, skipping API call")
                return None
            logger.info(f"Using cached body composition data for {date}")
            return cast(dict[str, Any], cached_data)

    # Fetch from Garmin Connect API
    logger.info(f"Fetching body composition data for {date} from Garmin Connect API")
    try:
        client = get_garmin_client()
        weight_data = client.get_daily_weigh_ins(date)

        if not weight_data or not weight_data.get("dateWeightList"):
            logger.warning(f"No body composition data found for {date}")
            # Create empty marker file to avoid repeated API calls
            weight_file.parent.mkdir(parents=True, exist_ok=True)
            with open(weight_file, "w", encoding="utf-8") as f:
                json.dump({}, f)
            logger.info(f"Created empty marker file: {weight_file}")
            return None

        # Save to cache
        weight_file.parent.mkdir(parents=True, exist_ok=True)
        with open(weight_file, "w", encoding="utf-8") as f:
            json.dump(weight_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Cached body composition data to {weight_file}")
        return weight_data  # type: ignore[no-any-return]

    except Exception as e:
        logger.error(f"Error fetching body composition data for {date}: {e}")
        # Create empty marker file to avoid repeated API calls
        weight_file.parent.mkdir(parents=True, exist_ok=True)
        with open(weight_file, "w", encoding="utf-8") as f:
            json.dump({}, f)
        logger.info(f"Created empty marker file after error: {weight_file}")
        return None
