"""Tests for the safe_tool_handler decorator."""

import json

import pytest
from mcp.types import TextContent

from garmin_mcp.utils.error_handling import LLMSafeError, safe_tool_handler


@pytest.mark.unit
class TestSafeToolHandler:
    """Tests for the safe_tool_handler decorator."""

    @pytest.mark.asyncio
    async def test_normal_response_passes_through(self) -> None:
        expected = [TextContent(type="text", text='{"ok": true}')]

        @safe_tool_handler
        async def handler() -> list[TextContent]:
            return expected

        result = await handler()
        assert result is expected

    @pytest.mark.asyncio
    async def test_llm_safe_error_formatted(self) -> None:
        @safe_tool_handler
        async def handler() -> list[TextContent]:
            raise LLMSafeError(
                message="Activity not found",
                suggestion="Check the activity ID",
            )

        result = await handler()
        assert len(result) == 1
        body = json.loads(result[0].text)
        assert body["error"] == "Activity not found"
        assert body["suggestion"] == "Check the activity ID"

    @pytest.mark.asyncio
    async def test_value_error_formatted(self) -> None:
        @safe_tool_handler
        async def handler() -> list[TextContent]:
            raise ValueError("activity_id must be positive")

        result = await handler()
        assert len(result) == 1
        body = json.loads(result[0].text)
        assert "Invalid parameter" in body["error"]
        assert "activity_id must be positive" in body["error"]
        assert body["suggestion"] == "Check parameter names and types"

    @pytest.mark.asyncio
    async def test_key_error_formatted(self) -> None:
        @safe_tool_handler
        async def handler() -> list[TextContent]:
            raise KeyError("missing_key")

        result = await handler()
        assert len(result) == 1
        body = json.loads(result[0].text)
        assert "Invalid parameter" in body["error"]

    @pytest.mark.asyncio
    async def test_unknown_exception_no_traceback(self) -> None:
        @safe_tool_handler
        async def handler() -> list[TextContent]:
            raise RuntimeError("something broke internally")

        result = await handler()
        assert len(result) == 1
        body = json.loads(result[0].text)
        assert body["error"] == "Internal error occurred"
        assert body["suggestion"] == "Try again or check server logs"
        # Must not leak internal details
        assert "something broke" not in result[0].text

    @pytest.mark.asyncio
    async def test_decorator_preserves_function_name(self) -> None:
        @safe_tool_handler
        async def my_handler() -> list[TextContent]:
            return []

        assert my_handler.__name__ == "my_handler"
