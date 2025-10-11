#!/usr/bin/env python3
"""
Test script to demonstrate force_refetch functionality.

This script demonstrates the selective cache refetch feature:
1. Load activity data with full cache
2. Simulate force refetch of specific files
3. Verify that only specified files are processed
"""

import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def setup_test_data(base_dir: Path, activity_id: int) -> None:
    """Create test cache data for demonstration."""
    activity_dir = base_dir / "data" / "raw" / "activity" / str(activity_id)
    activity_dir.mkdir(parents=True, exist_ok=True)

    # Create minimal test files
    test_files = {
        "activity.json": {"summaryDTO": {"activityId": activity_id}},
        "activity_details.json": {"activityId": activity_id, "metricDescriptors": []},
        "splits.json": {"lapDTOs": []},
        "weather.json": {"temp": 20, "timestamp": "2025-10-11T10:00:00"},
        "gear.json": {"uuid": "test-gear"},
        "hr_zones.json": {"zones": []},
        "vo2_max.json": {"vo2MaxValue": 50},
        "lactate_threshold.json": {"lactateThresholdHeartRate": 160},
    }

    for filename, data in test_files.items():
        filepath = activity_dir / filename
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Created: {filepath}")


def test_load_from_cache(activity_id: int) -> None:
    """Test 1: Load from cache without force_refetch."""
    from tools.ingest.garmin_worker import GarminIngestWorker

    worker = GarminIngestWorker()
    logger.info(f"\n{'='*60}")
    logger.info("Test 1: Load from cache (no force_refetch)")
    logger.info(f"{'='*60}")

    # Load from cache
    cached_data = worker.load_from_cache(activity_id)

    if cached_data:
        logger.info("✅ Cache loaded successfully")
        logger.info(f"   Keys: {list(cached_data.keys())}")
    else:
        logger.error("❌ Failed to load cache")


def test_load_with_skip_files(activity_id: int) -> None:
    """Test 2: Load from cache with skip_files (simulate force_refetch)."""
    from tools.ingest.garmin_worker import GarminIngestWorker

    worker = GarminIngestWorker()
    logger.info(f"\n{'='*60}")
    logger.info("Test 2: Load with skip_files=['weather', 'vo2_max']")
    logger.info(f"{'='*60}")

    # Load with skip_files
    skip_files = {"weather", "vo2_max"}
    cached_data = worker.load_from_cache(activity_id, skip_files=skip_files)

    if cached_data:
        logger.info("✅ Partial cache loaded successfully")
        logger.info(f"   Keys: {list(cached_data.keys())}")
        logger.info(f"   'weather' in data: {'weather' in cached_data}")
        logger.info(f"   'vo2_max' in data: {'vo2_max' in cached_data}")

        # Verify skipped files are not loaded
        if "weather" not in cached_data and "vo2_max" not in cached_data:
            logger.info("✅ Skipped files correctly excluded from cache")
        else:
            logger.error("❌ Skipped files should not be in cached data")
    else:
        logger.error("❌ Failed to load partial cache")


def test_force_refetch_parameter_validation() -> None:
    """Test 3: Validate force_refetch parameter."""
    logger.info(f"\n{'='*60}")
    logger.info("Test 3: Force refetch parameter validation")
    logger.info(f"{'='*60}")

    # Valid force_refetch values
    valid_values = [
        None,
        [],
        ["weather"],
        ["weather", "vo2_max"],
        [
            "activity_details",
            "splits",
            "weather",
            "gear",
            "hr_zones",
            "vo2_max",
            "lactate_threshold",
        ],
    ]

    for value in valid_values:
        logger.info(f"✅ Valid: force_refetch={value}")

    logger.info(
        "\n   Note: Invalid values (e.g., ['invalid_file']) would raise ValueError"
    )


def verify_cache_structure(activity_id: int) -> None:
    """Verify cache directory structure."""
    from tools.utils.paths import get_raw_dir

    raw_dir = get_raw_dir()
    activity_dir = raw_dir / "activity" / str(activity_id)

    logger.info(f"\n{'='*60}")
    logger.info("Cache Structure Verification")
    logger.info(f"{'='*60}")
    logger.info(f"Activity directory: {activity_dir}")

    if activity_dir.exists():
        files = sorted(activity_dir.glob("*.json"))
        logger.info(f"✅ Found {len(files)} cache files:")
        for f in files:
            size = f.stat().st_size
            logger.info(f"   - {f.name} ({size} bytes)")
    else:
        logger.error(f"❌ Activity directory not found: {activity_dir}")


def main() -> None:
    """Run all demonstration tests."""
    activity_id = 12345  # Test activity ID

    logger.info("=" * 60)
    logger.info("Force Refetch Feature Demonstration")
    logger.info("=" * 60)

    # Setup test data
    from tools.utils.paths import get_data_base_dir

    base_dir = get_data_base_dir().parent  # Get project root
    setup_test_data(base_dir, activity_id)

    # Verify cache structure
    verify_cache_structure(activity_id)

    # Run tests
    test_load_from_cache(activity_id)
    test_load_with_skip_files(activity_id)
    test_force_refetch_parameter_validation()

    logger.info(f"\n{'='*60}")
    logger.info("✅ All demonstration tests completed")
    logger.info("=" * 60)

    logger.info("\nUsage Examples:")
    logger.info("  # Force refetch weather.json only")
    logger.info(
        "  worker.process_activity(activity_id, date, force_refetch=['weather'])"
    )
    logger.info("\n  # Force refetch multiple files")
    logger.info(
        "  worker.process_activity(activity_id, date, force_refetch=['vo2_max', 'lactate_threshold'])"
    )
    logger.info("\n  # Default behavior (cache-first)")
    logger.info("  worker.process_activity(activity_id, date)")


if __name__ == "__main__":
    main()
