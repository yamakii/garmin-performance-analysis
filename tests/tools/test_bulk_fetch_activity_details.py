"""Tests for bulk_fetch_activity_details module.

This module tests the ActivityDetailsFetcher class that fetches
activity_details.json for multiple activities in bulk.
"""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


@pytest.mark.unit
class TestActivityDetailsFetcher:
    """Unit tests for ActivityDetailsFetcher class."""

    @pytest.fixture
    def temp_raw_dir(self, tmp_path):
        """Create temporary raw data directory with test activities."""
        raw_dir = tmp_path / "raw" / "activity"
        raw_dir.mkdir(parents=True)

        # Activity with activity_details.json (should be skipped)
        activity_1 = raw_dir / "12345"
        activity_1.mkdir()
        (activity_1 / "activity.json").write_text('{"activityId": 12345}')
        (activity_1 / "activity_details.json").write_text('{"activityId": 12345}')

        # Activity without activity_details.json (should be fetched)
        activity_2 = raw_dir / "67890"
        activity_2.mkdir()
        (activity_2 / "activity.json").write_text('{"activityId": 67890}')

        # Invalid directory (no activity.json, should be ignored)
        invalid_dir = raw_dir / "invalid"
        invalid_dir.mkdir()

        return raw_dir

    def test_scan_activities_finds_missing_files(self, temp_raw_dir):
        """Test scan_activities finds activities missing activity_details.json."""
        from tools.scripts.bulk_fetch_activity_details import ActivityDetailsFetcher

        fetcher = ActivityDetailsFetcher(raw_dir=temp_raw_dir.parent)
        missing = fetcher.scan_activities()

        # Should find only activity 67890 (missing activity_details.json)
        assert len(missing) == 1
        assert missing[0][0] == 67890
        assert missing[0][1] == temp_raw_dir / "67890"

    def test_scan_activities_skips_existing_files(self, temp_raw_dir):
        """Test scan_activities skips activities with existing activity_details.json."""
        from tools.scripts.bulk_fetch_activity_details import ActivityDetailsFetcher

        fetcher = ActivityDetailsFetcher(raw_dir=temp_raw_dir.parent)
        missing = fetcher.scan_activities()

        # Should not include activity 12345 (has activity_details.json)
        activity_ids = [activity_id for activity_id, _ in missing]
        assert 12345 not in activity_ids

    def test_scan_activities_skips_invalid_directories(self, temp_raw_dir):
        """Test scan_activities ignores directories without activity.json."""
        from tools.scripts.bulk_fetch_activity_details import ActivityDetailsFetcher

        fetcher = ActivityDetailsFetcher(raw_dir=temp_raw_dir.parent)
        missing = fetcher.scan_activities()

        # Should not include invalid directory
        activity_dirs = [str(activity_dir) for _, activity_dir in missing]
        assert not any("invalid" in path for path in activity_dirs)

    @patch("tools.scripts.bulk_fetch_activity_details.GarminIngestWorker")
    def test_fetch_single_activity_success(self, mock_worker_class, temp_raw_dir):
        """Test fetch_single_activity successfully fetches and saves data."""
        from tools.scripts.bulk_fetch_activity_details import ActivityDetailsFetcher

        # Setup mock
        mock_client = Mock()
        mock_client.get_activity_details.return_value = {
            "activityId": 67890,
            "activityName": "Morning Run",
        }
        mock_worker_class.get_garmin_client.return_value = mock_client

        # Execute
        fetcher = ActivityDetailsFetcher(raw_dir=temp_raw_dir.parent)
        activity_dir = temp_raw_dir / "67890"
        result = fetcher.fetch_single_activity(67890, activity_dir)

        # Verify
        assert result["status"] == "success"
        assert result["activity_id"] == 67890

        # Verify file was created
        details_file = activity_dir / "activity_details.json"
        assert details_file.exists()

        # Verify file content
        with open(details_file, encoding="utf-8") as f:
            saved_data = json.load(f)
        assert saved_data["activityId"] == 67890
        assert saved_data["activityName"] == "Morning Run"

    def test_fetch_single_activity_skip_existing(self, temp_raw_dir):
        """Test fetch_single_activity skips when file exists (force=False)."""
        from tools.scripts.bulk_fetch_activity_details import ActivityDetailsFetcher

        fetcher = ActivityDetailsFetcher(raw_dir=temp_raw_dir.parent, force=False)
        activity_dir = temp_raw_dir / "12345"
        result = fetcher.fetch_single_activity(12345, activity_dir)

        # Should be skipped
        assert result["status"] == "skipped"
        assert result["activity_id"] == 12345

    @patch("tools.scripts.bulk_fetch_activity_details.GarminIngestWorker")
    def test_fetch_single_activity_force_overwrite(
        self, mock_worker_class, temp_raw_dir
    ):
        """Test fetch_single_activity overwrites when force=True."""
        from tools.scripts.bulk_fetch_activity_details import ActivityDetailsFetcher

        # Setup mock
        mock_client = Mock()
        mock_client.get_activity_details.return_value = {
            "activityId": 12345,
            "activityName": "Updated Run",
        }
        mock_worker_class.get_garmin_client.return_value = mock_client

        # Execute with force=True
        fetcher = ActivityDetailsFetcher(raw_dir=temp_raw_dir.parent, force=True)
        activity_dir = temp_raw_dir / "12345"
        result = fetcher.fetch_single_activity(12345, activity_dir)

        # Should be success (not skipped)
        assert result["status"] == "success"
        assert result["activity_id"] == 12345

        # Verify file was overwritten
        details_file = activity_dir / "activity_details.json"
        with open(details_file, encoding="utf-8") as f:
            saved_data = json.load(f)
        assert saved_data["activityName"] == "Updated Run"

    @patch("tools.scripts.bulk_fetch_activity_details.GarminIngestWorker")
    def test_fetch_single_activity_api_error(self, mock_worker_class, temp_raw_dir):
        """Test fetch_single_activity handles API errors gracefully."""
        from tools.scripts.bulk_fetch_activity_details import ActivityDetailsFetcher

        # Setup mock to raise error
        mock_client = Mock()
        mock_client.get_activity_details.side_effect = Exception("API Error")
        mock_worker_class.get_garmin_client.return_value = mock_client

        # Execute
        fetcher = ActivityDetailsFetcher(raw_dir=temp_raw_dir.parent)
        activity_dir = temp_raw_dir / "67890"
        result = fetcher.fetch_single_activity(67890, activity_dir)

        # Should be error
        assert result["status"] == "error"
        assert result["activity_id"] == 67890
        assert "API Error" in result["error"]


@pytest.mark.integration
class TestActivityDetailsFetcherIntegration:
    """Integration tests for ActivityDetailsFetcher."""

    @pytest.fixture
    def temp_raw_dir_multi(self, tmp_path):
        """Create temporary raw data directory with multiple test activities."""
        raw_dir = tmp_path / "raw" / "activity"
        raw_dir.mkdir(parents=True)

        # Create 3 activities without activity_details.json
        for activity_id in [11111, 22222, 33333]:
            activity_dir = raw_dir / str(activity_id)
            activity_dir.mkdir()
            (activity_dir / "activity.json").write_text(
                f'{{"activityId": {activity_id}}}'
            )

        # Create 1 activity with activity_details.json (should be skipped)
        activity_dir = raw_dir / "44444"
        activity_dir.mkdir()
        (activity_dir / "activity.json").write_text('{"activityId": 44444}')
        (activity_dir / "activity_details.json").write_text('{"activityId": 44444}')

        return raw_dir

    @patch("tools.scripts.bulk_fetch_activity_details.GarminIngestWorker")
    @patch("tools.scripts.bulk_fetch_activity_details.tqdm")
    def test_bulk_fetch_with_mock_api(
        self, mock_tqdm, mock_worker_class, temp_raw_dir_multi
    ):
        """Test bulk fetch with mocked API."""
        from tools.scripts.bulk_fetch_activity_details import ActivityDetailsFetcher

        # Setup mock
        mock_client = Mock()

        def mock_get_details(activity_id, maxchart=2000):
            return {"activityId": activity_id, "maxchart": maxchart}

        mock_client.get_activity_details.side_effect = mock_get_details
        mock_worker_class.get_garmin_client.return_value = mock_client

        # Mock tqdm to return iterable
        mock_tqdm.return_value = [
            (11111, temp_raw_dir_multi / "11111"),
            (22222, temp_raw_dir_multi / "22222"),
            (33333, temp_raw_dir_multi / "33333"),
        ]

        # Execute
        fetcher = ActivityDetailsFetcher(
            raw_dir=temp_raw_dir_multi.parent, delay_seconds=0.0
        )
        summary = fetcher.fetch_all()

        # Verify summary
        assert summary["total"] == 3
        assert summary["success"] == 3
        assert summary["skipped"] == 0
        assert summary["error"] == 0
        assert len(summary["errors"]) == 0

        # Verify files were created
        for activity_id in [11111, 22222, 33333]:
            details_file = (
                temp_raw_dir_multi / str(activity_id) / "activity_details.json"
            )
            assert details_file.exists()

    @patch("tools.scripts.bulk_fetch_activity_details.GarminIngestWorker")
    def test_partial_failure_recovery(self, mock_worker_class, temp_raw_dir_multi):
        """Test that bulk fetch continues after partial failures."""
        from tools.scripts.bulk_fetch_activity_details import ActivityDetailsFetcher

        # Setup mock: 22222 will fail, others succeed
        mock_client = Mock()

        def mock_get_details(activity_id, maxchart=2000):
            if activity_id == 22222:
                raise Exception("Network error")
            return {"activityId": activity_id}

        mock_client.get_activity_details.side_effect = mock_get_details
        mock_worker_class.get_garmin_client.return_value = mock_client

        # Execute
        fetcher = ActivityDetailsFetcher(
            raw_dir=temp_raw_dir_multi.parent, delay_seconds=0.0
        )
        summary = fetcher.fetch_all()

        # Verify summary
        assert summary["total"] == 3
        assert summary["success"] == 2  # 11111, 33333
        assert summary["error"] == 1  # 22222
        assert len(summary["errors"]) == 1
        assert summary["errors"][0]["activity_id"] == 22222

        # Verify successful files were created
        assert (temp_raw_dir_multi / "11111" / "activity_details.json").exists()
        assert (temp_raw_dir_multi / "33333" / "activity_details.json").exists()

        # Verify failed file was not created
        assert not (temp_raw_dir_multi / "22222" / "activity_details.json").exists()


@pytest.mark.integration
@pytest.mark.garmin_api
class TestActivityDetailsFetcherRealAPI:
    """Integration tests with real Garmin API.

    Note: These tests are skipped by default (pyproject.toml addopts).
    Run explicitly with: uv run pytest -m garmin_api
    """

    def test_fetch_real_activity(self):
        """Test fetching activity_details for a real cached activity."""
        from tools.scripts.bulk_fetch_activity_details import ActivityDetailsFetcher

        # Use existing cached activity
        activity_id = 20594901208
        raw_dir = Path("data/raw")
        activity_dir = raw_dir / "activity" / str(activity_id)

        # Skip if cache doesn't exist
        if not activity_dir.exists():
            pytest.skip("Test requires cached activity")

        # Backup existing file if present
        details_file = activity_dir / "activity_details.json"
        backup_file = activity_dir / "activity_details.json.backup"
        if details_file.exists():
            details_file.rename(backup_file)

        try:
            # Execute
            fetcher = ActivityDetailsFetcher(raw_dir=raw_dir, force=False)
            result = fetcher.fetch_single_activity(activity_id, activity_dir)

            # Verify
            assert result["status"] == "success"
            assert details_file.exists()

            # Verify content
            with open(details_file, encoding="utf-8") as f:
                data = json.load(f)
            assert data["activityId"] == activity_id
            assert "metricsCount" in data  # Verify it's activity_details format

        finally:
            # Restore backup
            if backup_file.exists():
                if details_file.exists():
                    details_file.unlink()
                backup_file.rename(details_file)


@pytest.mark.unit
class TestCLI:
    """Unit tests for CLI interface."""

    @patch("tools.scripts.bulk_fetch_activity_details.ActivityDetailsFetcher")
    def test_main_dry_run(self, mock_fetcher_class, capsys):
        """Test main function with --dry-run option."""
        import sys

        from tools.scripts.bulk_fetch_activity_details import main

        # Setup mock
        mock_fetcher = Mock()
        mock_fetcher.scan_activities.return_value = [
            (11111, Path("data/raw/activity/11111")),
            (22222, Path("data/raw/activity/22222")),
        ]
        mock_fetcher_class.return_value = mock_fetcher

        # Mock sys.argv
        sys.argv = ["bulk_fetch_activity_details.py", "--dry-run"]

        # Execute
        main()

        # Verify output
        captured = capsys.readouterr()
        assert "Found 2 activities to fetch" in captured.out
        assert "Activity 11111" in captured.out
        assert "Activity 22222" in captured.out

    @patch("tools.scripts.bulk_fetch_activity_details.ActivityDetailsFetcher")
    def test_main_execute(self, mock_fetcher_class, capsys):
        """Test main function execution."""
        import sys

        from tools.scripts.bulk_fetch_activity_details import main

        # Setup mock
        mock_fetcher = Mock()
        mock_fetcher.fetch_all.return_value = {
            "total": 3,
            "success": 2,
            "skipped": 0,
            "error": 1,
            "errors": [{"activity_id": 33333, "error": "API Error"}],
        }
        mock_fetcher_class.return_value = mock_fetcher

        # Mock sys.argv
        sys.argv = ["bulk_fetch_activity_details.py", "--delay", "0.5", "--force"]

        # Execute
        main()

        # Verify fetcher was created with correct arguments
        mock_fetcher_class.assert_called_once_with(delay_seconds=0.5, force=True)

        # Verify output
        captured = capsys.readouterr()
        assert "Total activities: 3" in captured.out
        assert "Success: 2" in captured.out
        assert "Errors: 1" in captured.out
        assert "Activity 33333: API Error" in captured.out
