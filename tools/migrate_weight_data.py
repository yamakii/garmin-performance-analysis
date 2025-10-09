#!/usr/bin/env python3
"""CLI script for migrating weight data from old to new structure.

Usage:
    # Dry-run mode (no actual changes)
    python tools/migrate_weight_data.py --dry-run --all

    # Migrate all files
    python tools/migrate_weight_data.py --all

    # Migrate single date
    python tools/migrate_weight_data.py --date 2025-05-15

    # Verify migration
    python tools/migrate_weight_data.py --verify

    # Cleanup old structure (requires successful verification)
    python tools/migrate_weight_data.py --cleanup
"""

import argparse
import sys
from pathlib import Path

from weight_data_migrator import WeightDataMigrator


def main() -> int:
    """Main entry point for weight data migration CLI."""
    parser = argparse.ArgumentParser(
        description="Migrate weight data from data/weight_cache/ to data/raw/weight/"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making actual changes",
    )
    parser.add_argument(
        "--date",
        type=str,
        help="Migrate single date (YYYY-MM-DD format)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Migrate all weight data files",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify migration integrity",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete old structure after verification",
    )

    args = parser.parse_args()

    # Validate arguments
    if not any([args.date, args.all, args.verify, args.cleanup]):
        parser.error("Must specify one of: --date, --all, --verify, or --cleanup")

    # Initialize migrator
    project_root = Path(__file__).parent.parent
    migrator = WeightDataMigrator(project_root, dry_run=args.dry_run)

    try:
        # Execute requested operation
        if args.date:
            print(f"Migrating date: {args.date}")
            if args.dry_run:
                print("DRY-RUN MODE: No actual changes will be made")

            result = migrator.migrate_single_date(args.date)
            if result:
                print(f"✓ Successfully migrated {args.date}")
            else:
                print(f"✗ Failed to migrate {args.date} (source file not found)")
                return 1

        elif args.all:
            print("Migrating all weight data files...")
            if args.dry_run:
                print("DRY-RUN MODE: No actual changes will be made")

            report = migrator.migrate_all()
            print("\nMigration Report:")
            print(f"  Total files: {report['total_files']}")
            print(f"  Migrated: {report['migrated']}")
            print(f"  Skipped: {report['skipped']}")
            print(f"  Failed: {report['failed']}")

            if report["failed"] > 0:
                print("\n⚠ Some files failed to migrate")
                return 1

            print("\n✓ Migration complete")

            # Automatically update index
            if not args.dry_run:
                print("\nUpdating and moving index.json...")
                migrator.update_and_move_index()
                print("✓ Index updated")

        elif args.verify:
            print("Verifying migration integrity...")
            report = migrator.verify_migration()
            print("\nVerification Report:")
            print(f"  Total verified: {report['total_verified']}")
            print(f"  Discrepancies: {report['discrepancies']}")

            if report["discrepancies"] > 0:
                print("\n✗ Verification failed:")
                for error in report["errors"]:
                    print(f"    - {error}")
                return 1

            print("\n✓ Verification successful - all data migrated correctly")

        elif args.cleanup:
            if args.dry_run:
                print("DRY-RUN MODE: Would delete data/weight_cache/ directory")
                return 0

            print("Cleaning up old structure...")
            print("⚠ This will permanently delete data/weight_cache/")
            response = input("Continue? (yes/no): ")

            if response.lower() != "yes":
                print("Cleanup cancelled")
                return 0

            migrator.cleanup_old_structure()
            print("✓ Old structure deleted")

        return 0

    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
