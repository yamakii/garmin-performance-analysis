"""Tests for GarminWorkoutUploader."""

from typing import Any

import pytest

from garmin_mcp.training_plan.garmin_uploader import GarminWorkoutUploader


@pytest.mark.unit
class TestGarminWorkoutUploader:
    def test_upload_workout_not_found(self, mocker):
        """Should return error when workout not found."""
        mock_conn = mocker.MagicMock()
        mock_ctx = mocker.MagicMock()
        mock_ctx.__enter__ = mocker.Mock(return_value=mock_conn)
        mock_ctx.__exit__ = mocker.Mock(return_value=False)

        mock_conn.execute.return_value.fetchone.return_value = None

        uploader = GarminWorkoutUploader.__new__(GarminWorkoutUploader)
        uploader._db_path = ":memory:"
        mock_reader: Any = mocker.MagicMock()
        mock_reader._get_connection.return_value = mock_ctx
        uploader._reader = mock_reader

        result = uploader.upload_workout("nonexistent")
        assert "error" in result

    def test_upload_plan_workouts_not_found(self, mocker):
        """Should return error when plan not found."""
        uploader = GarminWorkoutUploader.__new__(GarminWorkoutUploader)
        uploader._db_path = ":memory:"
        mock_reader: Any = mocker.MagicMock()
        mock_reader.get_training_plan.return_value = {"error": "Plan not found"}
        uploader._reader = mock_reader

        result = uploader.upload_plan_workouts("nonexistent")
        assert "error" in result

    def test_upload_skips_already_uploaded(self, mocker):
        """Should skip workouts that already have garmin_workout_id."""
        uploader = GarminWorkoutUploader.__new__(GarminWorkoutUploader)
        uploader._db_path = ":memory:"
        mock_reader: Any = mocker.MagicMock()
        mock_reader.get_training_plan.return_value = {
            "workouts": [
                {"workout_id": "w1", "garmin_workout_id": 12345},
                {"workout_id": "w2", "garmin_workout_id": 67890},
            ]
        }
        uploader._reader = mock_reader

        result = uploader.upload_plan_workouts("plan-1")
        assert result["skipped"] == 2
        assert result["uploaded"] == 0
