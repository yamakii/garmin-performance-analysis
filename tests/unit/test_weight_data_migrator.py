"""Unit tests for WeightDataMigrator."""

import json
import shutil

import pytest

from tools.weight_data_migrator import WeightDataMigrator


@pytest.fixture
def temp_project_root(tmp_path):
    """Create temporary project structure for testing."""
    # Old structure
    old_raw_dir = tmp_path / "data" / "weight_cache" / "raw"
    old_raw_dir.mkdir(parents=True)

    # Create sample old weight files
    sample_data = {
        "startDate": "2025-05-15",
        "endDate": "2025-05-15",
        "dateWeightList": [
            {
                "samplePk": 1758435532139,
                "date": 1758467906000,
                "calendarDate": "2025-05-15",
                "weight": 76199.0,
                "bmi": 27.3,
                "bodyFat": 24.6,
                "bodyWater": 55.1,
                "boneMass": 4199,
                "muscleMass": 30799,
                "sourceType": "INDEX_SCALE",
            }
        ],
        "totalAverage": {
            "from": 1758412800000,
            "until": 1758499199999,
            "weight": 76599.33,
            "bmi": 27.43,
            "bodyFat": 24.9,
        },
    }

    (old_raw_dir / "weight_2025-05-15_raw.json").write_text(json.dumps(sample_data))
    (old_raw_dir / "weight_2025-05-16_raw.json").write_text(json.dumps(sample_data))

    # Create old index.json
    old_index_data = {
        "2025-05-15": {
            "date": "2025-05-15",
            "weight": 70.5,
            "bmi": 25.3,
            "raw_file": "data/weight_cache/raw/weight_2025-05-15_raw.json",
            "parquet_file": "data/weight_cache/weight_2025-05-15.parquet",
            "cached_at": "2025-09-29T17:53:20.486801",
            "source": "INDEX_SCALE",
        },
        "2025-05-16": {
            "date": "2025-05-16",
            "weight": 70.5,
            "bmi": 25.3,
            "raw_file": "data/weight_cache/raw/weight_2025-05-16_raw.json",
            "parquet_file": "data/weight_cache/weight_2025-05-16.parquet",
            "cached_at": "2025-09-29T17:53:20.486801",
            "source": "INDEX_SCALE",
        },
    }

    old_index_file = tmp_path / "data" / "weight_cache" / "weight_index.json"
    old_index_file.write_text(json.dumps(old_index_data))

    return tmp_path


@pytest.mark.unit
def test_migrate_single_date_success(temp_project_root):
    """Test successful migration of a single date's weight data."""
    migrator = WeightDataMigrator(temp_project_root)

    result = migrator.migrate_single_date("2025-05-15")

    assert result is True

    # Verify new file exists
    new_file = temp_project_root / "data" / "raw" / "weight" / "2025-05-15.json"
    assert new_file.exists()

    # Verify data integrity
    old_file = (
        temp_project_root
        / "data"
        / "weight_cache"
        / "raw"
        / "weight_2025-05-15_raw.json"
    )
    old_data = json.loads(old_file.read_text())
    new_data = json.loads(new_file.read_text())
    assert old_data == new_data


@pytest.mark.unit
def test_migrate_single_date_creates_directory(temp_project_root):
    """Test that migrate_single_date creates target directory if not exists."""
    migrator = WeightDataMigrator(temp_project_root)

    # Ensure directory doesn't exist
    new_dir = temp_project_root / "data" / "raw" / "weight"
    assert not new_dir.exists()

    migrator.migrate_single_date("2025-05-15")

    # Verify directory was created
    assert new_dir.exists()
    assert new_dir.is_dir()


@pytest.mark.unit
def test_migrate_single_date_skip_existing(temp_project_root):
    """Test that migrate_single_date skips if target file already exists."""
    migrator = WeightDataMigrator(temp_project_root)

    # Create target file first
    new_dir = temp_project_root / "data" / "raw" / "weight"
    new_dir.mkdir(parents=True)
    new_file = new_dir / "2025-05-15.json"
    new_file.write_text(json.dumps({"existing": "data"}))

    result = migrator.migrate_single_date("2025-05-15")

    # Should skip and return True
    assert result is True

    # Verify file was not overwritten
    data = json.loads(new_file.read_text())
    assert data == {"existing": "data"}


@pytest.mark.unit
def test_migrate_all_dry_run(temp_project_root):
    """Test dry-run mode does not actually copy files."""
    migrator = WeightDataMigrator(temp_project_root, dry_run=True)

    report = migrator.migrate_all()

    # Verify no files were created
    new_dir = temp_project_root / "data" / "raw" / "weight"
    assert not new_dir.exists() or len(list(new_dir.glob("*.json"))) == 0

    # Verify report shows what would be migrated
    assert "total_files" in report
    assert report["total_files"] == 2
    assert report["dry_run"] is True


@pytest.mark.unit
def test_migrate_all_actual(temp_project_root):
    """Test actual migration of all files."""
    migrator = WeightDataMigrator(temp_project_root)

    report = migrator.migrate_all()

    # Verify all files were migrated
    assert report["migrated"] == 2
    assert report["skipped"] == 0
    assert report["failed"] == 0

    # Verify new files exist
    new_dir = temp_project_root / "data" / "raw" / "weight"
    assert (new_dir / "2025-05-15.json").exists()
    assert (new_dir / "2025-05-16.json").exists()


@pytest.mark.unit
def test_update_and_move_index(temp_project_root):
    """Test that index.json is updated and moved to new location."""
    migrator = WeightDataMigrator(temp_project_root)

    # First migrate all files
    migrator.migrate_all()

    # Then update and move index
    migrator.update_and_move_index()

    # Verify new index exists
    new_index = temp_project_root / "data" / "weight" / "index.json"
    assert new_index.exists()

    # Verify content is updated
    index_data = json.loads(new_index.read_text())
    assert "2025-05-15" in index_data
    assert "2025-05-16" in index_data

    # Verify paths are updated to new structure
    assert index_data["2025-05-15"]["raw_file"] == "data/raw/weight/2025-05-15.json"
    assert index_data["2025-05-16"]["raw_file"] == "data/raw/weight/2025-05-16.json"

    # Verify parquet_file field is removed
    assert "parquet_file" not in index_data["2025-05-15"]
    assert "parquet_file" not in index_data["2025-05-16"]


@pytest.mark.unit
def test_verify_migration_no_discrepancies(temp_project_root):
    """Test verification passes when migration is complete."""
    migrator = WeightDataMigrator(temp_project_root)

    # Perform migration
    migrator.migrate_all()

    # Run verification
    report = migrator.verify_migration()

    # Should have no discrepancies
    assert report["total_verified"] == 2
    assert report["discrepancies"] == 0
    errors = report["errors"]
    assert isinstance(errors, list)
    assert len(errors) == 0


@pytest.mark.unit
def test_verify_migration_with_discrepancies(temp_project_root):
    """Test verification detects discrepancies."""
    migrator = WeightDataMigrator(temp_project_root)

    # Partially migrate (only one file)
    new_dir = temp_project_root / "data" / "raw" / "weight"
    new_dir.mkdir(parents=True)

    old_file = (
        temp_project_root
        / "data"
        / "weight_cache"
        / "raw"
        / "weight_2025-05-15_raw.json"
    )
    new_file = new_dir / "2025-05-15.json"
    shutil.copy(old_file, new_file)

    # Run verification
    report = migrator.verify_migration()

    # Should detect missing file
    assert report["total_verified"] == 2
    discrepancies = report["discrepancies"]
    assert isinstance(discrepancies, int)
    assert discrepancies > 0


@pytest.mark.unit
def test_cleanup_old_structure(temp_project_root):
    """Test cleanup removes old weight_cache directory."""
    migrator = WeightDataMigrator(temp_project_root)

    # Perform full migration and verification
    migrator.migrate_all()
    migrator.update_and_move_index()
    migrator.verify_migration()  # Required before cleanup

    # Cleanup
    migrator.cleanup_old_structure()

    # Verify old directory is deleted
    old_dir = temp_project_root / "data" / "weight_cache"
    assert not old_dir.exists()


@pytest.mark.unit
def test_cleanup_requires_verification(temp_project_root):
    """Test cleanup fails if verification is not complete."""
    migrator = WeightDataMigrator(temp_project_root)

    # Do NOT perform migration, try cleanup directly
    with pytest.raises(RuntimeError, match="verification"):
        migrator.cleanup_old_structure()
