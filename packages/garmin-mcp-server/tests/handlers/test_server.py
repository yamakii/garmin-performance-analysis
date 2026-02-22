"""Tests for server-level tool handlers (reload_server, get_server_info)."""

import asyncio
import json
from unittest.mock import MagicMock, mock_open, patch

import pytest

from garmin_mcp.server import _handle_get_server_info, _handle_reload_server


@pytest.mark.unit
class TestHandleGetServerInfo:
    """Tests for _handle_get_server_info."""

    def test_returns_server_dir(self) -> None:
        """get_server_info returns the server directory."""
        with (
            patch(
                "garmin_mcp.server._get_server_dir",
                return_value="/some/path/garmin-mcp-server",
            ),
            patch("garmin_mcp.server.os.path.exists", return_value=False),
        ):
            result = _handle_get_server_info()

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["server_dir"] == "/some/path/garmin-mcp-server"
        assert data["override_file_exists"] is False
        assert data["override_dir"] is None

    def test_with_override_file(self) -> None:
        """get_server_info includes override info when file exists."""
        with (
            patch(
                "garmin_mcp.server._get_server_dir",
                return_value="/default/garmin-mcp-server",
            ),
            patch("garmin_mcp.server.os.path.exists", return_value=True),
            patch(
                "builtins.open",
                mock_open(read_data="/worktree/packages/garmin-mcp-server"),
            ),
        ):
            result = _handle_get_server_info()

        data = json.loads(result[0].text)
        assert data["override_file_exists"] is True
        assert data["override_dir"] == "/worktree/packages/garmin-mcp-server"


@pytest.mark.unit
class TestHandleReloadServer:
    """Tests for _handle_reload_server."""

    @pytest.mark.asyncio
    async def test_returns_success_response_default(self) -> None:
        """reload_server without server_dir returns default directory message."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        with (
            patch("garmin_mcp.server.asyncio.get_event_loop", return_value=mock_loop),
            patch("garmin_mcp.server.os.path.exists", return_value=False),
        ):
            result = await _handle_reload_server()

        assert len(result) == 1
        assert result[0].type == "text"
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert "default" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_schedules_graceful_shutdown(self) -> None:
        """reload_server schedules _graceful_shutdown after 0.5s delay."""
        from garmin_mcp.server import _graceful_shutdown

        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        with (
            patch("garmin_mcp.server.asyncio.get_event_loop", return_value=mock_loop),
            patch("garmin_mcp.server.os.path.exists", return_value=False),
        ):
            await _handle_reload_server()

        mock_loop.call_later.assert_called_once_with(0.5, _graceful_shutdown)

    @pytest.mark.asyncio
    async def test_with_valid_server_dir_writes_override_file(self) -> None:
        """reload_server with valid server_dir writes the path to override file."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        test_dir = "/tmp/test-worktree/packages/garmin-mcp-server"
        m = mock_open()
        with (
            patch("garmin_mcp.server.asyncio.get_event_loop", return_value=mock_loop),
            patch("garmin_mcp.server.os.path.isdir", return_value=True),
            patch("garmin_mcp.server.os.path.isfile", return_value=True),
            patch("builtins.open", m),
        ):
            result = await _handle_reload_server(server_dir=test_dir)

        m.assert_called_once_with("/tmp/garmin-mcp-server-dir", "w")
        m().write.assert_called_once_with(test_dir)
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert test_dir in data["message"]

    @pytest.mark.asyncio
    async def test_with_invalid_server_dir_returns_error(self) -> None:
        """reload_server with invalid server_dir returns error without exiting."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        test_dir = "/nonexistent/path"
        with (
            patch("garmin_mcp.server.asyncio.get_event_loop", return_value=mock_loop),
            patch("garmin_mcp.server.os.path.isdir", return_value=False),
        ):
            result = await _handle_reload_server(server_dir=test_dir)

        data = json.loads(result[0].text)
        assert data["success"] is False
        assert "Invalid server_dir" in data["error"]
        # Should NOT schedule exit
        mock_loop.call_later.assert_not_called()

    @pytest.mark.asyncio
    async def test_with_dir_missing_pyproject_returns_error(self) -> None:
        """reload_server with dir that exists but has no pyproject.toml returns error."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        test_dir = "/exists/but/no/pyproject"
        with (
            patch("garmin_mcp.server.asyncio.get_event_loop", return_value=mock_loop),
            patch("garmin_mcp.server.os.path.isdir", return_value=True),
            patch("garmin_mcp.server.os.path.isfile", return_value=False),
        ):
            result = await _handle_reload_server(server_dir=test_dir)

        data = json.loads(result[0].text)
        assert data["success"] is False
        mock_loop.call_later.assert_not_called()

    @pytest.mark.asyncio
    async def test_without_server_dir_removes_override_file(self) -> None:
        """reload_server without server_dir removes the override file."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        with (
            patch("garmin_mcp.server.asyncio.get_event_loop", return_value=mock_loop),
            patch("garmin_mcp.server.os.path.exists", return_value=True),
            patch("garmin_mcp.server.os.remove") as mock_remove,
        ):
            result = await _handle_reload_server()

        mock_remove.assert_called_once_with("/tmp/garmin-mcp-server-dir")
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert "default" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_response_is_valid_json(self) -> None:
        """reload_server response is always valid JSON."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        test_dir = '/path/with special"chars/garmin-mcp-server'
        with (
            patch("garmin_mcp.server.asyncio.get_event_loop", return_value=mock_loop),
            patch("garmin_mcp.server.os.path.isdir", return_value=True),
            patch("garmin_mcp.server.os.path.isfile", return_value=True),
            patch("builtins.open", mock_open()),
        ):
            result = await _handle_reload_server(server_dir=test_dir)

        # Must not raise
        data = json.loads(result[0].text)
        assert data["success"] is True


@pytest.mark.unit
class TestGracefulShutdown:
    """Tests for _graceful_shutdown."""

    def test_calls_export_manager_cleanup(self) -> None:
        """_graceful_shutdown calls ExportManager.cleanup_all()."""
        from garmin_mcp.server import _graceful_shutdown

        mock_export_mgr = MagicMock()
        mock_view_mgr = MagicMock()
        with (
            patch(
                "garmin_mcp.server.get_export_manager",
                return_value=mock_export_mgr,
                create=True,
            ),
            patch(
                "garmin_mcp.mcp_server.export_manager.get_export_manager",
                return_value=mock_export_mgr,
            ),
            patch(
                "garmin_mcp.mcp_server.view_manager.get_view_manager",
                return_value=mock_view_mgr,
            ),
            patch("garmin_mcp.server.os._exit") as mock_exit,
        ):
            _graceful_shutdown()

        mock_export_mgr.cleanup_all.assert_called_once()
        mock_exit.assert_called_once_with(0)

    def test_calls_view_manager_cleanup(self) -> None:
        """_graceful_shutdown calls ViewManager.cleanup_all()."""
        from garmin_mcp.server import _graceful_shutdown

        mock_export_mgr = MagicMock()
        mock_view_mgr = MagicMock()
        with (
            patch(
                "garmin_mcp.mcp_server.export_manager.get_export_manager",
                return_value=mock_export_mgr,
            ),
            patch(
                "garmin_mcp.mcp_server.view_manager.get_view_manager",
                return_value=mock_view_mgr,
            ),
            patch("garmin_mcp.server.os._exit"),
        ):
            _graceful_shutdown()

        mock_view_mgr.cleanup_all.assert_called_once()

    def test_handles_uninitialized_managers(self) -> None:
        """_graceful_shutdown does not raise when managers are not initialized."""
        from garmin_mcp.server import _graceful_shutdown

        with (
            patch(
                "garmin_mcp.mcp_server.export_manager.get_export_manager",
                side_effect=Exception("not initialized"),
            ),
            patch(
                "garmin_mcp.mcp_server.view_manager.get_view_manager",
                side_effect=Exception("not initialized"),
            ),
            patch("garmin_mcp.server.os._exit") as mock_exit,
        ):
            _graceful_shutdown()

        mock_exit.assert_called_once_with(0)

    def test_calls_os_exit(self) -> None:
        """_graceful_shutdown calls os._exit(0)."""
        from garmin_mcp.server import _graceful_shutdown

        mock_export_mgr = MagicMock()
        mock_view_mgr = MagicMock()
        with (
            patch(
                "garmin_mcp.mcp_server.export_manager.get_export_manager",
                return_value=mock_export_mgr,
            ),
            patch(
                "garmin_mcp.mcp_server.view_manager.get_view_manager",
                return_value=mock_view_mgr,
            ),
            patch("garmin_mcp.server.os._exit") as mock_exit,
        ):
            _graceful_shutdown()

        mock_exit.assert_called_once_with(0)
