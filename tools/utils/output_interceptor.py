"""
Output Interceptor for automatic validation and trimming of LLM outputs.

This module provides functionality to intercept and validate outputs from Python
code execution, ensuring they adhere to size limits and preventing context bloat.
"""

import json
import logging
from typing import Any

from tools.utils.llm_safe_data import MAX_JSON_SIZE, MAX_TABLE_ROWS, validate_output

logger = logging.getLogger(__name__)


class OutputInterceptor:
    """
    Intercepts and validates Python execution outputs.

    Automatically trims outputs that exceed size limits and provides
    warning messages for LLM consumption.
    """

    def __init__(
        self,
        max_json_size: int = MAX_JSON_SIZE,
        max_table_rows: int = MAX_TABLE_ROWS,
        auto_trim: bool = True,
    ):
        """
        Initialize OutputInterceptor.

        Args:
            max_json_size: Maximum JSON output size in bytes (default: 1KB)
            max_table_rows: Maximum table rows to display (default: 10)
            auto_trim: Whether to auto-trim oversized outputs (default: True)
        """
        self.max_json_size = max_json_size
        self.max_table_rows = max_table_rows
        self.auto_trim = auto_trim

    def intercept(self, output: str) -> tuple[str, str | None]:
        """
        Intercept and validate output.

        Args:
            output: Output string to validate

        Returns:
            (processed_output, warning_message)
            - If valid: (original_output, None)
            - If invalid and auto_trim: (trimmed_output, warning)
            - If invalid and not auto_trim: (original_output, warning)
        """
        is_valid, error_msg = validate_output(output)

        if is_valid:
            return output, None

        # Output exceeds limits
        warning = f"⚠️ Output size limit exceeded: {error_msg}"

        if not self.auto_trim:
            logger.warning(warning)
            return output, warning

        # Auto-trim output
        trimmed_output = self._trim_output(output)
        logger.warning(f"{warning} - Auto-trimmed to fit limits")

        return trimmed_output, warning

    def _trim_output(self, output: str) -> str:
        """
        Trim output to fit size limits.

        Args:
            output: Output string to trim

        Returns:
            Trimmed output string
        """
        # Try to parse as JSON
        try:
            data = json.loads(output)
            return self._trim_json(data)
        except json.JSONDecodeError:
            # Not JSON, treat as table
            return self._trim_table(output)

    def _trim_json(self, data: dict[str, Any]) -> str:
        """
        Trim JSON output to fit size limit.

        Args:
            data: Dictionary to trim

        Returns:
            Trimmed JSON string
        """
        # Strategy: Remove keys until size is acceptable
        # Make a copy to avoid mutating the original
        trimmed_data = dict(data)
        keys_to_remove: list[str] = []

        # Add _trimmed metadata structure upfront to account for its size
        trimmed_metadata = {
            "reason": "Output exceeded size limit",
            "removed_keys": [],
            "suggestion": "Use aggregation or reduce output data",
        }

        # Remove keys one by one until we fit
        for key in list(trimmed_data.keys()):
            # Try with current state + metadata
            test_data = dict(trimmed_data)
            if keys_to_remove:
                trimmed_metadata["removed_keys"] = keys_to_remove
                test_data["_trimmed"] = trimmed_metadata

            json_str = json.dumps(test_data, ensure_ascii=False, indent=2)
            if len(json_str.encode("utf-8")) <= self.max_json_size:
                # Fits! Use this version
                if keys_to_remove:
                    trimmed_data["_trimmed"] = trimmed_metadata
                return json.dumps(trimmed_data, ensure_ascii=False, indent=2)

            # Still too big, remove this key
            keys_to_remove.append(key)
            del trimmed_data[key]

        # Even after removing all keys, still add metadata
        if keys_to_remove:
            trimmed_metadata["removed_keys"] = keys_to_remove
            trimmed_data["_trimmed"] = trimmed_metadata

        return json.dumps(trimmed_data, ensure_ascii=False, indent=2)

    def _trim_table(self, output: str) -> str:
        """
        Trim table output to fit row limit.

        Args:
            output: Table string to trim

        Returns:
            Trimmed table string
        """
        lines = output.strip().split("\n")

        if len(lines) <= self.max_table_rows + 5:  # +5 for header/footer
            return output

        # Extract header (first 2 lines usually)
        header_lines = lines[:2]

        # Get first and last few data rows
        half_rows = self.max_table_rows // 2
        first_rows = lines[2 : 2 + half_rows]
        last_rows = lines[-(half_rows):]

        # Combine with omission notice
        total_omitted = (
            len(lines) - len(header_lines) - len(first_rows) - len(last_rows)
        )

        trimmed_lines = (
            header_lines
            + first_rows
            + [f"... ({total_omitted} rows omitted) ..."]
            + last_rows
        )

        return "\n".join(trimmed_lines)


# Global interceptor instance
_global_interceptor: OutputInterceptor | None = None


def get_interceptor() -> OutputInterceptor:
    """
    Get global OutputInterceptor instance.

    Returns:
        Global OutputInterceptor
    """
    global _global_interceptor

    if _global_interceptor is None:
        _global_interceptor = OutputInterceptor()

    return _global_interceptor


def set_interceptor(interceptor: OutputInterceptor) -> None:
    """
    Set global OutputInterceptor instance.

    Args:
        interceptor: OutputInterceptor to use globally
    """
    global _global_interceptor
    _global_interceptor = interceptor


def intercept_output(output: str) -> tuple[str, str | None]:
    """
    Intercept and validate output using global interceptor.

    Args:
        output: Output string to validate

    Returns:
        (processed_output, warning_message)
    """
    return get_interceptor().intercept(output)
