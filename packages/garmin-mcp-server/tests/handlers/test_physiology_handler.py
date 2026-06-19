"""Tests for the physiology tools (dispatched via the single-source registry)."""

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from garmin_mcp.tools import ALL_DEFS_BY_NAME
from tests.handlers.conftest import dispatch_tool

# ---------------------------------------------------------------------------
# registry membership tests
# ---------------------------------------------------------------------------

EXPECTED_TOOL_NAMES = [
    "get_form_efficiency_summary",
    "get_form_evaluations",
    "get_form_baseline_trend",
    "get_hr_efficiency_analysis",
    "get_heart_rate_zones_detail",
    "get_vo2_max_data",
    "get_lactate_threshold_data",
]


@pytest.mark.unit
class TestToolRegistration:
    """Physiology tools are registered in the single-source registry."""

    @pytest.mark.parametrize("tool_name", EXPECTED_TOOL_NAMES)
    def test_physiology_tool_registered(self, tool_name: str) -> None:
        assert tool_name in ALL_DEFS_BY_NAME

    @pytest.mark.parametrize("tool_name", ["unknown_tool", ""])
    def test_unknown_tool_not_registered(self, tool_name: str) -> None:
        assert tool_name not in ALL_DEFS_BY_NAME


# ---------------------------------------------------------------------------
# Simple method tests (6 methods, all same db_reader delegation pattern)
# ---------------------------------------------------------------------------

SIMPLE_METHODS = [
    ("get_form_efficiency_summary", "get_form_efficiency_summary"),
    ("get_form_evaluations", "get_form_evaluations"),
    ("get_hr_efficiency_analysis", "get_hr_efficiency_analysis"),
    ("get_heart_rate_zones_detail", "get_heart_rate_zones_detail"),
    ("get_vo2_max_data", "get_vo2_max_data"),
    ("get_lactate_threshold_data", "get_lactate_threshold_data"),
]

SAMPLE_DATA = {
    "get_form_efficiency_summary": {
        "activity_id": 12345,
        "gct_mean": 245.3,
        "vo_mean": 8.2,
        "vr_mean": 7.1,
    },
    "get_form_evaluations": {
        "activity_id": 12345,
        "evaluations": [
            {"metric": "GCT", "score": 4, "stars": "****"},
        ],
    },
    "get_hr_efficiency_analysis": {
        "activity_id": 12345,
        "training_type": "base_run",
        "zone_distribution": {"zone1": 10, "zone2": 50, "zone3": 30},
    },
    "get_heart_rate_zones_detail": {
        "activity_id": 12345,
        "zones": [
            {"zone": 1, "low": 100, "high": 130, "time_seconds": 120},
        ],
    },
    "get_vo2_max_data": {
        "activity_id": 12345,
        "vo2_max": 52.3,
        "fitness_age": 28,
        "category": "Excellent",
    },
    "get_lactate_threshold_data": {
        "activity_id": 12345,
        "lt_heart_rate": 168,
        "lt_speed": 3.8,
        "lt_power": 320,
    },
}


@pytest.mark.unit
class TestSimpleMethods:
    """Test the 6 simple delegation methods that call db_reader and return JSON."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tool_name,reader_method", SIMPLE_METHODS)
    async def test_returns_data(
        self,
        mock_db_reader: MagicMock,
        tool_name: str,
        reader_method: str,
    ) -> None:
        expected = SAMPLE_DATA[tool_name]
        getattr(mock_db_reader, reader_method).return_value = expected

        result = dispatch_tool(mock_db_reader, tool_name, {"activity_id": 12345})

        assert len(result) == 1
        parsed = json.loads(result[0].text)
        assert parsed == expected
        getattr(mock_db_reader, reader_method).assert_called_once_with(12345)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tool_name,reader_method", SIMPLE_METHODS)
    async def test_returns_none(
        self,
        mock_db_reader: MagicMock,
        tool_name: str,
        reader_method: str,
    ) -> None:
        getattr(mock_db_reader, reader_method).return_value = None

        result = dispatch_tool(mock_db_reader, tool_name, {"activity_id": 99999})

        assert len(result) == 1
        parsed = json.loads(result[0].text)
        assert parsed is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tool_name,reader_method", SIMPLE_METHODS)
    async def test_returns_empty_dict(
        self,
        mock_db_reader: MagicMock,
        tool_name: str,
        reader_method: str,
    ) -> None:
        getattr(mock_db_reader, reader_method).return_value = {}

        result = dispatch_tool(mock_db_reader, tool_name, {"activity_id": 12345})

        assert len(result) == 1
        parsed = json.loads(result[0].text)
        assert parsed == {}


@pytest.mark.unit
class TestUnknownTool:
    """An unregistered tool name is not dispatchable via the registry."""

    def test_unknown_tool_not_in_registry(self, mock_db_reader: MagicMock) -> None:
        with pytest.raises(KeyError):
            dispatch_tool(mock_db_reader, "nonexistent_tool", {"activity_id": 1})


# ---------------------------------------------------------------------------
# get_form_baseline_trend — handler now delegates to PhysiologyReader
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFormBaselineTrendDelegation:
    """Handler is a thin delegator to PhysiologyReader.get_form_baseline_trend.

    The baseline trend logic was extracted to the reader in Issue #235;
    these tests verify the handler forwards arguments and serializes the
    reader's result without modification.
    """

    BASE_ARGS = {"activity_id": 12345, "activity_date": "2025-10-15"}

    def _reader_with_physiology(self, return_value: Any) -> MagicMock:
        reader = MagicMock()
        reader.physiology.get_form_baseline_trend.return_value = return_value
        return reader

    @pytest.mark.asyncio
    async def test_delegates_and_serializes(self) -> None:
        expected = {
            "success": True,
            "activity_id": 12345,
            "activity_date": "2025-10-15",
            "metrics": {"GCT": {"current": {"coef_d": -0.15}}},
        }
        reader = self._reader_with_physiology(expected)

        result = dispatch_tool(reader, "get_form_baseline_trend", self.BASE_ARGS)

        assert json.loads(result[0].text) == expected
        reader.physiology.get_form_baseline_trend.assert_called_once_with(
            12345, "2025-10-15", user_id="default", condition_group="flat_road"
        )

    @pytest.mark.asyncio
    async def test_custom_user_id_and_condition_group(self) -> None:
        reader = self._reader_with_physiology({"success": True, "metrics": {}})

        args = {
            **self.BASE_ARGS,
            "user_id": "runner1",
            "condition_group": "hilly",
        }
        dispatch_tool(reader, "get_form_baseline_trend", args)

        reader.physiology.get_form_baseline_trend.assert_called_once_with(
            12345, "2025-10-15", user_id="runner1", condition_group="hilly"
        )

    @pytest.mark.asyncio
    async def test_error_result_passed_through(self) -> None:
        error = {"success": False, "error": "No baseline found for 2025-10-15"}
        reader = self._reader_with_physiology(error)

        result = dispatch_tool(reader, "get_form_baseline_trend", self.BASE_ARGS)

        assert json.loads(result[0].text) == error
