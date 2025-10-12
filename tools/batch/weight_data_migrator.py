"""Weight data migration tool from old structure to new structure."""

import json
import shutil
from pathlib import Path


class WeightDataMigrator:
    """Migrate weight data from data/weight_cache/ to data/raw/weight/.

    This migrator handles the complete migration of weight data from the old
    directory structure (data/weight_cache/) to the new structure (data/raw/weight/).
    It includes verification and cleanup capabilities.
    """

    def __init__(self, project_root: Path, dry_run: bool = False) -> None:
        """Initialize migrator with project root and dry-run mode.

        Args:
            project_root: Root directory of the project
            dry_run: If True, no actual file operations are performed
        """
        self.project_root = project_root
        self.dry_run = dry_run
        self.old_raw_dir = project_root / "data" / "weight_cache" / "raw"
        self.old_index_file = (
            project_root / "data" / "weight_cache" / "weight_index.json"
        )
        self.new_raw_dir = project_root / "data" / "raw" / "weight"
        self.new_weight_dir = project_root / "data" / "weight"
        self.new_index_file = project_root / "data" / "weight" / "index.json"
        self._verified = False

    def _extract_date_from_filename(self, filename: str) -> str:
        """Extract date from old weight filename format.

        Args:
            filename: Old format filename (weight_YYYY-MM-DD_raw.json)

        Returns:
            Date in YYYY-MM-DD format
        """
        return filename.replace("weight_", "").replace("_raw.json", "")

    def migrate_single_date(self, date: str) -> bool:
        """Migrate a single date's weight data.

        Args:
            date: Date in YYYY-MM-DD format

        Returns:
            True if migration successful or file already exists, False if source missing
        """
        # Old file format: weight_YYYY-MM-DD_raw.json
        old_file = self.old_raw_dir / f"weight_{date}_raw.json"
        if not old_file.exists():
            return False

        # New file format: YYYY-MM-DD.json
        new_file = self.new_raw_dir / f"{date}.json"

        # Skip if already exists
        if new_file.exists():
            return True

        # Create directory and copy file
        if not self.dry_run:
            self.new_raw_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(old_file, new_file)

        return True

    def migrate_all(self) -> dict[str, int | bool]:
        """Migrate all weight data from old to new structure.

        Returns:
            Migration report with statistics:
                - total_files: Total number of files found
                - migrated: Number of files migrated
                - skipped: Number of files skipped (already exist)
                - failed: Number of files that failed to migrate
                - dry_run: Whether this was a dry-run
        """
        report: dict[str, int | bool] = {
            "total_files": 0,
            "migrated": 0,
            "skipped": 0,
            "failed": 0,
            "dry_run": self.dry_run,
        }

        # Find all old weight files
        if not self.old_raw_dir.exists():
            return report

        old_files = list(self.old_raw_dir.glob("weight_*_raw.json"))
        report["total_files"] = len(old_files)

        for old_file in old_files:
            # Extract date from filename
            date = self._extract_date_from_filename(old_file.name)
            new_file = self.new_raw_dir / f"{date}.json"

            if new_file.exists():
                report["skipped"] += 1
                continue

            try:
                if not self.dry_run:
                    self.new_raw_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy(old_file, new_file)
                report["migrated"] += 1
            except Exception:
                report["failed"] += 1

        return report

    def update_and_move_index(self) -> None:
        """Update index.json with new paths and move to new location.

        This method:
        1. Loads the old weight_index.json
        2. Updates all raw_file paths to new structure
        3. Removes parquet_file fields (no longer used)
        4. Writes to new location (data/weight/index.json)
        """
        if not self.old_index_file.exists():
            return

        # Load old index
        old_index = json.loads(self.old_index_file.read_text())

        # Update paths and remove parquet_file field
        new_index = {}
        for date, data in old_index.items():
            updated_data = data.copy()
            # Update raw_file path to new structure
            updated_data["raw_file"] = f"data/raw/weight/{date}.json"
            # Remove parquet_file field (deprecated)
            updated_data.pop("parquet_file", None)
            new_index[date] = updated_data

        # Write to new location
        if not self.dry_run:
            self.new_weight_dir.mkdir(parents=True, exist_ok=True)
            self.new_index_file.write_text(json.dumps(new_index, indent=2))

    def verify_migration(self) -> dict[str, int | list[str]]:
        """Verify migration integrity by comparing old and new files.

        Returns:
            Verification report:
                - total_verified: Total number of files verified
                - discrepancies: Number of files with issues
                - errors: List of error messages
        """
        errors: list[str] = []
        discrepancies = 0

        # Find all old files
        if not self.old_raw_dir.exists():
            return {
                "total_verified": 0,
                "discrepancies": 0,
                "errors": errors,
            }

        old_files = list(self.old_raw_dir.glob("weight_*_raw.json"))
        total_verified = len(old_files)

        for old_file in old_files:
            # Extract date
            date = self._extract_date_from_filename(old_file.name)

            # Check corresponding new file
            new_file = self.new_raw_dir / f"{date}.json"

            if not new_file.exists():
                discrepancies += 1
                errors.append(f"Missing new file for {date}")
                continue

            # Compare data
            try:
                old_data = json.loads(old_file.read_text())
                new_data = json.loads(new_file.read_text())

                if old_data != new_data:
                    discrepancies += 1
                    errors.append(f"Data mismatch for {date}")
            except json.JSONDecodeError as e:
                discrepancies += 1
                errors.append(f"JSON decode error for {date}: {e}")

        # Mark as verified if no discrepancies
        if discrepancies == 0:
            self._verified = True

        return {
            "total_verified": total_verified,
            "discrepancies": discrepancies,
            "errors": errors,
        }

    def cleanup_old_structure(self) -> None:
        """Delete old data/weight_cache/ directory after verification.

        Raises:
            RuntimeError: If verification has not been run successfully
        """
        if not self._verified:
            raise RuntimeError(
                "Cannot cleanup without successful verification. "
                "Run verify_migration() first."
            )

        old_dir = self.project_root / "data" / "weight_cache"
        if old_dir.exists() and not self.dry_run:
            shutil.rmtree(old_dir)
