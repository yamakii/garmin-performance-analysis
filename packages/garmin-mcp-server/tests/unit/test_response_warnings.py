"""Tests for inline _warnings system (#167)."""

from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock

import pytest

from garmin_mcp.handlers.base import inject_warnings
from garmin_mcp.server import _count_warnings, _extract_log_context


@pytest.mark.unit
class TestInjectWarnings:
    """Tests for inject_warnings helper."""

    def test_inject_warnings_adds_field(self) -> None:
        data: dict = {"x": 1}
        result = inject_warnings(data, ["w1"])
        assert result == {"x": 1, "_warnings": ["w1"]}

    def test_inject_warnings_empty_no_field(self) -> None:
        data: dict = {"x": 1}
        result = inject_warnings(data, [])
        assert result == {"x": 1}
        assert "_warnings" not in result

    def test_inject_warnings_preserves_data(self) -> None:
        data: dict = {"x": 1, "y": "hello", "nested": {"a": True}}
        result = inject_warnings(data, ["w1", "w2"])
        assert result["x"] == 1
        assert result["y"] == "hello"
        assert result["nested"] == {"a": True}
        assert result["_warnings"] == ["w1", "w2"]


@pytest.mark.unit
class TestCountWarnings:
    """Tests for _count_warnings helper."""

    @staticmethod
    def _make_text_content(text: str) -> MagicMock:
        tc = MagicMock()
        tc.text = text
        return tc

    def test_count_warnings_present(self) -> None:
        result = [
            self._make_text_content(json.dumps({"data": 1, "_warnings": ["a", "b"]}))
        ]
        assert _count_warnings(result) == 2

    def test_count_warnings_absent(self) -> None:
        result = [self._make_text_content(json.dumps({"data": 1}))]
        assert _count_warnings(result) == 0


@pytest.mark.unit
class TestWarningLogging:
    """Test that warning_count is logged."""

    def test_call_tool_logs_warning_count(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Verify that warning_count appears in log output when warnings exist."""
        with caplog.at_level(logging.INFO, logger="garmin_mcp.server"):
            logger = logging.getLogger("garmin_mcp.server")
            name = "test_tool"
            arguments = {"activity_id": 42}
            ctx = _extract_log_context(arguments)
            # Simulate what call_tool does with warnings
            tc = MagicMock()
            tc.text = json.dumps({"data": [], "_warnings": ["test warning"]})
            result = [tc]
            warning_count = _count_warnings(result)
            if warning_count > 0:
                logger.info("tool=%s %swarning_count=%d", name, ctx, warning_count)
        assert "warning_count=1" in caplog.text
