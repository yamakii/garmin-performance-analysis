"""Unit tests for the full single-source registry rollout (all 8 domains).

These guard the byte-for-byte parity contract for *every* tool: the
registry-derived schemas (``build_mcp_tools(ALL_DEFS)`` + the two server tools)
must equal the immutable golden snapshot captured from the pre-rollout MCP
surface, dispatch must route each domain to the correct underlying call, and the
``export`` tool's hand-written ``inputSchema`` override must be served verbatim.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from garmin_mcp.tool_schemas import get_tool_definitions
from garmin_mcp.tools import ALL_DEFS, ALL_DEFS_BY_NAME
from garmin_mcp.tools.registry import build_mcp_tools, dispatch

_GOLDEN_PATH = Path(__file__).parent / "snapshots" / "all_tools_golden.json"


def _as_dicts(tools: Any) -> list[dict[str, Any]]:
    return [
        {
            "name": t.name,
            "description": t.description,
            "inputSchema": t.inputSchema,
        }
        for t in tools
    ]


@pytest.mark.unit
def test_schema_parity_all_tools() -> None:
    """The full live MCP surface equals the immutable golden snapshot."""
    golden = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))

    live = _as_dicts(get_tool_definitions())

    # Same ordering and same dict contents (name/description/inputSchema).
    assert [t["name"] for t in live] == [t["name"] for t in golden]
    assert live == golden


@pytest.mark.unit
def test_all_tools_count_41() -> None:
    """ALL_DEFS holds the 39 handler-domain tools (unique names); the live MCP
    surface adds the 2 server tools for 41 total."""
    assert len(ALL_DEFS) == 39
    names = [d.name for d in ALL_DEFS]
    assert len(names) == len(set(names)), "duplicate tool names in ALL_DEFS"
    assert len(ALL_DEFS_BY_NAME) == 39

    live_names = [t.name for t in get_tool_definitions()]
    assert len(live_names) == 41
    assert len(live_names) == len(
        set(live_names)
    ), "duplicate tool names on MCP surface"
    assert "get_server_info" in live_names
    assert "reload_server" in live_names


@pytest.mark.unit
def test_dispatch_all_domains() -> None:
    """Each domain's representative tool routes to the expected underlying call."""
    # splits -> reader.get_splits_pace_hr(activity_id, statistics_only=...)
    reader = MagicMock()
    reader.get_splits_pace_hr.return_value = {"splits": []}
    dispatch(ALL_DEFS_BY_NAME, reader, "get_splits_pace_hr", {"activity_id": 1})
    reader.get_splits_pace_hr.assert_called_once_with(1, statistics_only=False)

    # metadata -> reader.get_activity_date(activity_id)
    reader = MagicMock()
    reader.get_activity_date.return_value = "2025-10-09"
    result = dispatch(
        ALL_DEFS_BY_NAME, reader, "get_date_by_activity_id", {"activity_id": 7}
    )
    reader.get_activity_date.assert_called_once_with(7)
    assert result == {"activity_id": 7, "date": "2025-10-09"}

    # performance -> reader.get_performance_trends(activity_id)
    reader = MagicMock()
    reader.get_performance_trends.return_value = {"ok": True}
    dispatch(ALL_DEFS_BY_NAME, reader, "get_performance_trends", {"activity_id": 3})
    reader.get_performance_trends.assert_called_once_with(3)

    # analysis -> WorkoutComparator.find_similar_workouts(...)
    reader = MagicMock()
    with patch(
        "garmin_mcp.rag.queries.comparisons.WorkoutComparator"
    ) as comparator_cls:
        comparator_cls.return_value.find_similar_workouts.return_value = {"matches": []}
        dispatch(
            ALL_DEFS_BY_NAME,
            reader,
            "compare_similar_workouts",
            {"activity_id": 42},
        )
        comparator_cls.return_value.find_similar_workouts.assert_called_once()
        kwargs = comparator_cls.return_value.find_similar_workouts.call_args.kwargs
        assert kwargs["activity_id"] == 42
        assert kwargs["pace_tolerance"] == 0.2
        assert kwargs["distance_tolerance"] == 0.2

    # time_series -> TimeSeriesDetailExtractor.get_split_time_series_detail(...)
    reader = MagicMock()
    with patch(
        "garmin_mcp.rag.queries.time_series_detail.TimeSeriesDetailExtractor"
    ) as extractor_cls:
        extractor_cls.return_value.get_split_time_series_detail.return_value = {"d": 1}
        dispatch(
            ALL_DEFS_BY_NAME,
            reader,
            "get_split_time_series_detail",
            {"activity_id": 5, "split_number": 2},
        )
        extractor_cls.return_value.get_split_time_series_detail.assert_called_once()
        kwargs = (
            extractor_cls.return_value.get_split_time_series_detail.call_args.kwargs
        )
        assert kwargs["activity_id"] == 5
        assert kwargs["split_number"] == 2
        assert kwargs["z_threshold"] == 2.0

    # training_plan -> TrainingPlanReader.get_training_plan(...)
    reader = MagicMock()
    reader.db_path = ":memory:"
    with patch(
        "garmin_mcp.database.readers.training_plans.TrainingPlanReader"
    ) as plan_reader_cls:
        plan_reader_cls.return_value.get_training_plan.return_value = {"plan_id": "p1"}
        dispatch(ALL_DEFS_BY_NAME, reader, "get_training_plan", {"plan_id": "p1"})
        plan_reader_cls.return_value.get_training_plan.assert_called_once_with(
            plan_id="p1", version=None, week_number=None, summary_only=False
        )

    # athlete -> AthleteReader.get_athlete_profile(...)
    reader = MagicMock()
    reader.db_path = ":memory:"
    with patch("garmin_mcp.database.readers.athlete.AthleteReader") as athlete_cls:
        athlete_cls.return_value.get_athlete_profile.return_value = {"goals": []}
        dispatch(ALL_DEFS_BY_NAME, reader, "get_athlete_profile", {})
        athlete_cls.return_value.get_athlete_profile.assert_called_once_with(
            user_id="default"
        )

    # export -> reader.export_query_result(...) via the export manager
    reader = MagicMock()
    reader.export_query_result.return_value = {
        "rows": 1,
        "size_mb": 0.1,
        "columns": ["a"],
    }
    with patch("garmin_mcp.mcp_server.export_manager.get_export_manager") as get_mgr:
        get_mgr.return_value.create_export_handle.return_value = (
            "/tmp/x.parquet",
            "handle-1",
            0,
        )
        result = dispatch(ALL_DEFS_BY_NAME, reader, "export", {"query": "SELECT 1"})
        reader.export_query_result.assert_called_once()
        assert isinstance(result, dict)
        assert result["handle"] == "handle-1"
        assert result["rows"] == 1


@pytest.mark.unit
def test_export_override_schema() -> None:
    """The export tool serves the verbatim hand-written inputSchema."""
    export_tool = next(t for t in build_mcp_tools(ALL_DEFS) if t.name == "export")
    assert export_tool.inputSchema == {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "DuckDB SQL query to execute",
            },
            "format": {
                "type": "string",
                "enum": ["parquet", "csv"],
                "description": "Output format (parquet recommended for efficiency)",
                "default": "parquet",
            },
            "max_rows": {
                "type": "integer",
                "description": "Safety limit for export size (default: 100000)",
                "default": 100000,
            },
        },
        "required": ["query"],
    }
