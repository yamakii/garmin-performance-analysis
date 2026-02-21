"""Tests for server-level tool handlers (reload_server)."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from garmin_mcp.server import _handle_reload_server


@pytest.mark.unit
class TestHandleReloadServer:
    """Tests for _handle_reload_server."""

    @pytest.mark.asyncio
    async def test_returns_success_response(self) -> None:
        """reload_server returns a success JSON response."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        with patch("garmin_mcp.server.asyncio.get_event_loop", return_value=mock_loop):
            result = await _handle_reload_server()

        assert len(result) == 1
        assert result[0].type == "text"
        assert '"success": true' in result[0].text
        assert "restart" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_schedules_exit(self) -> None:
        """reload_server schedules os._exit(0) after 0.5s delay."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        with (
            patch("garmin_mcp.server.asyncio.get_event_loop", return_value=mock_loop),
            patch("garmin_mcp.server.os._exit") as mock_exit,
        ):
            await _handle_reload_server()

        mock_loop.call_later.assert_called_once_with(0.5, mock_exit, 0)
