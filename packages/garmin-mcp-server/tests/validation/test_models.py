"""Unit tests for Pydantic validation models."""

import pytest
from pydantic import ValidationError

from garmin_mcp.validation.models import ActivityRecord, SplitRecord
from garmin_mcp.validation.validators import (
    validate_activity,
    validate_split,
    validate_splits,
)


@pytest.mark.unit
class TestActivityRecord:
    """Tests for ActivityRecord validation."""

    def test_valid(self, valid_activity_data: dict) -> None:
        record = validate_activity(valid_activity_data)
        assert record.activity_id == 12345
        assert record.total_distance_km == 10.5

    def test_negative_distance(self, valid_activity_data: dict) -> None:
        valid_activity_data["total_distance_km"] = -1.0
        with pytest.raises(ValidationError, match="total_distance_km"):
            validate_activity(valid_activity_data)

    def test_hr_out_of_range_high(self, valid_activity_data: dict) -> None:
        valid_activity_data["avg_heart_rate"] = 300
        with pytest.raises(ValidationError, match="avg_heart_rate"):
            validate_activity(valid_activity_data)

    def test_hr_out_of_range_low(self, valid_activity_data: dict) -> None:
        valid_activity_data["avg_heart_rate"] = 10
        with pytest.raises(ValidationError, match="avg_heart_rate"):
            validate_activity(valid_activity_data)

    def test_optional_nulls(self) -> None:
        record = ActivityRecord(
            activity_id=99999,
            activity_date="2025-01-01",
        )
        assert record.activity_name is None
        assert record.avg_heart_rate is None
        assert record.total_distance_km is None

    def test_pace_out_of_range(self, valid_activity_data: dict) -> None:
        valid_activity_data["avg_pace_seconds_per_km"] = 1500
        with pytest.raises(ValidationError, match="avg_pace_seconds_per_km"):
            validate_activity(valid_activity_data)

    def test_negative_time(self, valid_activity_data: dict) -> None:
        valid_activity_data["total_time_seconds"] = -100
        with pytest.raises(ValidationError, match="total_time_seconds"):
            validate_activity(valid_activity_data)

    def test_humidity_over_100(self, valid_activity_data: dict) -> None:
        valid_activity_data["relative_humidity_percent"] = 110.0
        with pytest.raises(ValidationError, match="relative_humidity_percent"):
            validate_activity(valid_activity_data)


@pytest.mark.unit
class TestSplitRecord:
    """Tests for SplitRecord validation."""

    def test_valid(self, valid_split_data: dict) -> None:
        record = validate_split(valid_split_data)
        assert record.activity_id == 12345
        assert record.split_index == 0

    def test_negative_duration(self, valid_split_data: dict) -> None:
        valid_split_data["duration_seconds"] = -10.0
        with pytest.raises(ValidationError, match="duration_seconds"):
            validate_split(valid_split_data)

    def test_pace_out_of_range(self, valid_split_data: dict) -> None:
        valid_split_data["pace_seconds_per_km"] = 1500.0
        with pytest.raises(ValidationError, match="pace_seconds_per_km"):
            validate_split(valid_split_data)

    def test_gct_out_of_range(self, valid_split_data: dict) -> None:
        valid_split_data["ground_contact_time"] = 600.0
        with pytest.raises(ValidationError, match="ground_contact_time"):
            validate_split(valid_split_data)

    def test_vo_out_of_range(self, valid_split_data: dict) -> None:
        valid_split_data["vertical_oscillation"] = 50.0
        with pytest.raises(ValidationError, match="vertical_oscillation"):
            validate_split(valid_split_data)

    def test_vr_out_of_range(self, valid_split_data: dict) -> None:
        valid_split_data["vertical_ratio"] = 35.0
        with pytest.raises(ValidationError, match="vertical_ratio"):
            validate_split(valid_split_data)

    def test_cadence_out_of_range_low(self, valid_split_data: dict) -> None:
        valid_split_data["cadence"] = 50.0
        with pytest.raises(ValidationError, match="cadence"):
            validate_split(valid_split_data)

    def test_optional_nulls(self) -> None:
        record = SplitRecord(activity_id=99999, split_index=0)
        assert record.heart_rate is None
        assert record.cadence is None
        assert record.ground_contact_time is None

    def test_negative_split_index(self, valid_split_data: dict) -> None:
        valid_split_data["split_index"] = -1
        with pytest.raises(ValidationError, match="split_index"):
            validate_split(valid_split_data)


@pytest.mark.unit
class TestValidateSplits:
    """Tests for validate_splits batch function."""

    def test_batch_valid(self) -> None:
        splits: list[dict] = [
            {"split_index": 0, "distance": 1.0, "heart_rate": 140},
            {"split_index": 1, "distance": 1.0, "heart_rate": 150},
        ]
        records = validate_splits(12345, splits)
        assert len(records) == 2
        assert all(r.activity_id == 12345 for r in records)

    def test_batch_fails_on_invalid(self) -> None:
        splits: list[dict] = [
            {"split_index": 0, "distance": 1.0},
            {"split_index": 1, "heart_rate": 999},  # invalid
        ]
        with pytest.raises(ValidationError, match="heart_rate"):
            validate_splits(12345, splits)
