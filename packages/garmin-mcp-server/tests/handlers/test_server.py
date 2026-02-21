"""Tests for server-level tool handlers (reload_server)."""

import asyncio
from unittest.mock import MagicMock, mock_open, patch

import pytest

from garmin_mcp.server import _handle_reload_server


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
        assert '"success": true' in result[0].text
        assert "default" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_schedules_exit(self) -> None:
        """reload_server schedules os._exit(0) after 0.5s delay."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        with (
            patch("garmin_mcp.server.asyncio.get_event_loop", return_value=mock_loop),
            patch("garmin_mcp.server.os._exit") as mock_exit,
            patch("garmin_mcp.server.os.path.exists", return_value=False),
        ):
            await _handle_reload_server()

        mock_loop.call_later.assert_called_once_with(0.5, mock_exit, 0)

    @pytest.mark.asyncio
    async def test_with_server_dir_writes_override_file(self) -> None:
        """reload_server with server_dir writes the path to override file."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        test_dir = "/tmp/test-worktree/packages/garmin-mcp-server"
        m = mock_open()
        with (
            patch("garmin_mcp.server.asyncio.get_event_loop", return_value=mock_loop),
            patch("builtins.open", m),
        ):
            result = await _handle_reload_server(server_dir=test_dir)

        m.assert_called_once_with("/tmp/garmin-mcp-server-dir", "w")
        m().write.assert_called_once_with(test_dir)
        assert test_dir in result[0].text

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
        assert "default" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_response_includes_directory_info(self) -> None:
        """reload_server response includes directory information."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        test_dir = "/path/to/worktree/packages/garmin-mcp-server"
        with (
            patch("garmin_mcp.server.asyncio.get_event_loop", return_value=mock_loop),
            patch("builtins.open", mock_open()),
        ):
            result = await _handle_reload_server(server_dir=test_dir)

        assert '"success": true' in result[0].text
        assert test_dir in result[0].text
