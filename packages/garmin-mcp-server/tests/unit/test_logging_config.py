"""Tests for MCP server logging configuration."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.mark.unit
class TestSetupMcpLogging:
    """Tests for setup_mcp_logging()."""

    def _clear_garmin_logger(self) -> None:
        """Remove all handlers from the garmin_mcp logger."""
        logger = logging.getLogger("garmin_mcp")
        logger.handlers.clear()
        logger.setLevel(logging.WARNING)

    def test_adds_stderr_handler(self, tmp_path: Path) -> None:
        """setup_mcp_logging() always adds a stderr StreamHandler."""
        from garmin_mcp.utils.logging_config import setup_mcp_logging

        self._clear_garmin_logger()
        setup_mcp_logging(log_dir=tmp_path)
        logger = logging.getLogger("garmin_mcp")
        stream_handlers = [
            h
            for h in logger.handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, RotatingFileHandler)
        ]
        assert len(stream_handlers) == 1
        self._clear_garmin_logger()

    def test_adds_file_handler_with_log_dir(self, tmp_path: Path) -> None:
        """setup_mcp_logging(log_dir=...) adds a RotatingFileHandler."""
        from garmin_mcp.utils.logging_config import setup_mcp_logging

        self._clear_garmin_logger()
        log_dir = tmp_path / "logs"
        setup_mcp_logging(log_dir=log_dir)

        logger = logging.getLogger("garmin_mcp")
        file_handlers = [
            h for h in logger.handlers if isinstance(h, RotatingFileHandler)
        ]
        assert len(file_handlers) == 1
        assert (log_dir / "mcp_server.log").exists()
        self._clear_garmin_logger()

    def test_rotating_file_handler_config(self, tmp_path: Path) -> None:
        """RotatingFileHandler has correct maxBytes and backupCount."""
        from garmin_mcp.utils.logging_config import (
            _BACKUP_COUNT,
            _MAX_BYTES,
            setup_mcp_logging,
        )

        self._clear_garmin_logger()
        log_dir = tmp_path / "logs"
        setup_mcp_logging(log_dir=log_dir)

        logger = logging.getLogger("garmin_mcp")
        file_handlers = [
            h for h in logger.handlers if isinstance(h, RotatingFileHandler)
        ]
        handler = file_handlers[0]
        assert handler.maxBytes == _MAX_BYTES
        assert handler.backupCount == _BACKUP_COUNT
        self._clear_garmin_logger()

    def test_sets_log_level(self, tmp_path: Path) -> None:
        """setup_mcp_logging(level=...) sets the logger level."""
        from garmin_mcp.utils.logging_config import setup_mcp_logging

        self._clear_garmin_logger()
        setup_mcp_logging(level="DEBUG", log_dir=tmp_path)
        logger = logging.getLogger("garmin_mcp")
        assert logger.level == logging.DEBUG
        self._clear_garmin_logger()

    def test_clears_handlers_on_repeated_calls(self, tmp_path: Path) -> None:
        """Calling setup_mcp_logging() twice doesn't duplicate handlers."""
        from garmin_mcp.utils.logging_config import setup_mcp_logging

        self._clear_garmin_logger()
        setup_mcp_logging(log_dir=tmp_path)
        setup_mcp_logging(log_dir=tmp_path)
        logger = logging.getLogger("garmin_mcp")
        # Should have exactly 2 handlers: stderr + file
        assert len(logger.handlers) == 2
        self._clear_garmin_logger()


@pytest.mark.unit
class TestCallToolLogging:
    """Tests for tool call logging in call_tool()."""

    @pytest.fixture
    def _patch_handlers(self, mocker: MockerFixture) -> None:
        """Patch _handlers to avoid real DB initialization."""
        import garmin_mcp.server as server_mod

        mock_handler = mocker.Mock()
        mock_handler.handles.return_value = True
        mock_handler.handle = mocker.AsyncMock(
            return_value=[{"type": "text", "text": "ok"}]
        )
        server_mod._handlers = [mock_handler]

    @pytest.fixture
    def _patch_handlers_error(self, mocker: MockerFixture) -> None:
        """Patch _handlers to raise an error."""
        import garmin_mcp.server as server_mod

        mock_handler = mocker.Mock()
        mock_handler.handles.return_value = True
        mock_handler.handle = mocker.AsyncMock(side_effect=RuntimeError("test error"))
        server_mod._handlers = [mock_handler]

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_patch_handlers")
    async def test_logs_info_on_success(self, caplog: pytest.LogCaptureFixture) -> None:
        """call_tool logs info with tool name, duration, and ok status."""
        from garmin_mcp.server import call_tool

        with caplog.at_level(logging.INFO, logger="garmin_mcp.server"):
            await call_tool("test_tool", {})

        assert any(
            "tool=test_tool" in r.message and "status=ok" in r.message
            for r in caplog.records
        )

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_patch_handlers")
    async def test_logs_duration_ms(self, caplog: pytest.LogCaptureFixture) -> None:
        """call_tool logs duration_ms."""
        from garmin_mcp.server import call_tool

        with caplog.at_level(logging.INFO, logger="garmin_mcp.server"):
            await call_tool("test_tool", {})

        assert any("duration_ms=" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_patch_handlers_error")
    async def test_logs_error_on_exception(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """call_tool logs error with tool name and error message on exception."""
        from garmin_mcp.server import call_tool

        with (
            caplog.at_level(logging.ERROR, logger="garmin_mcp.server"),
            pytest.raises(RuntimeError, match="test error"),
        ):
            await call_tool("failing_tool", {})

        assert any(
            "tool=failing_tool" in r.message
            and "status=error" in r.message
            and "test error" in r.message
            for r in caplog.records
        )
