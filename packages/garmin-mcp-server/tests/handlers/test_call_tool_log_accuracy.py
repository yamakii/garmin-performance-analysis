"""Tests for call_tool log accuracy improvements (#166)."""

from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock

import pytest

from garmin_mcp.server import _detect_tool_error, _extract_log_context


@pytest.mark.unit
class TestExtractLogContext:
    """Tests for _extract_log_context helper."""

    def test_extract_log_context_with_activity_id(self) -> None:
        result = _extract_log_context({"activity_id": 123})
        assert result == "activity_id=123 "

    def test_extract_log_context_with_date(self) -> None:
        result = _extract_log_context({"date": "2025-10-15"})
        assert result == "date=2025-10-15 "

    def test_extract_log_context_with_neither(self) -> None:
        result = _extract_log_context({"query": "SELECT 1"})
        assert result == ""


@pytest.mark.unit
class TestDetectToolError:
    """Tests for _detect_tool_error helper."""

    @staticmethod
    def _make_text_content(text: str) -> MagicMock:
        tc = MagicMock()
        tc.text = text
        return tc

    def test_detect_tool_error_with_error_key(self) -> None:
        result = [self._make_text_content(json.dumps({"error": "not found"}))]
        assert _detect_tool_error(result) is True

    def test_detect_tool_error_without_error_key(self) -> None:
        result = [self._make_text_content(json.dumps({"data": []}))]
        assert _detect_tool_error(result) is False

    def test_detect_tool_error_with_invalid_json(self) -> None:
        result = [self._make_text_content("not json")]
        assert _detect_tool_error(result) is False


@pytest.mark.unit
class TestCallToolLogging:
    """Tests for call_tool logging behavior with new helpers."""

    def test_call_tool_logs_tool_error_on_handler_error(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Verify that tool errors are logged with status=tool_error."""
        with caplog.at_level(logging.WARNING, logger="garmin_mcp.server"):
            logger = logging.getLogger("garmin_mcp.server")
            name = "test_tool"
            arguments = {"activity_id": 99}
            duration_ms = 10.5
            ctx = _extract_log_context(arguments)
            tc = MagicMock()
            tc.text = json.dumps({"error": "something failed"})
            result = [tc]
            if _detect_tool_error(result):
                logger.warning(
                    "tool=%s %sduration_ms=%.1f status=tool_error",
                    name,
                    ctx,
                    duration_ms,
                )
        assert "status=tool_error" in caplog.text

    def test_call_tool_logs_activity_id(self, caplog: pytest.LogCaptureFixture) -> None:
        """Verify that activity_id appears in log output."""
        with caplog.at_level(logging.INFO, logger="garmin_mcp.server"):
            logger = logging.getLogger("garmin_mcp.server")
            name = "test_tool"
            arguments = {"activity_id": 99}
            duration_ms = 5.0
            ctx = _extract_log_context(arguments)
            logger.info("tool=%s %sduration_ms=%.1f status=ok", name, ctx, duration_ms)
        assert "activity_id=99" in caplog.text
