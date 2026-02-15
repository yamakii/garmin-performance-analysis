"""
Standardized error handling for LLM-safe data operations.

This module provides consistent error messages and retry guidance for
size limit violations and data processing errors.
"""

import logging

logger = logging.getLogger(__name__)


class LLMSafeError(Exception):
    """Base class for LLM-safe operation errors."""

    def __init__(
        self,
        message: str,
        suggestion: str | None = None,
        retry_guidance: str | None = None,
    ):
        """
        Initialize LLMSafeError.

        Args:
            message: Error description
            suggestion: Suggested solution
            retry_guidance: How to retry with correct approach
        """
        self.message = message
        self.suggestion = suggestion
        self.retry_guidance = retry_guidance

        full_message = message
        if suggestion:
            full_message += f"\n💡 Suggestion: {suggestion}"
        if retry_guidance:
            full_message += f"\n🔄 Retry: {retry_guidance}"

        super().__init__(full_message)


class DataSizeError(LLMSafeError):
    """Raised when data size exceeds limits."""

    pass


class OutputSizeError(LLMSafeError):
    """Raised when output size exceeds limits."""

    pass


def format_size_error(current_size: int, max_size: int, data_type: str = "data") -> str:
    """
    Format size limit error message.

    Args:
        current_size: Actual size
        max_size: Maximum allowed size
        data_type: Type of data (e.g., "JSON", "table", "export")

    Returns:
        Formatted error message
    """
    return (
        f"{data_type.capitalize()} size limit exceeded: "
        f"{current_size:,} > {max_size:,}"
    )


def format_row_count_error(current_rows: int, max_rows: int) -> str:
    """
    Format row count error message.

    Args:
        current_rows: Actual row count
        max_rows: Maximum allowed rows

    Returns:
        Formatted error message
    """
    return f"Row count limit exceeded: " f"{current_rows:,} rows > {max_rows:,} rows"


def get_aggregation_suggestion(data_type: str) -> str:
    """
    Get aggregation suggestion for data type.

    Args:
        data_type: Type of data ("export", "json", "table")

    Returns:
        Suggestion text
    """
    suggestions = {
        "export": (
            "Add WHERE clause to filter data, " "or use GROUP BY for aggregation"
        ),
        "json": (
            "Remove unnecessary keys, "
            "or aggregate values (use mean/median instead of all values)"
        ),
        "table": (
            "Use safe_summary_table(df, max_rows=10) for display, "
            "or save full table to CSV"
        ),
    }

    return suggestions.get(
        data_type.lower(), "Reduce data size through filtering or aggregation"
    )


def get_retry_guidance(data_type: str) -> str:
    """
    Get retry guidance for data type.

    Args:
        data_type: Type of data ("export", "json", "table")

    Returns:
        Retry guidance text
    """
    guidance = {
        "export": (
            "Modify query: SELECT ... WHERE <condition> "
            "or SELECT AVG(...), COUNT(*) GROUP BY ..."
        ),
        "json": (
            "Call safe_json_output(reduced_data, max_size=1024) " "with fewer keys"
        ),
        "table": ("Call safe_summary_table(df, max_rows=10) " "instead of print(df)"),
    }

    return guidance.get(
        data_type.lower(), "Apply filtering or aggregation before retrying"
    )


def raise_export_size_error(current_rows: int, max_rows: int) -> None:
    """
    Raise standardized export size error.

    Args:
        current_rows: Actual row count
        max_rows: Maximum allowed rows

    Raises:
        DataSizeError: With standardized message and guidance
    """
    message = format_row_count_error(current_rows, max_rows)
    suggestion = get_aggregation_suggestion("export")
    retry_guidance = get_retry_guidance("export")

    error = DataSizeError(message)
    error.suggestion = suggestion
    error.retry_guidance = retry_guidance

    logger.error(f"{message}\n{suggestion}\n{retry_guidance}")
    raise error


def raise_json_size_error(current_size: int, max_size: int) -> None:
    """
    Raise standardized JSON size error.

    Args:
        current_size: Actual JSON size in bytes
        max_size: Maximum allowed size in bytes

    Raises:
        OutputSizeError: With standardized message and guidance
    """
    message = format_size_error(current_size, max_size, "JSON")
    suggestion = get_aggregation_suggestion("json")
    retry_guidance = get_retry_guidance("json")

    error = OutputSizeError(message)
    error.suggestion = suggestion
    error.retry_guidance = retry_guidance

    logger.error(f"{message}\n{suggestion}\n{retry_guidance}")
    raise error


def raise_table_size_error(current_rows: int, max_rows: int) -> None:
    """
    Raise standardized table size error.

    Args:
        current_rows: Actual row count
        max_rows: Maximum allowed rows

    Raises:
        OutputSizeError: With standardized message and guidance
    """
    message = format_row_count_error(current_rows, max_rows)
    suggestion = get_aggregation_suggestion("table")
    retry_guidance = get_retry_guidance("table")

    error = OutputSizeError(message)
    error.suggestion = suggestion
    error.retry_guidance = retry_guidance

    logger.error(f"{message}\n{suggestion}\n{retry_guidance}")
    raise error


def log_size_warning(current_size: int, max_size: int, data_type: str = "data") -> None:
    """
    Log size limit warning without raising error.

    Args:
        current_size: Actual size
        max_size: Maximum allowed size
        data_type: Type of data
    """
    message = format_size_error(current_size, max_size, data_type)
    logger.warning(f"⚠️ {message} - Auto-trimming applied")


def log_retry_suggestion(error: Exception, context: str | None = None) -> None:
    """
    Log retry suggestion for error.

    Args:
        error: Exception that occurred
        context: Optional context information
    """
    if hasattr(error, "suggestion") and hasattr(error, "retry_guidance"):
        logger.info(f"💡 {error.suggestion}\n" f"🔄 {error.retry_guidance}")
    else:
        logger.info(f"Error: {error}")

    if context:
        logger.info(f"Context: {context}")
