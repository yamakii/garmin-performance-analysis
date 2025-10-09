#!/usr/bin/env python3
"""
Migrate raw_data from old single-file format to new per-API directory structure.

Old format: data/raw/{activity_id}_raw.json (single file)
New format: data/raw/activity/{activity_id}/{api_name}.json (directory with multiple files)
"""

import json
import logging
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def split_raw_data_to_new_structure(
    activity_id: int,
    raw_dir: Path,
    dry_run: bool = False,
    archive_old: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    """
    Split old format raw_data into new directory structure.

    Args:
        activity_id: Activity ID
        raw_dir: Raw data directory path
        dry_run: If True, only show what would be done
        archive_old: If True, move old file to archived/ directory
        overwrite: If True, overwrite existing new structure

    Returns:
        Result dict with success status and details
    """
    # Check old file exists
    old_file = raw_dir / f"{activity_id}_raw.json"
    if not old_file.exists():
        return {
            "success": False,
            "activity_id": activity_id,
            "error": f"Old file not found: {old_file}",
        }

    # Check new directory
    new_dir = raw_dir / "activity" / str(activity_id)
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

    # Split data into individual files
    api_files = {
        "activity_details.json": raw_data.get("activity"),
        "splits.json": raw_data.get("splits"),
        "weather.json": raw_data.get("weather"),
        "gear.json": raw_data.get("gear"),
        "hr_zones.json": raw_data.get("hr_zones"),
        "vo2_max.json": raw_data.get("vo2_max"),
        "lactate_threshold.json": raw_data.get("lactate_threshold"),
    }

    files_created = []
    for file_name, data in api_files.items():
        file_path = new_dir / file_name
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            files_created.append(str(file_path))
        except Exception as e:
            logger.warning(f"Failed to write {file_name}: {e}")

    # Archive old file if requested
    if archive_old:
        archive_dir = raw_dir / "archived"
        archive_dir.mkdir(exist_ok=True)
        archive_file = archive_dir / f"{activity_id}_raw.json"
        shutil.move(str(old_file), str(archive_file))

    return {
        "success": True,
        "activity_id": activity_id,
        "old_file": str(old_file),
        "new_dir": str(new_dir),
        "files_created": files_created,
        "archived": archive_old,
    }


def migrate_all_raw_data_files(
    raw_dir: Path,
    dry_run: bool = False,
    archive_old: bool = False,
) -> list[dict[str, Any]]:
    """
    Migrate all old format raw_data files in directory.

    Args:
        raw_dir: Raw data directory path
        dry_run: If True, only show what would be done
        archive_old: If True, move old files to archived/ directory

    Returns:
        List of migration results
    """
    # Find all old format files
    old_files = list(raw_dir.glob("*_raw.json"))

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
            raw_dir=raw_dir,
            dry_run=dry_run,
            archive_old=archive_old,
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

    parser = argparse.ArgumentParser(description="Migrate raw_data to new structure")
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path("data/raw"),
        help="Raw data directory (default: data/raw)",
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
    parser.add_argument(
        "--archive-old",
        action="store_true",
        help="Archive old files to archived/ directory",
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
            raw_dir=args.raw_dir,
            dry_run=args.dry_run,
            archive_old=args.archive_old,
        )
        print(json.dumps(result, indent=2))
    else:
        # Migrate all
        results = migrate_all_raw_data_files(
            raw_dir=args.raw_dir,
            dry_run=args.dry_run,
            archive_old=args.archive_old,
        )
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
