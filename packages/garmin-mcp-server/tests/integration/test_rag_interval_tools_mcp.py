"""Shim-layer tests for RAG interval/anomaly tools.

After the shim/worker split, the shim no longer dispatches these tools
in-process: it forwards ``(name, arguments)`` verbatim to the worker via
``worker.rpc("call", name, args)``. The underlying tool logic (IntervalAnalyzer,
FormAnomalyDetector, trends, insights, comparisons) is covered by the registry
dispatch tests (``tests/test_all_tools_registry.py``) and the per-query unit
tests. These tests assert the *shim contract*: list_tools surfaces the tools and
call_tool forwards args + serializes the worker's response.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

import garmin_mcp.server as server
from garmin_mcp.server import call_tool, list_tools


@pytest.fixture
def fixture_activity_id() -> int:
    """Fixture activity ID for testing."""
    return 12345678901


def _worker_schema(*names: str) -> AsyncMock:
    """Build a mock worker whose schema rpc advertises the given tool names."""
    worker = AsyncMock()
    worker.rpc.return_value = {
        "ok": True,
        "data": [
            {
                "name": n,
                "description": f"{n} desc",
                "inputSchema": {
                    "type": "object",
                    "properties": {"activity_id": {"type": "integer"}},
                    "required": ["activity_id"],
                },
            }
            for n in names
        ],
    }
    return worker


@pytest.mark.integration
class TestRagIntervalToolsShim:
    """The shim surfaces RAG tools and forwards calls to the worker."""

    @pytest.mark.asyncio
    async def test_list_tools_surfaces_worker_tools(self) -> None:
        """list_tools includes the worker-advertised RAG tools + server tools."""
        worker = _worker_schema(
            "get_interval_analysis",
            "get_split_time_series_detail",
            "detect_form_anomalies_summary",
            "get_form_anomaly_details",
            "analyze_performance_trends",
            "extract_insights",
            "compare_similar_workouts",
        )
        with patch.object(server, "worker", worker):
            tools = await list_tools()

        names = {t.name for t in tools}
        for expected in (
            "get_interval_analysis",
            "get_split_time_series_detail",
            "detect_form_anomalies_summary",
            "get_form_anomaly_details",
            "analyze_performance_trends",
            "extract_insights",
            "compare_similar_workouts",
        ):
            assert expected in names
        # Server tools always appended.
        assert "get_server_info" in names
        assert "reload_server" in names

    @pytest.mark.asyncio
    async def test_call_forwards_args_to_worker(self, fixture_activity_id: int) -> None:
        """call_tool forwards (name, args) verbatim to worker.rpc('call', ...)."""
        worker = AsyncMock()
        worker.rpc.return_value = {
            "ok": True,
            "data": {
                "activity_id": fixture_activity_id,
                "segments": [],
                "work_recovery_comparison": {},
                "fatigue_indicators": {},
            },
        }
        with patch.object(server, "worker", worker):
            result = await call_tool(
                name="get_interval_analysis",
                arguments={"activity_id": fixture_activity_id},
            )

        worker.rpc.assert_awaited_once_with(
            "call", "get_interval_analysis", {"activity_id": fixture_activity_id}
        )
        response_data = json.loads(result[0].text)
        assert response_data["activity_id"] == fixture_activity_id
        assert "segments" in response_data

    @pytest.mark.asyncio
    async def test_call_serializes_complex_payload(
        self, fixture_activity_id: int
    ) -> None:
        """A nested worker payload is serialized into a single TextContent."""
        worker = AsyncMock()
        worker.rpc.return_value = {
            "ok": True,
            "data": {
                "target_activity": {"activity_id": fixture_activity_id},
                "similar_activities": [{"activity_id": 12345678900}],
            },
        }
        with patch.object(server, "worker", worker):
            result = await call_tool(
                name="compare_similar_workouts",
                arguments={"activity_id": fixture_activity_id},
            )

        assert len(result) == 1
        response_data = json.loads(result[0].text)
        assert response_data["target_activity"]["activity_id"] == fixture_activity_id
        assert len(response_data["similar_activities"]) == 1

    @pytest.mark.asyncio
    async def test_call_worker_validation_error_surfaces(
        self, fixture_activity_id: int
    ) -> None:
        """A worker validation error (ok=False) becomes an {'error': ...} payload."""
        worker = AsyncMock()
        worker.rpc.return_value = {
            "ok": False,
            "error": "Invalid parameter: activity_id field required",
        }
        with patch.object(server, "worker", worker):
            result = await call_tool(name="get_interval_analysis", arguments={})

        response = json.loads(result[0].text)
        assert "Invalid parameter" in response["error"]
        assert "activity_id" in response["error"]
