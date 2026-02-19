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

        # Mock pace zones query for deduplication
        mock_conn = mocker.MagicMock()
        mock_ctx = mocker.MagicMock()
        mock_ctx.__enter__ = mocker.Mock(return_value=mock_conn)
        mock_ctx.__exit__ = mocker.Mock(return_value=False)
        mock_conn.execute.return_value.fetchone.return_value = (
            '{"easy_low":360,"easy_high":300,"marathon":276,"threshold":255,"interval":234,"repetition":221}',
        )
        mock_reader._get_connection.return_value = mock_ctx
        uploader._reader = mock_reader

        result = uploader.upload_plan_workouts("plan-1")
        assert result["skipped"] == 2
        assert result["uploaded"] == 0

    def test_schedule_workout_success(self, mocker):
        """Should schedule workout on Garmin Connect calendar."""
        mock_client = mocker.MagicMock()
        mock_client.garth.post.return_value = None  # Success

        uploader = GarminWorkoutUploader.__new__(GarminWorkoutUploader)
        uploader._db_path = ":memory:"
        uploader._reader = mocker.MagicMock()

        result = uploader._schedule_workout(mock_client, 12345, "2026-03-15")

        assert result is True
        mock_client.garth.post.assert_called_once_with(
            "connectapi",
            "/workout-service/schedule/12345",
            json={"date": "2026-03-15"},
            api=True,
        )

    def test_schedule_workout_failure(self, mocker):
        """Should return False and log warning on schedule failure."""
        mock_client = mocker.MagicMock()
        mock_client.garth.post.side_effect = Exception("API error")

        uploader = GarminWorkoutUploader.__new__(GarminWorkoutUploader)
        uploader._db_path = ":memory:"
        uploader._reader = mocker.MagicMock()

        result = uploader._schedule_workout(mock_client, 12345, "2026-03-15")

        assert result is False

    def test_upload_workout_with_schedule(self, mocker):
        """Upload should schedule workout when schedule=True and date is set."""
        # Setup mock connection
        mock_conn = mocker.MagicMock()
        mock_ctx = mocker.MagicMock()
        mock_ctx.__enter__ = mocker.Mock(return_value=mock_conn)
        mock_ctx.__exit__ = mocker.Mock(return_value=False)

        columns = [
            "workout_id",
            "plan_id",
            "week_number",
            "day_of_week",
            "workout_type",
            "workout_date",
            "description_ja",
            "target_distance_km",
            "target_duration_minutes",
            "target_pace_low",
            "target_pace_high",
            "intervals_json",
            "phase",
            "warmup_minutes",
            "cooldown_minutes",
            "garmin_workout_id",
            "uploaded_at",
            "actual_activity_id",
            "adherence_score",
            "completed_at",
        ]
        workout_row = [
            "w1",
            "plan1",
            1,
            2,
            "easy",
            "2026-03-10",
            "イージーラン 5km",
            5.0,
            None,
            340.0,
            300.0,
            None,
            "base",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        ]
        pace_zones_json = '{"easy_low":340,"easy_high":300,"marathon":270,"threshold":255,"interval":234,"repetition":221}'

        # First execute returns workout row, second returns pace zones
        mock_cursor1 = mocker.MagicMock()
        mock_cursor1.fetchone.return_value = workout_row

        mock_cursor2 = mocker.MagicMock()
        mock_cursor2.fetchone.return_value = (pace_zones_json,)

        mock_conn.execute.side_effect = [mock_cursor1, mock_cursor2]
        # conn.description is read after first execute
        mock_conn.description = [(c,) for c in columns]

        # Mock client
        mock_client = mocker.MagicMock()
        mock_client.upload_workout.return_value = {"workoutId": 99999}
        mock_client.garth.post.return_value = None

        # Mock duckdb for update
        mock_duckdb_conn = mocker.MagicMock()
        mocker.patch("duckdb.connect", return_value=mock_duckdb_conn)

        uploader = GarminWorkoutUploader.__new__(GarminWorkoutUploader)
        uploader._db_path = ":memory:"
        mock_reader: Any = mocker.MagicMock()
        mock_reader._get_connection.return_value = mock_ctx
        uploader._reader = mock_reader

        mocker.patch.object(uploader, "_get_garmin_client", return_value=mock_client)
        mocker.patch.object(
            GarminWorkoutUploader, "_schedule_workout", return_value=True
        )

        result = uploader.upload_workout("w1", schedule=True)

        assert result["success"] is True
        assert result["scheduled"] is True
        assert result["scheduled_date"] == "2026-03-10"

    def test_upload_workout_without_schedule(self, mocker):
        """Upload should NOT schedule when schedule=False."""
        mock_conn = mocker.MagicMock()
        mock_ctx = mocker.MagicMock()
        mock_ctx.__enter__ = mocker.Mock(return_value=mock_conn)
        mock_ctx.__exit__ = mocker.Mock(return_value=False)

        columns = [
            "workout_id",
            "plan_id",
            "week_number",
            "day_of_week",
            "workout_type",
            "workout_date",
            "description_ja",
            "target_distance_km",
            "target_duration_minutes",
            "target_pace_low",
            "target_pace_high",
            "intervals_json",
            "phase",
            "warmup_minutes",
            "cooldown_minutes",
            "garmin_workout_id",
            "uploaded_at",
            "actual_activity_id",
            "adherence_score",
            "completed_at",
        ]
        workout_row = [
            "w1",
            "plan1",
            1,
            2,
            "easy",
            "2026-03-10",
            "イージーラン 5km",
            5.0,
            None,
            340.0,
            300.0,
            None,
            "base",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        ]
        pace_zones_json = '{"easy_low":340,"easy_high":300,"marathon":270,"threshold":255,"interval":234,"repetition":221}'

        mock_cursor1 = mocker.MagicMock()
        mock_cursor1.fetchone.return_value = workout_row

        mock_cursor2 = mocker.MagicMock()
        mock_cursor2.fetchone.return_value = (pace_zones_json,)

        mock_conn.execute.side_effect = [mock_cursor1, mock_cursor2]
        mock_conn.description = [(c,) for c in columns]

        mock_client = mocker.MagicMock()
        mock_client.upload_workout.return_value = {"workoutId": 99999}

        mock_duckdb_conn = mocker.MagicMock()
        mocker.patch("duckdb.connect", return_value=mock_duckdb_conn)

        uploader = GarminWorkoutUploader.__new__(GarminWorkoutUploader)
        uploader._db_path = ":memory:"
        mock_reader: Any = mocker.MagicMock()
        mock_reader._get_connection.return_value = mock_ctx
        uploader._reader = mock_reader

        mocker.patch.object(uploader, "_get_garmin_client", return_value=mock_client)

        result = uploader.upload_workout("w1", schedule=False)

        assert result["success"] is True
        assert result["scheduled"] is False

    def test_delete_workout_success(self, mocker):
        """Should delete workout from Garmin and reset DB fields."""
        mock_conn = mocker.MagicMock()
        mock_ctx = mocker.MagicMock()
        mock_ctx.__enter__ = mocker.Mock(return_value=mock_conn)
        mock_ctx.__exit__ = mocker.Mock(return_value=False)

        # First query: get workout row
        mock_cursor1 = mocker.MagicMock()
        mock_cursor1.fetchone.return_value = ("w1", 99999)

        # Second query: count shared references (0 = last reference)
        mock_cursor2 = mocker.MagicMock()
        mock_cursor2.fetchone.return_value = (0,)

        mock_conn.execute.side_effect = [mock_cursor1, mock_cursor2]

        mock_client = mocker.MagicMock()
        mock_client.connectapi.return_value = None

        mock_duckdb_conn = mocker.MagicMock()
        mocker.patch("duckdb.connect", return_value=mock_duckdb_conn)

        uploader = GarminWorkoutUploader.__new__(GarminWorkoutUploader)
        uploader._db_path = ":memory:"
        mock_reader: Any = mocker.MagicMock()
        mock_reader._get_connection.return_value = mock_ctx
        mock_reader.db_path = ":memory:"
        uploader._reader = mock_reader

        mocker.patch.object(uploader, "_get_garmin_client", return_value=mock_client)

        result = uploader.delete_workout("w1")

        assert result["success"] is True
        assert result["deleted"] is True
        assert result["garmin_workout_id"] == 99999
        mock_client.connectapi.assert_called_once_with(
            "/workout-service/workout/99999", method="DELETE"
        )
        mock_duckdb_conn.execute.assert_called_once()
        mock_duckdb_conn.close.assert_called_once()

    def test_delete_workout_not_uploaded(self, mocker):
        """Should skip deletion when garmin_workout_id is NULL."""
        mock_conn = mocker.MagicMock()
        mock_ctx = mocker.MagicMock()
        mock_ctx.__enter__ = mocker.Mock(return_value=mock_conn)
        mock_ctx.__exit__ = mocker.Mock(return_value=False)

        mock_conn.execute.return_value.fetchone.return_value = ("w1", None)

        uploader = GarminWorkoutUploader.__new__(GarminWorkoutUploader)
        uploader._db_path = ":memory:"
        mock_reader: Any = mocker.MagicMock()
        mock_reader._get_connection.return_value = mock_ctx
        uploader._reader = mock_reader

        result = uploader.delete_workout("w1")

        assert result["skipped"] is True
        assert result["reason"] == "Not uploaded to Garmin"

    def test_delete_plan_workouts(self, mocker):
        """Should delete all uploaded workouts for a plan."""
        uploader = GarminWorkoutUploader.__new__(GarminWorkoutUploader)
        uploader._db_path = ":memory:"
        mock_reader: Any = mocker.MagicMock()
        mock_reader.get_training_plan.return_value = {
            "workouts": [
                {"workout_id": "w1", "garmin_workout_id": 11111},
                {"workout_id": "w2", "garmin_workout_id": None},
                {"workout_id": "w3", "garmin_workout_id": 33333},
            ]
        }
        uploader._reader = mock_reader

        mocker.patch.object(
            uploader,
            "delete_workout",
            side_effect=[
                {
                    "success": True,
                    "workout_id": "w1",
                    "garmin_workout_id": 11111,
                    "deleted": True,
                },
                {
                    "success": True,
                    "workout_id": "w3",
                    "garmin_workout_id": 33333,
                    "deleted": True,
                },
            ],
        )

        result = uploader.delete_plan_workouts("plan-1")

        assert result["deleted"] == 2
        assert result["skipped"] == 1
        assert result["total"] == 3


@pytest.mark.unit
class TestWorkoutFingerprint:
    def test_same_workout_same_fingerprint(self):
        """Identical workout dicts should produce the same fingerprint."""
        workout = {
            "workoutName": "イージーラン 30分",
            "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
            "workoutSegments": [{"segmentOrder": 1}],
        }
        fp1 = GarminWorkoutUploader._workout_fingerprint(workout)
        fp2 = GarminWorkoutUploader._workout_fingerprint(workout)
        assert fp1 == fp2

    def test_different_workout_different_fingerprint(self):
        """Different workout dicts should produce different fingerprints."""
        workout1 = {
            "workoutName": "イージーラン 30分",
            "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
            "workoutSegments": [{"endConditionValue": 1800}],
        }
        workout2 = {
            "workoutName": "ロングラン 60分",
            "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
            "workoutSegments": [{"endConditionValue": 3600}],
        }
        fp1 = GarminWorkoutUploader._workout_fingerprint(workout1)
        fp2 = GarminWorkoutUploader._workout_fingerprint(workout2)
        assert fp1 != fp2


@pytest.mark.unit
class TestUploadPlanDeduplication:
    def test_upload_deduplicates_identical_workouts(self, mocker):
        """Identical workouts should be uploaded once and reused."""
        uploader = GarminWorkoutUploader.__new__(GarminWorkoutUploader)
        uploader._db_path = ":memory:"
        mock_reader: Any = mocker.MagicMock()

        # Two identical easy workouts on different dates
        mock_reader.get_training_plan.return_value = {
            "workouts": [
                {
                    "workout_id": "w1",
                    "plan_id": "plan-1",
                    "week_number": 1,
                    "day_of_week": 2,
                    "workout_type": "easy",
                    "workout_date": "2026-03-10",
                    "description_ja": "イージーラン 30分",
                    "target_distance_km": 5.0,
                    "target_duration_minutes": 30.0,
                    "target_pace_low": None,
                    "target_pace_high": None,
                    "target_hr_low": 111,
                    "target_hr_high": 135,
                    "phase": "base",
                    "garmin_workout_id": None,
                },
                {
                    "workout_id": "w2",
                    "plan_id": "plan-1",
                    "week_number": 2,
                    "day_of_week": 2,
                    "workout_type": "easy",
                    "workout_date": "2026-03-17",
                    "description_ja": "イージーラン 30分",
                    "target_distance_km": 5.0,
                    "target_duration_minutes": 30.0,
                    "target_pace_low": None,
                    "target_pace_high": None,
                    "target_hr_low": 111,
                    "target_hr_high": 135,
                    "phase": "base",
                    "garmin_workout_id": None,
                },
            ]
        }
        uploader._reader = mock_reader

        # Mock pace zones query
        mock_conn = mocker.MagicMock()
        mock_ctx = mocker.MagicMock()
        mock_ctx.__enter__ = mocker.Mock(return_value=mock_conn)
        mock_ctx.__exit__ = mocker.Mock(return_value=False)
        mock_conn.execute.return_value.fetchone.return_value = (
            '{"easy_low":360,"easy_high":300,"marathon":276,"threshold":255,"interval":234,"repetition":221}',
        )
        mock_reader._get_connection.return_value = mock_ctx

        # First upload succeeds
        mocker.patch.object(
            uploader,
            "upload_workout",
            return_value={
                "success": True,
                "workout_id": "w1",
                "garmin_workout_id": 99999,
                "workout_name": "イージーラン 30分",
                "scheduled": True,
                "scheduled_date": "2026-03-10",
            },
        )

        # Mock reuse
        mocker.patch.object(
            uploader,
            "_reuse_workout",
            return_value={
                "success": True,
                "workout_id": "w2",
                "garmin_workout_id": 99999,
                "reused": True,
                "scheduled": True,
                "scheduled_date": "2026-03-17",
            },
        )

        result = uploader.upload_plan_workouts("plan-1")

        assert result["uploaded"] == 1
        assert result["reused"] == 1
        assert result["total"] == 2

        # upload_workout called once (first workout), _reuse_workout once (second)
        uploader.upload_workout.assert_called_once_with("w1", schedule=True)  # type: ignore[attr-defined]
        uploader._reuse_workout.assert_called_once()  # type: ignore[attr-defined]


@pytest.mark.unit
class TestReuseWorkoutDateConversion:
    """Test that _reuse_workout converts datetime.date to str for scheduling."""

    def test_reuse_workout_converts_date_to_str(self, mocker):
        """datetime.date from DuckDB must be converted to str before scheduling."""
        from datetime import date

        uploader = GarminWorkoutUploader.__new__(GarminWorkoutUploader)
        uploader._db_path = ":memory:"

        mock_reader: Any = mocker.MagicMock()
        uploader._reader = mock_reader

        # Mock DuckDB connection for UPDATE
        mock_conn = mocker.MagicMock()
        mocker.patch("duckdb.connect", return_value=mock_conn)

        # Mock Garmin client
        mock_client = mocker.MagicMock()
        mocker.patch.object(uploader, "_get_garmin_client", return_value=mock_client)

        # Mock _schedule_workout to verify the date type
        mock_schedule = mocker.patch.object(
            uploader, "_schedule_workout", return_value=True
        )

        # Pass datetime.date (as DuckDB returns) instead of str
        workout_date = date(2026, 3, 17)
        result = uploader._reuse_workout(
            workout_id="w2",
            garmin_workout_id=99999,
            workout_date=workout_date,  # type: ignore[arg-type]
            schedule=True,
        )

        # _schedule_workout must receive a string, not datetime.date
        mock_schedule.assert_called_once_with(mock_client, 99999, "2026-03-17")
        assert result["scheduled"] is True
        assert result["scheduled_date"] == workout_date


@pytest.mark.unit
class TestDeleteWorkoutSafeSharing:
    def test_delete_shared_workout_only_unlinks(self, mocker):
        """Deleting a workout with shared garmin_workout_id should only unlink."""
        mock_conn = mocker.MagicMock()
        mock_ctx = mocker.MagicMock()
        mock_ctx.__enter__ = mocker.Mock(return_value=mock_conn)
        mock_ctx.__exit__ = mocker.Mock(return_value=False)

        # First query: get workout row
        mock_cursor1 = mocker.MagicMock()
        mock_cursor1.fetchone.return_value = ("w1", 99999)

        # Second query: count other workouts sharing this garmin_workout_id
        mock_cursor2 = mocker.MagicMock()
        mock_cursor2.fetchone.return_value = (2,)  # 2 other workouts share it

        mock_conn.execute.side_effect = [mock_cursor1, mock_cursor2]

        mock_duckdb_conn = mocker.MagicMock()
        mocker.patch("duckdb.connect", return_value=mock_duckdb_conn)

        uploader = GarminWorkoutUploader.__new__(GarminWorkoutUploader)
        uploader._db_path = ":memory:"
        mock_reader: Any = mocker.MagicMock()
        mock_reader._get_connection.return_value = mock_ctx
        mock_reader.db_path = ":memory:"
        uploader._reader = mock_reader

        # Should NOT call _get_garmin_client (no Garmin deletion)
        mock_get_client = mocker.patch.object(uploader, "_get_garmin_client")

        result = uploader.delete_workout("w1")

        assert result["success"] is True
        assert result["unlinked"] is True
        assert result["deleted"] is False
        mock_get_client.assert_not_called()
        # DB update should clear the garmin_workout_id
        mock_duckdb_conn.execute.assert_called_once()

    def test_delete_last_reference_deletes_from_garmin(self, mocker):
        """Deleting the last reference should delete from Garmin."""
        mock_conn = mocker.MagicMock()
        mock_ctx = mocker.MagicMock()
        mock_ctx.__enter__ = mocker.Mock(return_value=mock_conn)
        mock_ctx.__exit__ = mocker.Mock(return_value=False)

        # First query: get workout row
        mock_cursor1 = mocker.MagicMock()
        mock_cursor1.fetchone.return_value = ("w1", 99999)

        # Second query: no other workouts share this ID
        mock_cursor2 = mocker.MagicMock()
        mock_cursor2.fetchone.return_value = (0,)

        mock_conn.execute.side_effect = [mock_cursor1, mock_cursor2]

        mock_client = mocker.MagicMock()
        mock_client.connectapi.return_value = None

        mock_duckdb_conn = mocker.MagicMock()
        mocker.patch("duckdb.connect", return_value=mock_duckdb_conn)

        uploader = GarminWorkoutUploader.__new__(GarminWorkoutUploader)
        uploader._db_path = ":memory:"
        mock_reader: Any = mocker.MagicMock()
        mock_reader._get_connection.return_value = mock_ctx
        mock_reader.db_path = ":memory:"
        uploader._reader = mock_reader

        mocker.patch.object(uploader, "_get_garmin_client", return_value=mock_client)

        result = uploader.delete_workout("w1")

        assert result["success"] is True
        assert result["deleted"] is True
        mock_client.connectapi.assert_called_once_with(
            "/workout-service/workout/99999", method="DELETE"
        )
