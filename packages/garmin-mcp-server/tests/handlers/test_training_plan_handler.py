"""Tests for TrainingPlanHandler."""

import json
from unittest.mock import MagicMock

import pytest

from garmin_mcp.handlers.training_plan_handler import TrainingPlanHandler

# --- Fixtures ---


def _make_plan_dict(
    *,
    goal_type: str = "fitness",
    total_weeks: int = 4,
    weekly_volumes: list[float] | None = None,
    workouts: list[dict] | None = None,
    start_date: str = "2026-03-02",
    plan_id: str = "test0001",
) -> dict:
    """Build a minimal valid TrainingPlan dict for testing."""
    if weekly_volumes is None:
        weekly_volumes = [20.0, 21.0, 22.0, 18.0]
    if workouts is None:
        workouts = [
            {
                "workout_id": "w001",
                "plan_id": plan_id,
                "week_number": 1,
                "day_of_week": 2,
                "workout_date": "2026-03-03",
                "workout_type": "easy",
                "phase": "base",
            },
        ]
    return {
        "plan_id": plan_id,
        "version": 1,
        "goal_type": goal_type,
        "vdot": 42.0,
        "pace_zones": {
            "easy_low": 370.0,
            "easy_high": 340.0,
            "marathon": 310.0,
            "threshold": 285.0,
            "interval": 260.0,
            "repetition": 245.0,
        },
        "total_weeks": total_weeks,
        "start_date": start_date,
        "weekly_volume_start_km": weekly_volumes[0],
        "weekly_volume_peak_km": max(weekly_volumes),
        "runs_per_week": 3,
        "phases": [["base", total_weeks]],
        "weekly_volumes": weekly_volumes,
        "workouts": workouts,
    }


# --- TestHandles ---


class TestHandles:
    """Test handles() method for tool name matching."""

    def test_handles_get_current_fitness_summary(
        self, mock_db_reader: MagicMock
    ) -> None:
        handler = TrainingPlanHandler(mock_db_reader)
        assert handler.handles("get_current_fitness_summary") is True

    def test_handles_save_training_plan(self, mock_db_reader: MagicMock) -> None:
        handler = TrainingPlanHandler(mock_db_reader)
        assert handler.handles("save_training_plan") is True

    def test_does_not_handle_generate_training_plan(
        self, mock_db_reader: MagicMock
    ) -> None:
        handler = TrainingPlanHandler(mock_db_reader)
        assert handler.handles("generate_training_plan") is False

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


# --- TestGetCurrentFitnessSummary ---


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


# --- TestSaveTrainingPlan ---


class TestSaveTrainingPlan:
    """Test save_training_plan via handle()."""

    @pytest.mark.asyncio
    async def test_save_valid_plan(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_db_reader.db_path = "/tmp/test.duckdb"
        mock_insert = mocker.patch(
            "garmin_mcp.database.inserters.training_plans.insert_training_plan"
        )
        handler = TrainingPlanHandler(mock_db_reader)
        plan_dict = _make_plan_dict()

        result = await handler.handle("save_training_plan", {"plan": plan_dict})

        data = json.loads(result[0].text)
        assert data["status"] == "saved"
        assert data["plan_id"] == "test0001"
        assert data["version"] == 1
        assert data["workout_count"] == 1
        mock_insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_plan_with_pydantic_validation_error(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_db_reader.db_path = "/tmp/test.duckdb"
        mocker.patch(
            "garmin_mcp.database.inserters.training_plans.insert_training_plan"
        )
        handler = TrainingPlanHandler(mock_db_reader)

        # Missing required fields
        result = await handler.handle(
            "save_training_plan", {"plan": {"goal_type": "fitness"}}
        )

        data = json.loads(result[0].text)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_save_plan_with_insert_error(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        mock_db_reader.db_path = "/tmp/test.duckdb"
        mocker.patch(
            "garmin_mcp.database.inserters.training_plans.insert_training_plan",
            side_effect=RuntimeError("DB write error"),
        )
        handler = TrainingPlanHandler(mock_db_reader)
        plan_dict = _make_plan_dict()

        result = await handler.handle("save_training_plan", {"plan": plan_dict})

        data = json.loads(result[0].text)
        assert "error" in data
        assert "DB write error" in data["error"]


# --- TestValidatePlanSafety ---


class TestValidatePlanSafety:
    """Test _validate_plan_safety safety checks."""

    def test_safe_plan_returns_no_errors(self) -> None:
        from garmin_mcp.training_plan.models import TrainingPlan

        plan = TrainingPlan.model_validate(
            _make_plan_dict(weekly_volumes=[20.0, 21.0, 22.0, 18.0])
        )
        errors = TrainingPlanHandler._validate_plan_safety(plan)
        assert errors == []

    def test_volume_increase_over_15_percent(self) -> None:
        from garmin_mcp.training_plan.models import TrainingPlan

        plan = TrainingPlan.model_validate(
            _make_plan_dict(weekly_volumes=[20.0, 24.0, 28.0, 22.0])
        )
        errors = TrainingPlanHandler._validate_plan_safety(plan)
        assert len(errors) >= 1
        assert "volume increase" in errors[0]
        assert "15%" in errors[0]

    def test_return_to_run_with_tempo_rejected(self) -> None:
        from garmin_mcp.training_plan.models import TrainingPlan

        plan = TrainingPlan.model_validate(
            _make_plan_dict(
                goal_type="return_to_run",
                workouts=[
                    {
                        "workout_id": "w001",
                        "plan_id": "test0001",
                        "week_number": 1,
                        "day_of_week": 2,
                        "workout_date": "2026-03-03",
                        "workout_type": "tempo",
                        "phase": "base",
                    },
                ],
            )
        )
        errors = TrainingPlanHandler._validate_plan_safety(plan)
        assert len(errors) >= 1
        assert "prohibited workout type" in errors[0]
        assert "'tempo'" in errors[0]

    def test_return_to_run_with_interval_rejected(self) -> None:
        from garmin_mcp.training_plan.models import TrainingPlan

        plan = TrainingPlan.model_validate(
            _make_plan_dict(
                goal_type="return_to_run",
                workouts=[
                    {
                        "workout_id": "w001",
                        "plan_id": "test0001",
                        "week_number": 1,
                        "day_of_week": 2,
                        "workout_date": "2026-03-03",
                        "workout_type": "interval",
                        "phase": "base",
                    },
                ],
            )
        )
        errors = TrainingPlanHandler._validate_plan_safety(plan)
        assert len(errors) >= 1
        assert "prohibited workout type" in errors[0]

    def test_return_to_run_with_easy_only_passes(self) -> None:
        from garmin_mcp.training_plan.models import TrainingPlan

        plan = TrainingPlan.model_validate(
            _make_plan_dict(
                goal_type="return_to_run",
                workouts=[
                    {
                        "workout_id": "w001",
                        "plan_id": "test0001",
                        "week_number": 1,
                        "day_of_week": 2,
                        "workout_date": "2026-03-03",
                        "workout_type": "easy",
                        "phase": "recovery",
                    },
                    {
                        "workout_id": "w002",
                        "plan_id": "test0001",
                        "week_number": 1,
                        "day_of_week": 7,
                        "workout_date": "2026-03-08",
                        "workout_type": "long_run",
                        "phase": "recovery",
                    },
                ],
            )
        )
        errors = TrainingPlanHandler._validate_plan_safety(plan)
        assert errors == []

    def test_workout_date_outside_week_range(self) -> None:
        from garmin_mcp.training_plan.models import TrainingPlan

        plan = TrainingPlan.model_validate(
            _make_plan_dict(
                start_date="2026-03-02",
                workouts=[
                    {
                        "workout_id": "w001",
                        "plan_id": "test0001",
                        "week_number": 1,
                        "day_of_week": 2,
                        # Date is in week 2 range, not week 1
                        "workout_date": "2026-03-12",
                        "workout_type": "easy",
                        "phase": "base",
                    },
                ],
            )
        )
        errors = TrainingPlanHandler._validate_plan_safety(plan)
        assert len(errors) >= 1
        assert "outside week 1 range" in errors[0]

    def test_workout_without_date_skips_date_check(self) -> None:
        from garmin_mcp.training_plan.models import TrainingPlan

        plan = TrainingPlan.model_validate(
            _make_plan_dict(
                workouts=[
                    {
                        "workout_id": "w001",
                        "plan_id": "test0001",
                        "week_number": 1,
                        "day_of_week": 2,
                        "workout_type": "easy",
                        "phase": "base",
                    },
                ],
            )
        )
        errors = TrainingPlanHandler._validate_plan_safety(plan)
        assert errors == []

    def test_volume_decrease_is_allowed(self) -> None:
        """Recovery weeks with volume decrease should not trigger errors."""
        from garmin_mcp.training_plan.models import TrainingPlan

        plan = TrainingPlan.model_validate(
            _make_plan_dict(weekly_volumes=[25.0, 27.0, 28.0, 20.0])
        )
        errors = TrainingPlanHandler._validate_plan_safety(plan)
        assert errors == []

    @pytest.mark.asyncio
    async def test_safety_violation_returns_error_response(
        self, mock_db_reader: MagicMock, mocker: MagicMock
    ) -> None:
        """Safety violations should return error response without calling insert."""
        mock_db_reader.db_path = "/tmp/test.duckdb"
        mock_insert = mocker.patch(
            "garmin_mcp.database.inserters.training_plans.insert_training_plan"
        )
        handler = TrainingPlanHandler(mock_db_reader)
        plan_dict = _make_plan_dict(
            goal_type="return_to_run",
            workouts=[
                {
                    "workout_id": "w001",
                    "plan_id": "test0001",
                    "week_number": 1,
                    "day_of_week": 2,
                    "workout_date": "2026-03-03",
                    "workout_type": "interval",
                    "phase": "base",
                },
            ],
        )

        result = await handler.handle("save_training_plan", {"plan": plan_dict})

        data = json.loads(result[0].text)
        assert data["error"] == "Safety validation failed"
        assert len(data["details"]) >= 1
        # insert should NOT be called when safety check fails
        mock_insert.assert_not_called()


# --- TestGetTrainingPlan ---


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


# --- TestUploadWorkoutToGarmin ---


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


# --- TestDeleteWorkoutFromGarmin ---


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


# --- TestHandleUnknownTool ---


class TestHandleUnknownTool:
    """Test that unknown tool names raise ValueError."""

    @pytest.mark.asyncio
    async def test_raises_value_error(self, mock_db_reader: MagicMock) -> None:
        handler = TrainingPlanHandler(mock_db_reader)
        with pytest.raises(ValueError, match="Unknown tool"):
            await handler.handle("nonexistent_tool", {})
