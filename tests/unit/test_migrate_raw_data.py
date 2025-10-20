"""
Unit tests for raw_data migration script.
"""

import json

import pytest


@pytest.fixture
def temp_dirs(tmp_path):
    """Create temporary source and output directories."""
    source_dir = tmp_path / "source"
    output_dir = tmp_path / "output"
    source_dir.mkdir()
    output_dir.mkdir()
    return {"source": source_dir, "output": output_dir}


@pytest.fixture
def sample_old_format_data():
    """Sample old format raw_data."""
    return {
        "activity": {
            "summaryDTO": {
                "activityId": 20594901208,
                "trainingEffect": 2.4,
                "anaerobicTrainingEffect": 0.0,
                "startTimeLocal": "2025-09-22T06:00:00.0",
            }
        },
        "splits": {"lapDTOs": [{"lapIndex": 1}]},
        "weather": {"temp": 20},
        "gear": [{"gearId": "123"}],
        "hr_zones": [{"zoneNumber": 1}],
        "training_effect": {
            "aerobicTrainingEffect": 2.4,
            "anaerobicTrainingEffect": 0.0,
        },
        "vo2_max": {"vo2MaxValue": 50},
        "lactate_threshold": {"speed_and_heart_rate": {"heartRate": 160}},
        "weight": None,
    }


@pytest.mark.unit
class TestMigrateRawDataStructure:
    """Test cases for migrate_raw_data_structure script."""

    def test_split_raw_data_to_new_structure(self, temp_dirs, sample_old_format_data):
        """Test splitting old format raw_data into new directory structure."""
        from tools.scripts.migrate_raw_data_structure import (
            split_raw_data_to_new_structure,
        )

        activity_id = 20594901208
        source_dir = temp_dirs["source"]
        output_dir = temp_dirs["output"]

        # Create old format file in source
        old_file = source_dir / f"{activity_id}_raw.json"
        with open(old_file, "w", encoding="utf-8") as f:
            json.dump(sample_old_format_data, f)

        # Execute migration
        result = split_raw_data_to_new_structure(
            activity_id=activity_id,
            source_dir=source_dir,
            output_dir=output_dir,
            dry_run=False,
        )

        # Verify result
        assert result["success"] is True
        assert result["activity_id"] == activity_id
        assert "files_created" in result

        # Verify new directory structure in output
        activity_dir = output_dir / "activity" / str(activity_id)
        assert activity_dir.exists()

        # Verify individual files
        expected_files = [
            "activity.json",
            "splits.json",
            "weather.json",
            "gear.json",
            "hr_zones.json",
            "vo2_max.json",
            "lactate_threshold.json",
        ]

        for file_name in expected_files:
            file_path = activity_dir / file_name
            assert file_path.exists(), f"{file_name} should exist"

        # Verify file contents
        with open(activity_dir / "activity.json", encoding="utf-8") as f:
            activity_data = json.load(f)
            assert activity_data["summaryDTO"]["activityId"] == activity_id

        with open(activity_dir / "splits.json", encoding="utf-8") as f:
            splits_data = json.load(f)
            assert "lapDTOs" in splits_data

    def test_split_raw_data_dry_run(self, temp_dirs, sample_old_format_data):
        """Test dry-run mode (should not create files)."""
        from tools.scripts.migrate_raw_data_structure import (
            split_raw_data_to_new_structure,
        )

        activity_id = 20594901208
        source_dir = temp_dirs["source"]
        output_dir = temp_dirs["output"]

        # Create old format file
        old_file = source_dir / f"{activity_id}_raw.json"
        with open(old_file, "w", encoding="utf-8") as f:
            json.dump(sample_old_format_data, f)

        # Execute dry-run
        result = split_raw_data_to_new_structure(
            activity_id=activity_id,
            source_dir=source_dir,
            output_dir=output_dir,
            dry_run=True,
        )

        # Verify dry-run result
        assert result["success"] is True
        assert result["dry_run"] is True

        # Verify no files were created in output
        activity_dir = output_dir / "activity" / str(activity_id)
        assert not activity_dir.exists()

    def test_split_raw_data_missing_optional_fields(self, temp_dirs):
        """Test migration with missing optional fields."""
        from tools.scripts.migrate_raw_data_structure import (
            split_raw_data_to_new_structure,
        )

        activity_id = 20594901208
        source_dir = temp_dirs["source"]
        output_dir = temp_dirs["output"]

        # Create minimal raw_data (missing vo2_max, lactate_threshold)
        minimal_data = {
            "activity": {"summaryDTO": {"activityId": activity_id}},
            "splits": {"lapDTOs": []},
            "weather": {},
            "gear": [],
            "hr_zones": [],
        }

        old_file = source_dir / f"{activity_id}_raw.json"
        with open(old_file, "w", encoding="utf-8") as f:
            json.dump(minimal_data, f)

        # Execute migration
        result = split_raw_data_to_new_structure(
            activity_id=activity_id,
            source_dir=source_dir,
            output_dir=output_dir,
            dry_run=False,
        )

        # Verify result
        assert result["success"] is True

        # Verify optional files are created with default values
        activity_dir = output_dir / "activity" / str(activity_id)

        with open(activity_dir / "vo2_max.json", encoding="utf-8") as f:
            vo2_data = json.load(f)
            # Should be empty dict or null
            assert vo2_data is None or vo2_data == {}

    def test_split_raw_data_already_exists(self, temp_dirs, sample_old_format_data):
        """Test behavior when new structure already exists."""
        from tools.scripts.migrate_raw_data_structure import (
            split_raw_data_to_new_structure,
        )

        activity_id = 20594901208
        source_dir = temp_dirs["source"]
        output_dir = temp_dirs["output"]

        # Create old format file
        old_file = source_dir / f"{activity_id}_raw.json"
        with open(old_file, "w", encoding="utf-8") as f:
            json.dump(sample_old_format_data, f)

        # Create new structure manually in output
        activity_dir = output_dir / "activity" / str(activity_id)
        activity_dir.mkdir(parents=True)

        # Execute migration
        result = split_raw_data_to_new_structure(
            activity_id=activity_id,
            source_dir=source_dir,
            output_dir=output_dir,
            dry_run=False,
            overwrite=False,
        )

        # Should fail gracefully
        assert result["success"] is False
        assert "already exists" in result.get("error", "").lower()

    def test_migrate_all_raw_data_files(self, temp_dirs, sample_old_format_data):
        """Test migrating all old format files in directory."""
        from tools.scripts.migrate_raw_data_structure import migrate_all_raw_data_files

        source_dir = temp_dirs["source"]
        output_dir = temp_dirs["output"]

        # Create multiple old format files in source
        activity_ids = [20594901208, 20615445009, 20700000000]
        for activity_id in activity_ids:
            old_file = source_dir / f"{activity_id}_raw.json"
            data = sample_old_format_data.copy()
            data["activity"]["summaryDTO"]["activityId"] = activity_id
            with open(old_file, "w", encoding="utf-8") as f:
                json.dump(data, f)

        # Execute bulk migration
        results = migrate_all_raw_data_files(
            source_dir=source_dir,
            output_dir=output_dir,
            dry_run=False,
        )

        # Verify all files migrated
        assert len(results) == 3
        assert all(r["success"] for r in results)

        # Verify new directories created in output
        for activity_id in activity_ids:
            activity_dir = output_dir / "activity" / str(activity_id)
            assert activity_dir.exists()
