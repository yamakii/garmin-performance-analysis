"""Dispatch -> Reader -> DuckDB integration tests using the verification DB.

Tests the full chain from the registry ``dispatch`` through reader queries to
DuckDB, ensuring SQL queries return correct data shapes from the real schema.
The per-domain handler classes were removed in #340; these tests now exercise
the production dispatch path directly via ``dispatch``.

Related: GitHub Issue #102
"""

import json

import pytest
from mcp.types import TextContent

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.handlers.base import format_json_response
from garmin_mcp.tools import ALL_DEFS_BY_NAME
from garmin_mcp.tools.registry import dispatch

FIXTURE_ACTIVITY_ID = 12345678901
FIXTURE_ACTIVITY_DATE = "2025-01-15"


def _dispatch(reader: GarminDBReader, name: str, arguments: dict) -> list[TextContent]:
    """Dispatch a registry tool and wrap it like ``server._dispatch_tool``."""
    result = dispatch(ALL_DEFS_BY_NAME, reader, name, arguments)
    return [TextContent(type="text", text=format_json_response(result, default=str))]


@pytest.mark.integration
class TestHandlerIntegration:
    """Dispatch -> Reader -> DuckDB integration tests using the verification DB."""

    # --- splits ---

    def test_splits_handler_comprehensive(self, verification_db_path):
        """get_splits_comprehensive returns 7 splits with all fields."""
        reader = GarminDBReader(db_path=str(verification_db_path))
        result = _dispatch(
            reader, "get_splits_comprehensive", {"activity_id": FIXTURE_ACTIVITY_ID}
        )
        data = json.loads(result[0].text)
        assert "splits" in data
        assert len(data["splits"]) == 7
        # Each split should have essential fields
        first_split = data["splits"][0]
        assert "split_number" in first_split
        assert "avg_pace_seconds_per_km" in first_split

    def test_splits_handler_statistics_only(self, verification_db_path):
        """get_splits_comprehensive with statistics_only=True returns aggregated stats."""
        reader = GarminDBReader(db_path=str(verification_db_path))
        result = _dispatch(
            reader,
            "get_splits_comprehensive",
            {"activity_id": FIXTURE_ACTIVITY_ID, "statistics_only": True},
        )
        data = json.loads(result[0].text)
        # statistics_only mode should NOT have a "splits" list
        assert "splits" not in data
        # Should have activity_id, statistics_only flag, and metrics dict
        assert data["activity_id"] == FIXTURE_ACTIVITY_ID
        assert data["statistics_only"] is True
        assert "metrics" in data

    # --- performance ---

    def test_performance_handler_trends(self, verification_db_path):
        """get_performance_trends returns pace_consistency and phase data."""
        reader = GarminDBReader(db_path=str(verification_db_path))
        result = _dispatch(
            reader, "get_performance_trends", {"activity_id": FIXTURE_ACTIVITY_ID}
        )
        data = json.loads(result[0].text)
        assert "pace_consistency" in data
        assert "hr_drift_percentage" in data
        assert "warmup_phase" in data
        assert "run_phase" in data

    # --- physiology ---

    def test_physiology_handler_hr_zones(self, verification_db_path):
        """get_heart_rate_zones_detail returns 5 zones."""
        reader = GarminDBReader(db_path=str(verification_db_path))
        result = _dispatch(
            reader, "get_heart_rate_zones_detail", {"activity_id": FIXTURE_ACTIVITY_ID}
        )
        data = json.loads(result[0].text)
        assert "zones" in data
        assert len(data["zones"]) == 5
        # Each zone should have boundary and time fields
        first_zone = data["zones"][0]
        assert "zone_number" in first_zone
        assert "low_boundary" in first_zone
        assert "time_in_zone_seconds" in first_zone

    def test_physiology_handler_hr_efficiency(self, verification_db_path):
        """get_hr_efficiency_analysis returns zone distribution fields."""
        reader = GarminDBReader(db_path=str(verification_db_path))
        result = _dispatch(
            reader, "get_hr_efficiency_analysis", {"activity_id": FIXTURE_ACTIVITY_ID}
        )
        data = json.loads(result[0].text)
        assert "primary_zone" in data
        assert "training_type" in data
        assert "zone_percentages" in data
        assert "zone1" in data["zone_percentages"]
        assert "zone5" in data["zone_percentages"]

    # --- metadata ---

    def test_metadata_handler_get_by_date(self, verification_db_path):
        """get_activity_by_date maps date to activity ID."""
        reader = GarminDBReader(db_path=str(verification_db_path))
        result = _dispatch(
            reader, "get_activity_by_date", {"date": FIXTURE_ACTIVITY_DATE}
        )
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["activity_id"] == FIXTURE_ACTIVITY_ID

    def test_metadata_handler_get_date_by_id(self, verification_db_path):
        """get_date_by_activity_id maps activity ID to date."""
        reader = GarminDBReader(db_path=str(verification_db_path))
        result = _dispatch(
            reader, "get_date_by_activity_id", {"activity_id": FIXTURE_ACTIVITY_ID}
        )
        data = json.loads(result[0].text)
        assert data["activity_id"] == FIXTURE_ACTIVITY_ID
        assert FIXTURE_ACTIVITY_DATE in str(data["date"])
