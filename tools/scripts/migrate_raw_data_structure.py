#!/usr/bin/env python3
"""
Migrate raw_data from old single-file format to new per-API directory structure.

Old format: data/raw/{activity_id}_raw.json (single file)
New format: data/raw/activity/{activity_id}/{api_name}.json (directory with multiple files)
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def split_raw_data_to_new_structure(
    activity_id: int,
    source_dir: Path,
    output_dir: Path,
    dry_run: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    """
    Split old format raw_data into new directory structure.

    Args:
        activity_id: Activity ID
        source_dir: Source directory containing {activity_id}_raw.json files
        output_dir: Output directory for new structure (will create activity/ subdirectory)
        dry_run: If True, only show what would be done
        overwrite: If True, overwrite existing new structure

    Returns:
        Result dict with success status and details
    """
    # Check old file exists in source
    old_file = source_dir / f"{activity_id}_raw.json"
    if not old_file.exists():
        return {
            "success": False,
            "activity_id": activity_id,
            "error": f"Old file not found: {old_file}",
        }

    # Check new directory in output
    new_dir = output_dir / "activity" / str(activity_id)
    if new_dir.exists() and not overwrite:
        return {
            "success": False,
            "activity_id": activity_id,
            "error": f"New directory already exists: {new_dir}",
        }

    # Load old format data
    try:
        with open(old_file, encoding="utf-8") as f:
            raw_data = json.load(f)
    except Exception as e:
        return {
            "success": False,
            "activity_id": activity_id,
            "error": f"Failed to load old file: {e}",
        }

    if dry_run:
        return {
            "success": True,
            "activity_id": activity_id,
            "dry_run": True,
            "old_file": str(old_file),
            "new_dir": str(new_dir),
        }

    # Create new directory structure
    new_dir.mkdir(parents=True, exist_ok=True)

    # Determine activity data type and save appropriately
    activity_data = raw_data.get("activity")
    files_created = []

    if activity_data:
        has_summary_dto = "summaryDTO" in activity_data
        has_chart_data = "metricDescriptors" in activity_data

        if has_summary_dto:
            # Basic info with summaryDTO -> activity.json
            activity_file = new_dir / "activity.json"
            with open(activity_file, "w", encoding="utf-8") as f:
                json.dump(activity_data, f, ensure_ascii=False, indent=2)
            files_created.append(str(activity_file))

        if has_chart_data:
            # Chart data with metricDescriptors -> activity_details.json
            activity_details_file = new_dir / "activity_details.json"
            with open(activity_details_file, "w", encoding="utf-8") as f:
                json.dump(activity_data, f, ensure_ascii=False, indent=2)
            files_created.append(str(activity_details_file))

    # Save other API files
    other_files = {
        "splits.json": raw_data.get("splits"),
        "weather.json": raw_data.get("weather"),
        "gear.json": raw_data.get("gear"),
        "hr_zones.json": raw_data.get("hr_zones"),
        "vo2_max.json": raw_data.get("vo2_max"),
        "lactate_threshold.json": raw_data.get("lactate_threshold"),
    }

    for file_name, data in other_files.items():
        file_path = new_dir / file_name
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            files_created.append(str(file_path))
        except Exception as e:
            logger.warning(f"Failed to write {file_name}: {e}")

    return {
        "success": True,
        "activity_id": activity_id,
        "old_file": str(old_file),
        "new_dir": str(new_dir),
        "files_created": files_created,
    }


def migrate_all_raw_data_files(
    source_dir: Path,
    output_dir: Path,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """
    Migrate all old format raw_data files in directory.

    Args:
        source_dir: Source directory containing {activity_id}_raw.json files
        output_dir: Output directory for new structure
        dry_run: If True, only show what would be done

    Returns:
        List of migration results
    """
    # Find all old format files in source directory
    old_files = list(source_dir.glob("*_raw.json"))

    results = []
    for old_file in old_files:
        # Extract activity_id from filename
        activity_id_str = old_file.stem.replace("_raw", "")
        try:
            activity_id = int(activity_id_str)
        except ValueError:
            logger.warning(f"Skipping invalid filename: {old_file}")
            continue

        # Migrate
        result = split_raw_data_to_new_structure(
            activity_id=activity_id,
            source_dir=source_dir,
            output_dir=output_dir,
            dry_run=dry_run,
        )
        results.append(result)

        if result["success"]:
            logger.info(f"Migrated activity {activity_id}")
        else:
            logger.error(
                f"Failed to migrate activity {activity_id}: {result.get('error')}"
            )

    return results


def main():
    """CLI entry point for migration script."""
    import argparse

    from tools.utils.paths import get_raw_dir

    parser = argparse.ArgumentParser(description="Migrate raw_data to new structure")
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=get_raw_dir().parent / "archive" / "raw",
        help="Source directory with old format files (default: data/archive/raw)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=get_raw_dir(),
        help="Output directory for new structure (default: data/raw)",
    )
    parser.add_argument(
        "--activity-id",
        type=int,
        help="Migrate specific activity ID (if not provided, migrate all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode (don't create files)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    if args.activity_id:
        # Migrate specific activity
        result = split_raw_data_to_new_structure(
            activity_id=args.activity_id,
            source_dir=args.source_dir,
            output_dir=args.output_dir,
            dry_run=args.dry_run,
        )
        print(json.dumps(result, indent=2))
    else:
        # Migrate all
        results = migrate_all_raw_data_files(
            source_dir=args.source_dir,
            output_dir=args.output_dir,
            dry_run=args.dry_run,
        )
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
