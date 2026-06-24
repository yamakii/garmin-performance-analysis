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
from typing import Annotated, Any, Literal
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel, Field, ValidationError

from garmin_mcp.tool_schemas import get_tool_definitions
from garmin_mcp.tools import ALL_DEFS, ALL_DEFS_BY_NAME
from garmin_mcp.tools.registry import (
    ToolDef,
    build_mcp_tools,
    dispatch,
    to_mcp_input_schema,
)

_GOLDEN_PATH = Path(__file__).parent / "snapshots" / "all_tools_golden.json"

# Tools allowed to keep an ``input_schema_override`` (documented exceptions).
# ``extract_insights`` keeps one because its params model carries an internal
# ``activity_id`` validation field that the documented MCP surface intentionally
# hides, so a derived schema would not be byte-identical to the golden snapshot.
_OVERRIDE_ALLOWLIST = {"extract_insights"}


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
def test_all_tools_count_49() -> None:
    """ALL_DEFS holds the 50 handler-domain tools (unique names); the live MCP
    surface adds the 2 server tools for 52 total.

    #450 added 2 strength-session tools (ingest_strength_sessions,
    get_strength_sessions), raising the domain count from 44 to 46. #463 added
    the catch_up_ingest orchestrator, raising it to 47. #501 added
    get_body_composition_trend, raising it to 48. #499 added get_recovery_trend,
    raising it to 49. #500 added get_recovery_status, raising it to 50.
    """
    assert len(ALL_DEFS) == 50
    names = [d.name for d in ALL_DEFS]
    assert len(names) == len(set(names)), "duplicate tool names in ALL_DEFS"
    assert len(ALL_DEFS_BY_NAME) == 50

    live_names = [t.name for t in get_tool_definitions()]
    assert len(live_names) == 52
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
def test_export_derived_schema() -> None:
    """The export tool's inputSchema is now DERIVED from ``ExportParams`` (no
    ``input_schema_override``) yet remains byte-identical to the hand schema."""
    assert ALL_DEFS_BY_NAME["export"].input_schema_override is None
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


# ----------------------------------------------------------------------------
# Normalizer unit tests (Issue #333)
# ----------------------------------------------------------------------------


@pytest.mark.unit
def test_normalizer_enum() -> None:
    """``Literal[...]`` fields surface as an inline ``enum`` on the property,
    including the optional (``anyOf``) case."""

    class M(BaseModel):
        fmt: Literal["parquet", "csv"] = "parquet"
        opt: Literal["x", "y"] | None = None

    schema = to_mcp_input_schema(M)
    fmt = schema["properties"]["fmt"]
    assert fmt["type"] == "string"
    assert fmt["enum"] == ["parquet", "csv"]
    assert fmt["default"] == "parquet"

    opt = schema["properties"]["opt"]
    assert opt["type"] == "string"
    assert opt["enum"] == ["x", "y"]
    assert "default" not in opt  # None default dropped


@pytest.mark.unit
def test_normalizer_array_items_and_length() -> None:
    """``list[T]`` keeps ``items``; ``Annotated[list[T], Field(min/max_length)]``
    adds ``minItems``/``maxItems``."""

    class M(BaseModel):
        ids: list[int]
        pair: Annotated[list[float], Field(min_length=2, max_length=2)] | None = None

    schema = to_mcp_input_schema(M)
    ids = schema["properties"]["ids"]
    assert ids == {"type": "array", "items": {"type": "integer"}}

    pair = schema["properties"]["pair"]
    assert pair["type"] == "array"
    assert pair["items"] == {"type": "number"}
    assert pair["minItems"] == 2
    assert pair["maxItems"] == 2
    assert "default" not in pair


@pytest.mark.unit
def test_normalizer_drops_none_default() -> None:
    """An Optional field defaulting to ``None`` emits no ``default`` key and is
    not listed in ``required``."""

    class M(BaseModel):
        opt: str | None = None

    schema = to_mcp_input_schema(M)
    assert "default" not in schema["properties"]["opt"]
    assert "required" not in schema


@pytest.mark.unit
def test_normalizer_keeps_explicit_default() -> None:
    """Explicit non-None defaults (``False``, ``"parquet"``, ``10``, ``True``)
    are emitted as ``default``."""

    class M(BaseModel):
        flag: bool = False
        fmt: str = "parquet"
        limit: int = 10
        on: bool = True

    props = to_mcp_input_schema(M)["properties"]
    assert props["flag"]["default"] is False
    assert props["fmt"]["default"] == "parquet"
    assert props["limit"]["default"] == 10
    assert props["on"]["default"] is True


@pytest.mark.unit
def test_field_description_override() -> None:
    """``field_descriptions`` overwrites the named property's description while
    leaving the rest of the derived schema intact (shared-model pattern)."""

    class M(BaseModel):
        activity_id: int
        statistics_only: bool = False

    schema = to_mcp_input_schema(
        M, field_descriptions={"statistics_only": "tool-specific text"}
    )
    assert schema["properties"]["statistics_only"]["description"] == (
        "tool-specific text"
    )
    # Unrelated properties are untouched.
    assert schema["properties"]["activity_id"] == {"type": "integer"}


@pytest.mark.unit
def test_dispatch_rejects_invalid_enum() -> None:
    """Dispatching a tool with an out-of-range ``Literal`` value raises a
    pydantic ``ValidationError`` (the model is the faithful validator)."""
    reader = MagicMock()
    with pytest.raises(ValidationError):
        dispatch(
            ALL_DEFS_BY_NAME,
            reader,
            "get_analysis_contract",
            {"section_type": "not_a_section"},
        )


@pytest.mark.unit
def test_override_usage_minimized() -> None:
    """Exactly the allow-listed tools keep an ``input_schema_override``; every
    other tool's schema is derived from its params model."""
    with_override = {d.name for d in ALL_DEFS if d.input_schema_override is not None}
    assert with_override == _OVERRIDE_ALLOWLIST
    assert len(with_override) == 1


@pytest.mark.unit
def test_tooldef_has_field_descriptions_attr() -> None:
    """``ToolDef`` exposes the new ``field_descriptions`` override field."""
    assert "field_descriptions" in ToolDef.__dataclass_fields__


# ----------------------------------------------------------------------------
# reload_server schema simplification (Issue #481)
# ----------------------------------------------------------------------------


@pytest.mark.unit
def test_reload_server_schema_has_no_server_dir() -> None:
    """``reload_server`` takes no arguments: its ``inputSchema.properties`` is
    empty (the override ``server_dir`` argument was removed in #481)."""
    tools = {t.name: t for t in get_tool_definitions()}
    reload_tool = tools["reload_server"]
    assert reload_tool.inputSchema == {"type": "object", "properties": {}}
    assert reload_tool.inputSchema["properties"] == {}
    assert "server_dir" not in reload_tool.inputSchema["properties"]


@pytest.mark.unit
def test_tool_golden_snapshot_matches() -> None:
    """The live MCP surface still equals the (regenerated) golden snapshot."""
    golden = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))
    live = _as_dicts(get_tool_definitions())
    assert live == golden


@pytest.mark.unit
def test_tool_count_unchanged() -> None:
    """Removing ``server_dir`` does not change the tool count: ``reload_server``
    is retained by name; the surface serves 52 tools (50 domain + 2 server,
    after #500's get_recovery_status)."""
    live_names = [t.name for t in get_tool_definitions()]
    assert len(live_names) == 52
    assert "reload_server" in live_names
    assert "get_server_info" in live_names
