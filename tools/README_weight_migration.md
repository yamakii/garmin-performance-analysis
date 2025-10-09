# Weight Data Migration Tool

## Overview

This tool migrates weight data from the old structure to the new unified structure:

- **Old**: `data/weight_cache/raw/weight_YYYY-MM-DD_raw.json`
- **New**: `data/raw/weight/YYYY-MM-DD.json`

The migration unifies all raw data under `data/raw/` for consistency with activity data storage.

## Features

- ✅ Migrate all weight files to new flat structure
- ✅ Update and move `weight_index.json` with new paths
- ✅ Data integrity verification (JSON comparison)
- ✅ Dry-run mode for safe testing
- ✅ Single-date or bulk migration
- ✅ Safe cleanup after verification

## Installation

No additional dependencies required. Uses Python standard library.

## Usage

### Full Migration (Recommended)

```bash
# 1. Dry-run test
uv run python tools/migrate_weight_data.py --all --dry-run

# 2. Execute migration
uv run python tools/migrate_weight_data.py --all

# 3. Verify data integrity
uv run python tools/migrate_weight_data.py --verify

# 4. Cleanup old structure (after verification)
uv run python tools/migrate_weight_data.py --cleanup
```

### Single Date Migration

```bash
# Migrate specific date
uv run python tools/migrate_weight_data.py --date 2025-10-03

# Verify specific date
uv run python tools/migrate_weight_data.py --date 2025-10-03 --verify
```

### Options

| Option | Description |
|--------|-------------|
| `--all` | Migrate all weight data files |
| `--date YYYY-MM-DD` | Migrate specific date only |
| `--dry-run` | Test migration without actual changes |
| `--verify` | Verify migration integrity |
| `--cleanup` | Delete old structure (requires verification first) |

## Migration Process

### Step 1: File Migration
- Copies `data/weight_cache/raw/weight_{date}_raw.json` → `data/raw/weight/{date}.json`
- Creates `data/raw/weight/` directory if needed
- Preserves original JSON structure

### Step 2: Index Update
- Moves `data/weight_cache/weight_index.json` → `data/weight/index.json`
- Updates all `raw_file` paths to new structure
- Removes deprecated `parquet_file` field

### Step 3: Verification
- Compares JSON content between old and new files
- Reports any discrepancies (should be 0)
- Safe to run multiple times

### Step 4: Cleanup
- Deletes `data/weight_cache/` directory
- Only runs after successful verification
- Irreversible operation

## Example Output

```
$ uv run python tools/migrate_weight_data.py --all

Migrating all weight data files...

Migration Report:
  Total files: 111
  Migrated: 111
  Skipped: 0
  Failed: 0

✓ Migration complete

Updating and moving index.json...
✓ Index updated
```

## Code Integration

After migration, update code references:

### GarminIngestWorker
```python
# Old
self.weight_cache_dir = project_root / "data" / "weight_cache" / "raw"
weight_file = self.weight_cache_dir / f"weight_{date}_raw.json"

# New
self.weight_raw_dir = project_root / "data" / "raw" / "weight"
weight_file = self.weight_raw_dir / f"{date}.json"
```

### BodyCompositionInserter
```python
# Old
raw_file = "data/weight_cache/raw/weight_2025-10-03_raw.json"

# New
raw_file = "data/raw/weight/2025-10-03.json"
```

## Testing

Run migration tests:

```bash
# Unit tests
uv run pytest tests/unit/test_weight_data_migrator.py -v

# Integration tests with new structure
uv run pytest tests/unit/test_garmin_worker_weight_migration.py -v
uv run pytest tests/ingest/test_body_composition.py -v

# All weight-related tests
uv run pytest tests/ -k "weight or body_composition" -v
```

## Rollback

If needed, rollback via Git:

```bash
# Restore old structure from git history
git checkout HEAD~1 -- data/weight_cache/

# Revert code changes
git revert <commit-hash>
```

## Architecture

### WeightDataMigrator Class

```python
from pathlib import Path
from tools.weight_data_migrator import WeightDataMigrator

# Initialize
migrator = WeightDataMigrator(
    project_root=Path("/path/to/project"),
    dry_run=False
)

# Migrate all
report = migrator.migrate_all()

# Verify
verification = migrator.verify_migration()

# Cleanup (after verification)
if verification["discrepancies"] == 0:
    migrator.cleanup_old_structure()
```

### File Paths

```python
class WeightDataMigrator:
    # Old structure
    old_raw_dir = project_root / "data" / "weight_cache" / "raw"
    old_index_file = project_root / "data" / "weight_cache" / "weight_index.json"

    # New structure
    new_raw_dir = project_root / "data" / "raw" / "weight"
    new_index_file = project_root / "data" / "weight" / "index.json"
```

## Migration History

- **2025-10-09**: Initial migration completed
  - Phase 1: Tool implementation (commit `4508844`)
  - Phase 2: Data migration execution (commit `f2de466`)
  - Phase 3: Code updates (commit `906c22d`)
  - Total files migrated: 111
  - Zero discrepancies

## Troubleshooting

### "Cannot cleanup without successful verification"
Run `--verify` first to confirm data integrity before cleanup.

### "File already exists at destination"
This is normal if re-running migration. Files are skipped, not overwritten.

### "JSON structure mismatch"
Indicates potential data corruption. Do NOT run cleanup until resolved.

## Related Documentation

- Project planning: `docs/project/2025-10-09_weight_data_migration/planning.md`
- Main documentation: `CLAUDE.md` (Data Files Naming Convention section)
- Test documentation: `tests/unit/test_weight_data_migrator.py`

## Support

For issues or questions:
1. Check `docs/project/2025-10-09_weight_data_migration/planning.md`
2. Review test cases in `tests/unit/test_weight_data_migrator.py`
3. Run verification: `uv run python tools/migrate_weight_data.py --verify`
