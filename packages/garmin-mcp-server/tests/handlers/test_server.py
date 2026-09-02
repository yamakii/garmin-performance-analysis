"""Unit tests for the MCP shim handlers (server.py).

The shim delegates all domain work to a ``WorkerClient``; these tests mock that
client so they stay fast and process-free. They cover the three shim responsibilities:
``list_tools`` (worker schema + 2 server tools), ``get_server_info`` (shim
started_at + worker DB diagnostics), and ``reload_server`` (worker restart +
tools/list_changed, no process suicide).
"""

import json
from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    TextContent,
)

import garmin_mcp.server as server
from garmin_mcp.server import (
    _dispatch_tool,
    _handle_get_server_info,
    _handle_reload_server,
    _serialize_result,
    call_tool,
    list_tools,
)


def _text(result: CallToolResult) -> str:
    """Return the text of a tool result's single content block."""
    block = result.content[0]
    assert isinstance(block, TextContent)
    return block.text


def _ctx(session: Any = None) -> Any:
    """Minimal stand-in for the ``ServerRequestContext`` mcp 2.x passes handlers."""
    return SimpleNamespace(session=session)


def _mock_worker(rpc_side_effect=None, rpc_return=None) -> AsyncMock:
    """Build an AsyncMock standing in for the module-level WorkerClient."""
    worker = AsyncMock()
    if rpc_side_effect is not None:
        worker.rpc.side_effect = rpc_side_effect
    elif rpc_return is not None:
        worker.rpc.return_value = rpc_return
    return worker


@pytest.mark.unit
class TestListTools:
    """Tests for list_tools (worker schema + 2 server tools)."""

    @pytest.mark.asyncio
    async def test_appends_two_server_tools(self) -> None:
        """Domain tools from the worker are returned plus get_server_info/reload_server."""
        worker = _mock_worker(
            rpc_return={
                "ok": True,
                "data": [
                    {
                        "name": "get_performance_trends",
                        "description": "d",
                        "inputSchema": {"type": "object"},
                    }
                ],
            }
        )
        with patch.object(server, "worker", worker):
            tools = (await list_tools(_ctx(), None)).tools

        names = [t.name for t in tools]
        assert names == [
            "get_performance_trends",
            "get_server_info",
            "reload_server",
        ]
        worker.rpc.assert_awaited_once_with("schema")

    @pytest.mark.asyncio
    async def test_worker_schema_failure_still_returns_server_tools(self) -> None:
        """If the worker schema rpc fails, the 2 server tools are still listed."""
        worker = _mock_worker(rpc_return={"ok": False, "error": "boom"})
        with patch.object(server, "worker", worker):
            tools = (await list_tools(_ctx(), None)).tools

        names = {t.name for t in tools}
        assert names == {"get_server_info", "reload_server"}

    @pytest.mark.asyncio
    async def test_list_tools_returns_list_tools_result(self) -> None:
        """The handler returns a ListToolsResult whose tools carry input_schema."""
        worker = _mock_worker(
            rpc_return={
                "ok": True,
                "data": [
                    {
                        "name": "get_performance_trends",
                        "description": "d1",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"activity_id": {"type": "integer"}},
                        },
                    },
                    {
                        "name": "get_splits_comprehensive",
                        "description": "d2",
                        "inputSchema": {"type": "object", "properties": {}},
                    },
                ],
            }
        )
        with patch.object(server, "worker", worker):
            result = await list_tools(_ctx(), None)

        assert isinstance(result, ListToolsResult)
        # 2 worker domain tools + the 2 server tools.
        assert len(result.tools) == 4
        assert result.tools[0].input_schema == {
            "type": "object",
            "properties": {"activity_id": {"type": "integer"}},
        }
        assert result.tools[1].input_schema == {"type": "object", "properties": {}}


@pytest.mark.unit
class TestHandleGetServerInfo:
    """Tests for _handle_get_server_info (shim + worker merge)."""

    @pytest.mark.asyncio
    async def test_merges_started_at_and_table_count(self) -> None:
        """Shim started_at + worker table_count/last_ingest_date are merged."""
        worker = _mock_worker(
            rpc_return={
                "ok": True,
                "data": {
                    "db_path": "/x/db.duckdb",
                    "started_at": "2025-10-15T00:00:00+00:00",
                    "table_count": 14,
                    "last_ingest_date": "2025-10-15",
                },
            }
        )
        with patch.object(server, "worker", worker):
            result = await _handle_get_server_info()

        data = json.loads(result[0].text)
        assert isinstance(data["started_at"], str)
        assert data["ready"] is True
        assert data["db_status"] == "connected"
        assert data["table_count"] == 14
        assert data["last_ingest_date"] == "2025-10-15"
        assert data["worker_started_at"] == "2025-10-15T00:00:00+00:00"
        worker.rpc.assert_awaited_once_with("info")

    @pytest.mark.asyncio
    async def test_worker_info_failure_reports_error(self) -> None:
        """A failed worker info rpc degrades to an error db_status, null counts."""
        worker = _mock_worker(rpc_return={"ok": False, "error": "worker down"})
        with patch.object(server, "worker", worker):
            result = await _handle_get_server_info()

        data = json.loads(result[0].text)
        assert data["ready"] is False
        assert "error" in data["db_status"]
        assert data["table_count"] is None
        assert data["last_ingest_date"] is None

    @pytest.mark.asyncio
    async def test_worker_db_error_surfaces_db_status_error(self) -> None:
        """A worker that connected but hit a DB error reports db_status=error."""
        worker = _mock_worker(
            rpc_return={
                "ok": True,
                "data": {
                    "db_path": "/x/db.duckdb",
                    "started_at": "2025-10-15T00:00:00+00:00",
                    "table_count": 0,
                    "last_ingest_date": None,
                    "db_error": "RuntimeError('locked')",
                },
            }
        )
        with patch.object(server, "worker", worker):
            result = await _handle_get_server_info()

        data = json.loads(result[0].text)
        assert data["ready"] is True
        assert data["db_status"] == "error"
        assert data["db_error"] == "RuntimeError('locked')"


@pytest.mark.unit
class TestHandleReloadServer:
    """Tests for _handle_reload_server (restart worker, notify, stay alive)."""

    @pytest.mark.asyncio
    async def test_reload_server_sends_list_changed_via_ctx_session(self) -> None:
        """reload_server restarts the worker and notifies via the call's session."""
        worker = AsyncMock()
        mock_session = AsyncMock()
        with patch.object(server, "worker", worker):
            result = await _handle_reload_server(mock_session)

        worker.restart.assert_awaited_once()
        mock_session.send_tool_list_changed.assert_awaited_once()
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["list_changed_sent"] is True

    @pytest.mark.asyncio
    async def test_reload_server_without_session_still_restarts(self) -> None:
        """Without a session, the restart succeeds but the notify is skipped."""
        worker = AsyncMock()
        with patch.object(server, "worker", worker):
            result = await _handle_reload_server()

        worker.restart.assert_awaited_once()
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["list_changed_sent"] is False

    @pytest.mark.asyncio
    async def test_takes_no_server_dir_argument(self) -> None:
        """reload_server takes only the notification session, no server_dir."""
        import inspect

        sig = inspect.signature(_handle_reload_server)
        assert list(sig.parameters) == ["session"]

    @pytest.mark.asyncio
    async def test_response_is_valid_json(self) -> None:
        """reload_server response is always valid JSON."""
        worker = AsyncMock()
        with patch.object(server, "worker", worker):
            result = await _handle_reload_server(AsyncMock())

        data = json.loads(result[0].text)
        assert data["success"] is True


@pytest.mark.unit
class TestDispatchTool:
    """Tests for _dispatch_tool routing (server tools inline, rest -> worker)."""

    @pytest.mark.asyncio
    async def test_dispatch_domain_tool_delegates_to_worker(self) -> None:
        """A domain tool is delegated to worker.rpc('call', ...) and serialized."""
        worker = _mock_worker(
            rpc_return={"ok": True, "data": {"activity_id": 7, "date": "2025-10-09"}}
        )
        with patch.object(server, "worker", worker):
            result = await _dispatch_tool("get_date_by_activity_id", {"activity_id": 7})

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data == {"activity_id": 7, "date": "2025-10-09"}
        worker.rpc.assert_awaited_once_with(
            "call", "get_date_by_activity_id", {"activity_id": 7}
        )

    @pytest.mark.asyncio
    async def test_dispatch_worker_error_becomes_error_payload(self) -> None:
        """A worker ok=False response surfaces as an {'error': ...} payload."""
        worker = _mock_worker(rpc_return={"ok": False, "error": "Unknown tool: nope"})
        with patch.object(server, "worker", worker):
            result = await _dispatch_tool("nope", {})

        data = json.loads(result[0].text)
        assert data["error"] == "Unknown tool: nope"

    @pytest.mark.asyncio
    async def test_dispatch_server_tool_get_server_info(self) -> None:
        """get_server_info is handled inline via the worker info rpc."""
        worker = _mock_worker(
            rpc_return={
                "ok": True,
                "data": {"table_count": 1, "started_at": "t", "last_ingest_date": None},
            }
        )
        with patch.object(server, "worker", worker):
            result = await _dispatch_tool("get_server_info", {})

        data = json.loads(result[0].text)
        assert "started_at" in data
        assert data["ready"] is True

    @pytest.mark.asyncio
    async def test_dispatch_tool_result_unescaped(self) -> None:
        """Japanese in a worker payload reaches the client raw, not \\uXXXX escaped."""
        worker = _mock_worker(rpc_return={"ok": True, "data": {"note": "評価"}})
        with patch.object(server, "worker", worker):
            result = await _dispatch_tool("get_section_analyses", {"activity_id": 7})

        text = result[0].text
        assert "評価" in text
        assert "\\u" not in text
        assert json.loads(text) == {"note": "評価"}


@pytest.mark.unit
class TestCallTool:
    """Tests for the mcp 2.x call_tool handler (params in, CallToolResult out)."""

    @pytest.mark.asyncio
    async def test_call_tool_wraps_dispatch_exception_as_is_error(self) -> None:
        """A dispatch exception becomes an is_error result, not a JSON-RPC error."""
        with patch.object(
            server, "_dispatch_tool", AsyncMock(side_effect=RuntimeError("boom"))
        ):
            result = await call_tool(
                _ctx(), CallToolRequestParams(name="get_server_info", arguments={})
            )

        assert result.is_error is True
        assert "boom" in _text(result)

    @pytest.mark.asyncio
    async def test_call_tool_none_arguments_defaults_to_empty(self) -> None:
        """``arguments=None`` is normalized to an empty dict (no TypeError)."""
        worker = _mock_worker(
            rpc_return={
                "ok": True,
                "data": {"table_count": 1, "started_at": "t", "last_ingest_date": None},
            }
        )
        with patch.object(server, "worker", worker):
            result = await call_tool(
                _ctx(), CallToolRequestParams(name="get_server_info", arguments=None)
            )

        assert not result.is_error
        data = json.loads(_text(result))
        assert data["ready"] is True


@pytest.mark.unit
class TestSerializeResult:
    """Tests for _serialize_result (MCP boundary serialization)."""

    def test_serialize_result_keeps_japanese_unescaped(self) -> None:
        """Japanese stays raw (no \\uXXXX escapes) so payloads stay ~3-4x smaller."""
        text = _serialize_result({"msg": "日本語テスト"})

        assert "日本語テスト" in text
        assert "\\u" not in text

    def test_serialize_result_compact_and_default_str(self) -> None:
        """Compact separators are used and dates fall back to str()."""
        text = _serialize_result({"a": 1, "d": date(2026, 8, 19)})

        assert text == '{"a":1,"d":"2026-08-19"}'
