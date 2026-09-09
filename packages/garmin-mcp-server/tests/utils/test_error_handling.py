"""Tests for error_handling module."""

import pytest

from garmin_mcp.utils.error_handling import (
    DataSizeError,
    LLMSafeError,
    OutputSizeError,
    format_row_count_error,
    format_size_error,
    get_aggregation_suggestion,
    get_retry_guidance,
    log_retry_suggestion,
    log_size_warning,
    raise_export_size_error,
    raise_json_size_error,
    raise_table_size_error,
)


@pytest.mark.unit
class TestLLMSafeError:
    """Test LLMSafeError base class."""

    def test_init_message_only(self):
        """Test initialization with message only."""
        error = LLMSafeError("Something went wrong")

        assert str(error) == "Something went wrong"
        assert error.message == "Something went wrong"
        assert error.suggestion is None
        assert error.retry_guidance is None

    def test_init_with_suggestion(self):
        """Test initialization with suggestion."""
        error = LLMSafeError("Error occurred", suggestion="Try this instead")

        error_str = str(error)
        assert "Error occurred" in error_str
        assert "💡 Suggestion: Try this instead" in error_str
        assert error.suggestion == "Try this instead"

    def test_init_with_retry_guidance(self):
        """Test initialization with retry guidance."""
        error = LLMSafeError("Error occurred", retry_guidance="Retry with parameter X")

        error_str = str(error)
        assert "Error occurred" in error_str
        assert "🔄 Retry: Retry with parameter X" in error_str
        assert error.retry_guidance == "Retry with parameter X"

    def test_init_with_all_fields(self):
        """Test initialization with all fields."""
        error = LLMSafeError(
            "Error occurred",
            suggestion="Try this",
            retry_guidance="Retry like this",
        )

        error_str = str(error)
        assert "Error occurred" in error_str
        assert "💡 Suggestion: Try this" in error_str
        assert "🔄 Retry: Retry like this" in error_str


@pytest.mark.unit
class TestErrorFormatting:
    """Test error message formatting functions."""

    def test_format_size_error(self):
        """Test size error formatting."""
        message = format_size_error(2048, 1024, "JSON")

        assert "size limit exceeded" in message.lower()
        assert "json" in message.lower()
        assert "2,048" in message
        assert "1,024" in message

    def test_format_size_error_default_type(self):
        """Test size error formatting with default type."""
        message = format_size_error(5000, 1000)

        assert "Data size limit exceeded" in message
        assert "5,000" in message
        assert "1,000" in message

    def test_format_row_count_error(self):
        """Test row count error formatting."""
        message = format_row_count_error(100000, 10000)

        assert "Row count limit exceeded" in message
        assert "100,000 rows" in message
        assert "10,000 rows" in message


@pytest.mark.unit
class TestSuggestions:
    """Test suggestion and retry guidance functions."""

    def test_get_aggregation_suggestion_export(self):
        """Test aggregation suggestion for export."""
        suggestion = get_aggregation_suggestion("export")

        assert "WHERE clause" in suggestion
        assert "GROUP BY" in suggestion

    def test_get_aggregation_suggestion_json(self):
        """Test aggregation suggestion for JSON."""
        suggestion = get_aggregation_suggestion("json")

        assert "Remove unnecessary keys" in suggestion
        assert "aggregate" in suggestion

    def test_get_aggregation_suggestion_table(self):
        """Test aggregation suggestion for table."""
        suggestion = get_aggregation_suggestion("table")

        assert "safe_summary_table" in suggestion
        assert "max_rows=10" in suggestion

    def test_get_aggregation_suggestion_unknown(self):
        """Test aggregation suggestion for unknown type."""
        suggestion = get_aggregation_suggestion("unknown")

        assert "Reduce data size" in suggestion

    def test_get_retry_guidance_export(self):
        """Test retry guidance for export."""
        guidance = get_retry_guidance("export")

        assert "SELECT" in guidance
        assert "WHERE" in guidance or "GROUP BY" in guidance

    def test_get_retry_guidance_json(self):
        """Test retry guidance for JSON."""
        guidance = get_retry_guidance("json")

        assert "safe_json_output" in guidance
        assert "max_size" in guidance

    def test_get_retry_guidance_table(self):
        """Test retry guidance for table."""
        guidance = get_retry_guidance("table")

        assert "safe_summary_table" in guidance
        assert "max_rows" in guidance


@pytest.mark.unit
class TestRaiseErrors:
    """Test error raising functions."""

    def test_raise_export_size_error(self):
        """Test raising export size error."""
        with pytest.raises(DataSizeError) as exc_info:
            raise_export_size_error(100000, 10000)

        error = exc_info.value
        assert "100,000" in str(error)
        assert "10,000" in str(error)
        assert hasattr(error, "suggestion")
        assert hasattr(error, "retry_guidance")

    def test_raise_json_size_error(self):
        """Test raising JSON size error."""
        with pytest.raises(OutputSizeError) as exc_info:
            raise_json_size_error(2048, 1024)

        error = exc_info.value
        assert "2,048" in str(error)
        assert "1,024" in str(error)
        assert hasattr(error, "suggestion")
        assert hasattr(error, "retry_guidance")

    def test_raise_table_size_error(self):
        """Test raising table size error."""
        with pytest.raises(OutputSizeError) as exc_info:
            raise_table_size_error(100, 10)

        error = exc_info.value
        assert "100" in str(error)
        assert "10" in str(error)
        assert hasattr(error, "suggestion")
        assert hasattr(error, "retry_guidance")


@pytest.mark.unit
class TestLogging:
    """Test logging functions."""

    def test_log_size_warning(self, caplog):
        """Test size warning logging."""
        log_size_warning(2048, 1024, "JSON")

        assert "size limit exceeded" in caplog.text.lower()
        assert "json" in caplog.text.lower()
        assert "2,048" in caplog.text
        assert "1,024" in caplog.text
        assert "Auto-trimming" in caplog.text

    def test_log_retry_suggestion_with_attrs(self, caplog):
        """Test retry suggestion logging with error attributes."""
        import logging

        caplog.set_level(logging.INFO)

        error = LLMSafeError(
            "Test error", suggestion="Try this", retry_guidance="Retry like this"
        )

        log_retry_suggestion(error)

        assert "Try this" in caplog.text
        assert "Retry like this" in caplog.text
        assert "🔄 Retry like this" in caplog.text

    def test_log_retry_suggestion_without_attrs(self, caplog):
        """Test retry suggestion logging without error attributes."""
        import logging

        caplog.set_level(logging.INFO)

        error = ValueError("Standard error")

        log_retry_suggestion(error)

        assert "Standard error" in caplog.text

    def test_log_retry_suggestion_with_context(self, caplog):
        """Test retry suggestion logging with context."""
        import logging

        caplog.set_level(logging.INFO)

        error = ValueError("Test error")

        log_retry_suggestion(error, context="Processing activity 12345")

        assert "Test error" in caplog.text
        assert "Processing activity 12345" in caplog.text
        assert "Context: Processing activity 12345" in caplog.text


@pytest.mark.unit
class TestErrorAttributes:
    """Test that raised errors have correct attributes."""

    def test_export_error_attributes(self):
        """Test export error has suggestion and retry guidance."""
        try:
            raise_export_size_error(100000, 10000)
        except DataSizeError as e:
            assert e.suggestion is not None
            assert e.retry_guidance is not None
            assert "WHERE" in e.suggestion or "GROUP BY" in e.suggestion
            assert "SELECT" in e.retry_guidance

    def test_json_error_attributes(self):
        """Test JSON error has suggestion and retry guidance."""
        try:
            raise_json_size_error(2048, 1024)
        except OutputSizeError as e:
            assert e.suggestion is not None
            assert e.retry_guidance is not None
            assert "keys" in e.suggestion
            assert "safe_json_output" in e.retry_guidance

    def test_table_error_attributes(self):
        """Test table error has suggestion and retry guidance."""
        try:
            raise_table_size_error(100, 10)
        except OutputSizeError as e:
            assert e.suggestion is not None
            assert e.retry_guidance is not None
            assert "safe_summary_table" in e.suggestion
            assert "max_rows" in e.retry_guidance
