"""Tests for TrainingPlanHandler."""

import json
from unittest.mock import MagicMock

import pytest

from garmin_mcp.handlers.training_plan_handler import TrainingPlanHandler


class TestHandles:
    """Test handles() method for tool name matching."""

    def test_handles_get_current_fitness_summary(
        self, mock_db_reader: MagicMock
    ) -> None:
        handler = TrainingPlanHandler(mock_db_reader)
        assert handler.handles("get_current_fitness_summary") is True

    def test_handles_generate_training_plan(self, mock_db_reader: MagicMock) -> None:
        handler = TrainingPlanHandler(mock_db_reader)
        assert handler.handles("generate_training_plan") is True

    def test_handles_get_training_plan(self, mock_db_reader: MagicMock) -> None:
        handler = TrainingPlanHandler(mock_db_reader)
        assert handler.handles("get_training_plan") is True

    def test_handles_upload_workout_to_garmin(self, mock_db_reader: MagicMock) -> None:
        handler = TrainingPlanHandler(mock_db_reader)
        assert handler.handles("upload_workout_to_garmin") is True

    def test_handles_delete_workout_from_garmin(
        self, mock_db_reader: MagicMock
    ) -> None:
        handler = TrainingPlanHandler(mock_db_reader)
        assert handler.handles("delete_workout_from_garmin") is True

    def test_does_not_handle_unknown_tool(self, mock_db_reader: MagicMock) -> None:
        handler = TrainingPlanHandler(mock_db_reader)
        assert handler.handles("get_splits_pace_hr") is False

    def test_does_not_handle_empty_string(self, mock_db_reader: MagicMock) -> None:
        handler = TrainingPlanHandler(mock_db_reader)
        assert handler.handles("") is False


class TestGetCurrentFitnessSummary:
    """Test get_current_fitness_summary via handle()."""

    @pytest.mark.asyncio
    async def test_with_default_lookback(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_db_reader.db_path = "/tmp/test.duckdb"
        expected = {"vdot": 45.2, "weekly_volume_km": 30.0}
        mock_assessor_cls = mocker.patch(
            "garmin_mcp.training_plan.fitness_assessor.FitnessAssessor"
        )
        mock_assessor = mock_assessor_cls.return_value
        mock_assessor.assess.return_value.model_dump.return_value = expected
        handler = TrainingPlanHandler(mock_db_reader)

        result = await handler.handle("get_current_fitness_summary", {})

        data = json.loads(result[0].text)
        assert data["vdot"] == 45.2
        assert data["weekly_volume_km"] == 30.0
        mock_assessor_cls.assert_called_once_with(db_path="/tmp/test.duckdb")
        mock_assessor.assess.assert_called_once_with(lookback_weeks=8)

    @pytest.mark.asyncio
    async def test_with_custom_lookback(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_db_reader.db_path = "/tmp/test.duckdb"
        mock_assessor_cls = mocker.patch(
            "garmin_mcp.training_plan.fitness_assessor.FitnessAssessor"
        )
        mock_assessor_cls.return_value.assess.return_value.model_dump.return_value = {}
        handler = TrainingPlanHandler(mock_db_reader)

        await handler.handle("get_current_fitness_summary", {"lookback_weeks": 12})

        mock_assessor_cls.return_value.assess.assert_called_once_with(lookback_weeks=12)

    @pytest.mark.asyncio
    async def test_error_returns_error_dict(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_db_reader.db_path = "/tmp/test.duckdb"
        mock_assessor_cls = mocker.patch(
            "garmin_mcp.training_plan.fitness_assessor.FitnessAssessor"
        )
        mock_assessor_cls.return_value.assess.side_effect = RuntimeError("DB error")
        handler = TrainingPlanHandler(mock_db_reader)

        result = await handler.handle("get_current_fitness_summary", {})

        data = json.loads(result[0].text)
        assert "error" in data
        assert "DB error" in data["error"]


class TestGenerateTrainingPlan:
    """Test generate_training_plan via handle()."""

    @pytest.mark.asyncio
    async def test_with_required_args(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_db_reader.db_path = "/tmp/test.duckdb"
        mock_gen_cls = mocker.patch(
            "garmin_mcp.training_plan.plan_generator.TrainingPlanGenerator"
        )
        mock_plan = mock_gen_cls.return_value.generate.return_value
        mock_plan.to_summary.return_value = {
            "plan_id": "plan_001",
            "goal_type": "race_10k",
        }
        mock_workout = MagicMock()
        mock_workout.model_dump.return_value = {"day": 1, "type": "easy"}
        mock_plan.get_week_workouts.return_value = [mock_workout]
        handler = TrainingPlanHandler(mock_db_reader)

        result = await handler.handle(
            "generate_training_plan",
            {"goal_type": "race_10k", "total_weeks": 12},
        )

        data = json.loads(result[0].text)
        assert data["plan_id"] == "plan_001"
        assert data["goal_type"] == "race_10k"
        assert len(data["first_week_workouts"]) == 1
        mock_gen_cls.assert_called_once_with(db_path="/tmp/test.duckdb")
        mock_gen_cls.return_value.generate.assert_called_once_with(
            goal_type="race_10k",
            total_weeks=12,
            target_race_date=None,
            target_time_seconds=None,
            runs_per_week=4,
            start_frequency=None,
            preferred_long_run_day=7,
            rest_days=None,
        )

    @pytest.mark.asyncio
    async def test_with_all_optional_args(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_db_reader.db_path = "/tmp/test.duckdb"
        mock_gen_cls = mocker.patch(
            "garmin_mcp.training_plan.plan_generator.TrainingPlanGenerator"
        )
        mock_plan = mock_gen_cls.return_value.generate.return_value
        mock_plan.to_summary.return_value = {"plan_id": "plan_002"}
        mock_plan.get_week_workouts.return_value = []
        handler = TrainingPlanHandler(mock_db_reader)

        await handler.handle(
            "generate_training_plan",
            {
                "goal_type": "race_half",
                "total_weeks": 16,
                "target_race_date": "2025-06-01",
                "target_time_seconds": 5400,
                "runs_per_week": 5,
                "start_frequency": 3,
                "preferred_long_run_day": 6,
                "rest_days": [1, 5],
            },
        )

        mock_gen_cls.return_value.generate.assert_called_once_with(
            goal_type="race_half",
            total_weeks=16,
            target_race_date="2025-06-01",
            target_time_seconds=5400,
            runs_per_week=5,
            start_frequency=3,
            preferred_long_run_day=6,
            rest_days=[1, 5],
        )

    @pytest.mark.asyncio
    async def test_error_returns_error_dict(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_db_reader.db_path = "/tmp/test.duckdb"
        mock_gen_cls = mocker.patch(
            "garmin_mcp.training_plan.plan_generator.TrainingPlanGenerator"
        )
        mock_gen_cls.return_value.generate.side_effect = ValueError("Invalid goal")
        handler = TrainingPlanHandler(mock_db_reader)

        result = await handler.handle(
            "generate_training_plan",
            {"goal_type": "invalid", "total_weeks": 4},
        )

        data = json.loads(result[0].text)
        assert "error" in data
        assert "Invalid goal" in data["error"]


class TestGetTrainingPlan:
    """Test get_training_plan via handle()."""

    @pytest.mark.asyncio
    async def test_with_plan_id_only(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_db_reader.db_path = "/tmp/test.duckdb"
        mock_reader_cls = mocker.patch(
            "garmin_mcp.database.readers.training_plans.TrainingPlanReader"
        )
        expected = {"plan_id": "plan_001", "weeks": []}
        mock_reader_cls.return_value.get_training_plan.return_value = expected
        handler = TrainingPlanHandler(mock_db_reader)

        result = await handler.handle("get_training_plan", {"plan_id": "plan_001"})

        data = json.loads(result[0].text)
        assert data["plan_id"] == "plan_001"
        mock_reader_cls.return_value.get_training_plan.assert_called_once_with(
            plan_id="plan_001",
            version=None,
            week_number=None,
            summary_only=False,
        )

    @pytest.mark.asyncio
    async def test_with_week_number_and_summary(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_db_reader.db_path = "/tmp/test.duckdb"
        mock_reader_cls = mocker.patch(
            "garmin_mcp.database.readers.training_plans.TrainingPlanReader"
        )
        mock_reader_cls.return_value.get_training_plan.return_value = {"summary": True}
        handler = TrainingPlanHandler(mock_db_reader)

        await handler.handle(
            "get_training_plan",
            {"plan_id": "plan_001", "week_number": 3, "summary_only": True},
        )

        mock_reader_cls.return_value.get_training_plan.assert_called_once_with(
            plan_id="plan_001",
            version=None,
            week_number=3,
            summary_only=True,
        )

    @pytest.mark.asyncio
    async def test_error_returns_error_dict(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_db_reader.db_path = "/tmp/test.duckdb"
        mock_reader_cls = mocker.patch(
            "garmin_mcp.database.readers.training_plans.TrainingPlanReader"
        )
        mock_reader_cls.return_value.get_training_plan.side_effect = FileNotFoundError(
            "Plan not found"
        )
        handler = TrainingPlanHandler(mock_db_reader)

        result = await handler.handle("get_training_plan", {"plan_id": "nonexistent"})

        data = json.loads(result[0].text)
        assert "error" in data
        assert "Plan not found" in data["error"]


class TestUploadWorkoutToGarmin:
    """Test upload_workout_to_garmin via handle()."""

    @pytest.mark.asyncio
    async def test_upload_single_workout(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_db_reader.db_path = "/tmp/test.duckdb"
        mock_uploader_cls = mocker.patch(
            "garmin_mcp.training_plan.garmin_uploader.GarminWorkoutUploader"
        )
        mock_uploader_cls.return_value.upload_workout.return_value = {
            "status": "uploaded",
            "garmin_id": 999,
        }
        handler = TrainingPlanHandler(mock_db_reader)

        result = await handler.handle(
            "upload_workout_to_garmin",
            {"workout_id": "w_001", "schedule": True},
        )

        data = json.loads(result[0].text)
        assert data["status"] == "uploaded"
        assert data["garmin_id"] == 999
        mock_uploader_cls.return_value.upload_workout.assert_called_once_with(
            "w_001", schedule=True
        )

    @pytest.mark.asyncio
    async def test_upload_plan_workouts(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_db_reader.db_path = "/tmp/test.duckdb"
        mock_uploader_cls = mocker.patch(
            "garmin_mcp.training_plan.garmin_uploader.GarminWorkoutUploader"
        )
        mock_uploader_cls.return_value.upload_plan_workouts.return_value = {
            "uploaded": 3
        }
        handler = TrainingPlanHandler(mock_db_reader)

        result = await handler.handle(
            "upload_workout_to_garmin",
            {"plan_id": "plan_001", "week_number": 2, "schedule": False},
        )

        data = json.loads(result[0].text)
        assert data["uploaded"] == 3
        mock_uploader_cls.return_value.upload_plan_workouts.assert_called_once_with(
            "plan_001", week_number=2, schedule=False
        )

    @pytest.mark.asyncio
    async def test_upload_plan_without_week(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_db_reader.db_path = "/tmp/test.duckdb"
        mock_uploader_cls = mocker.patch(
            "garmin_mcp.training_plan.garmin_uploader.GarminWorkoutUploader"
        )
        mock_uploader_cls.return_value.upload_plan_workouts.return_value = {
            "uploaded": 10
        }
        handler = TrainingPlanHandler(mock_db_reader)

        result = await handler.handle(
            "upload_workout_to_garmin",
            {"plan_id": "plan_001"},
        )

        data = json.loads(result[0].text)
        assert data["uploaded"] == 10
        mock_uploader_cls.return_value.upload_plan_workouts.assert_called_once_with(
            "plan_001", week_number=None, schedule=True
        )

    @pytest.mark.asyncio
    async def test_upload_neither_workout_nor_plan(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_db_reader.db_path = "/tmp/test.duckdb"
        mocker.patch("garmin_mcp.training_plan.garmin_uploader.GarminWorkoutUploader")
        handler = TrainingPlanHandler(mock_db_reader)

        result = await handler.handle("upload_workout_to_garmin", {})

        data = json.loads(result[0].text)
        assert "error" in data
        assert "Either workout_id or plan_id is required" in data["error"]

    @pytest.mark.asyncio
    async def test_upload_exception(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_db_reader.db_path = "/tmp/test.duckdb"
        mock_uploader_cls = mocker.patch(
            "garmin_mcp.training_plan.garmin_uploader.GarminWorkoutUploader"
        )
        mock_uploader_cls.return_value.upload_workout.side_effect = ConnectionError(
            "API timeout"
        )
        handler = TrainingPlanHandler(mock_db_reader)

        result = await handler.handle(
            "upload_workout_to_garmin", {"workout_id": "w_001"}
        )

        data = json.loads(result[0].text)
        assert "error" in data
        assert "API timeout" in data["error"]


class TestDeleteWorkoutFromGarmin:
    """Test delete_workout_from_garmin via handle()."""

    @pytest.mark.asyncio
    async def test_delete_single_workout(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_db_reader.db_path = "/tmp/test.duckdb"
        mock_uploader_cls = mocker.patch(
            "garmin_mcp.training_plan.garmin_uploader.GarminWorkoutUploader"
        )
        mock_uploader_cls.return_value.delete_workout.return_value = {
            "status": "deleted"
        }
        handler = TrainingPlanHandler(mock_db_reader)

        result = await handler.handle(
            "delete_workout_from_garmin", {"workout_id": "w_001"}
        )

        data = json.loads(result[0].text)
        assert data["status"] == "deleted"
        mock_uploader_cls.return_value.delete_workout.assert_called_once_with("w_001")

    @pytest.mark.asyncio
    async def test_delete_plan_workouts_with_week(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_db_reader.db_path = "/tmp/test.duckdb"
        mock_uploader_cls = mocker.patch(
            "garmin_mcp.training_plan.garmin_uploader.GarminWorkoutUploader"
        )
        mock_uploader_cls.return_value.delete_plan_workouts.return_value = {
            "deleted": 3
        }
        handler = TrainingPlanHandler(mock_db_reader)

        result = await handler.handle(
            "delete_workout_from_garmin",
            {"plan_id": "plan_001", "week_number": 2},
        )

        data = json.loads(result[0].text)
        assert data["deleted"] == 3
        mock_uploader_cls.return_value.delete_plan_workouts.assert_called_once_with(
            "plan_001", week_number=2
        )

    @pytest.mark.asyncio
    async def test_delete_plan_workouts_without_week(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_db_reader.db_path = "/tmp/test.duckdb"
        mock_uploader_cls = mocker.patch(
            "garmin_mcp.training_plan.garmin_uploader.GarminWorkoutUploader"
        )
        mock_uploader_cls.return_value.delete_plan_workouts.return_value = {
            "deleted": 10
        }
        handler = TrainingPlanHandler(mock_db_reader)

        result = await handler.handle(
            "delete_workout_from_garmin", {"plan_id": "plan_001"}
        )

        data = json.loads(result[0].text)
        assert data["deleted"] == 10
        mock_uploader_cls.return_value.delete_plan_workouts.assert_called_once_with(
            "plan_001", week_number=None
        )

    @pytest.mark.asyncio
    async def test_delete_neither_workout_nor_plan(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_db_reader.db_path = "/tmp/test.duckdb"
        mocker.patch("garmin_mcp.training_plan.garmin_uploader.GarminWorkoutUploader")
        handler = TrainingPlanHandler(mock_db_reader)

        result = await handler.handle("delete_workout_from_garmin", {})

        data = json.loads(result[0].text)
        assert "error" in data
        assert "Either workout_id or plan_id is required" in data["error"]

    @pytest.mark.asyncio
    async def test_delete_exception(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_db_reader.db_path = "/tmp/test.duckdb"
        mock_uploader_cls = mocker.patch(
            "garmin_mcp.training_plan.garmin_uploader.GarminWorkoutUploader"
        )
        mock_uploader_cls.return_value.delete_workout.side_effect = ConnectionError(
            "API error"
        )
        handler = TrainingPlanHandler(mock_db_reader)

        result = await handler.handle(
            "delete_workout_from_garmin", {"workout_id": "w_001"}
        )

        data = json.loads(result[0].text)
        assert "error" in data
        assert "API error" in data["error"]


class TestHandleUnknownTool:
    """Test that unknown tool names raise ValueError."""

    @pytest.mark.asyncio
    async def test_raises_value_error(self, mock_db_reader: MagicMock) -> None:
        handler = TrainingPlanHandler(mock_db_reader)
        with pytest.raises(ValueError, match="Unknown tool"):
            await handler.handle("nonexistent_tool", {})
