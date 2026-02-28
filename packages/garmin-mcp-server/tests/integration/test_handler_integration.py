"""Handler -> Reader -> DuckDB integration tests using verification DB.

Tests the full chain from handler.handle() through reader queries to DuckDB,
ensuring SQL queries return correct data shapes from real schema.

Related: GitHub Issue #102
"""

import json

import pytest

from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.handlers.metadata_handler import MetadataHandler
from garmin_mcp.handlers.performance_handler import PerformanceHandler
from garmin_mcp.handlers.physiology_handler import PhysiologyHandler
from garmin_mcp.handlers.splits_handler import SplitsHandler

FIXTURE_ACTIVITY_ID = 12345678901
FIXTURE_ACTIVITY_DATE = "2025-01-15"


@pytest.mark.integration
class TestHandlerIntegration:
    """Handler -> Reader -> DuckDB integration tests using verification DB."""

    # --- SplitsHandler ---

    @pytest.mark.asyncio
    async def test_splits_handler_comprehensive(self, verification_db_path):
        """get_splits_comprehensive returns 7 splits with all fields."""
        reader = GarminDBReader(db_path=str(verification_db_path))
        handler = SplitsHandler(reader)
        result = await handler.handle(
            "get_splits_comprehensive", {"activity_id": FIXTURE_ACTIVITY_ID}
        )
        data = json.loads(result[0].text)
        assert "splits" in data
        assert len(data["splits"]) == 7
        # Each split should have essential fields
        first_split = data["splits"][0]
        assert "split_number" in first_split
        assert "avg_pace_seconds_per_km" in first_split

    @pytest.mark.asyncio
    async def test_splits_handler_statistics_only(self, verification_db_path):
        """get_splits_comprehensive with statistics_only=True returns aggregated stats."""
        reader = GarminDBReader(db_path=str(verification_db_path))
        handler = SplitsHandler(reader)
        result = await handler.handle(
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

    # --- PerformanceHandler ---

    @pytest.mark.asyncio
    async def test_performance_handler_trends(self, verification_db_path):
        """get_performance_trends returns pace_consistency and phase data."""
        reader = GarminDBReader(db_path=str(verification_db_path))
        handler = PerformanceHandler(reader)
        result = await handler.handle(
            "get_performance_trends", {"activity_id": FIXTURE_ACTIVITY_ID}
        )
        data = json.loads(result[0].text)
        assert "pace_consistency" in data
        assert "hr_drift_percentage" in data
        assert "warmup_phase" in data
        assert "run_phase" in data

    # --- PhysiologyHandler ---

    @pytest.mark.asyncio
    async def test_physiology_handler_hr_zones(self, verification_db_path):
        """get_heart_rate_zones_detail returns 5 zones."""
        reader = GarminDBReader(db_path=str(verification_db_path))
        handler = PhysiologyHandler(reader)
        result = await handler.handle(
            "get_heart_rate_zones_detail", {"activity_id": FIXTURE_ACTIVITY_ID}
        )
        data = json.loads(result[0].text)
        assert "zones" in data
        assert len(data["zones"]) == 5
        # Each zone should have boundary and time fields
        first_zone = data["zones"][0]
        assert "zone_number" in first_zone
        assert "low_boundary" in first_zone
        assert "time_in_zone_seconds" in first_zone

    @pytest.mark.asyncio
    async def test_physiology_handler_hr_efficiency(self, verification_db_path):
        """get_hr_efficiency_analysis returns zone distribution fields."""
        reader = GarminDBReader(db_path=str(verification_db_path))
        handler = PhysiologyHandler(reader)
        result = await handler.handle(
            "get_hr_efficiency_analysis", {"activity_id": FIXTURE_ACTIVITY_ID}
        )
        data = json.loads(result[0].text)
        assert "primary_zone" in data
        assert "training_type" in data
        assert "zone_percentages" in data
        assert "zone1" in data["zone_percentages"]
        assert "zone5" in data["zone_percentages"]

    # --- MetadataHandler ---

    @pytest.mark.asyncio
    async def test_metadata_handler_get_by_date(self, verification_db_path):
        """get_activity_by_date maps date to activity ID."""
        reader = GarminDBReader(db_path=str(verification_db_path))
        handler = MetadataHandler(reader)
        result = await handler.handle(
            "get_activity_by_date", {"date": FIXTURE_ACTIVITY_DATE}
        )
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["activity_id"] == FIXTURE_ACTIVITY_ID

    @pytest.mark.asyncio
    async def test_metadata_handler_get_date_by_id(self, verification_db_path):
        """get_date_by_activity_id maps activity ID to date."""
        reader = GarminDBReader(db_path=str(verification_db_path))
        handler = MetadataHandler(reader)
        result = await handler.handle(
            "get_date_by_activity_id", {"activity_id": FIXTURE_ACTIVITY_ID}
        )
        data = json.loads(result[0].text)
        assert data["activity_id"] == FIXTURE_ACTIVITY_ID
        assert FIXTURE_ACTIVITY_DATE in str(data["date"])
