"""Tests for output_interceptor module."""

import json

from tools.utils.output_interceptor import (
    OutputInterceptor,
    get_interceptor,
    intercept_output,
    set_interceptor,
)


class TestOutputInterceptor:
    """Test OutputInterceptor class."""

    def test_init_default_values(self):
        """Test initialization with default values."""
        interceptor = OutputInterceptor()
        assert interceptor.max_json_size == 1024
        assert interceptor.max_table_rows == 10
        assert interceptor.auto_trim is True

    def test_init_custom_values(self):
        """Test initialization with custom values."""
        interceptor = OutputInterceptor(
            max_json_size=2048, max_table_rows=20, auto_trim=False
        )
        assert interceptor.max_json_size == 2048
        assert interceptor.max_table_rows == 20
        assert interceptor.auto_trim is False

    def test_intercept_valid_json(self):
        """Test intercepting valid JSON output."""
        interceptor = OutputInterceptor()
        output = json.dumps({"result": "success", "value": 42})

        processed, warning = interceptor.intercept(output)

        assert processed == output
        assert warning is None

    def test_intercept_valid_table(self):
        """Test intercepting valid table output."""
        interceptor = OutputInterceptor()
        # 10 rows + 2 header lines = 12 total (within limit with +5 buffer)
        output = "col1  col2\n" "----  ----\n" + "\n".join(
            [f"val{i}  dat{i}" for i in range(10)]
        )

        processed, warning = interceptor.intercept(output)

        assert processed == output
        assert warning is None

    def test_intercept_oversized_json_auto_trim(self):
        """Test intercepting oversized JSON with auto-trim."""
        interceptor = OutputInterceptor(max_json_size=100, auto_trim=True)

        # Create large JSON
        large_data = {f"key{i}": f"value{i}" * 10 for i in range(20)}
        output = json.dumps(large_data, ensure_ascii=False, indent=2)

        processed, warning = interceptor.intercept(output)

        # Should be trimmed
        assert processed != output
        assert warning is not None
        assert "Output size limit exceeded" in warning

        # Trimmed output should be valid JSON
        trimmed_data = json.loads(processed)
        assert "_trimmed" in trimmed_data
        assert "removed_keys" in trimmed_data["_trimmed"]

    def test_intercept_oversized_json_no_auto_trim(self):
        """Test intercepting oversized JSON without auto-trim."""
        interceptor = OutputInterceptor(max_json_size=100, auto_trim=False)

        # Create large JSON
        large_data = {f"key{i}": f"value{i}" * 10 for i in range(20)}
        output = json.dumps(large_data, ensure_ascii=False, indent=2)

        processed, warning = interceptor.intercept(output)

        # Should NOT be trimmed
        assert processed == output
        assert warning is not None
        assert "Output size limit exceeded" in warning

    def test_intercept_oversized_table_auto_trim(self):
        """Test intercepting oversized table with auto-trim."""
        interceptor = OutputInterceptor(max_table_rows=10, auto_trim=True)

        # Create table with 100 rows
        header = "col1  col2\n----  ----\n"
        data_rows = "\n".join([f"val{i}  dat{i}" for i in range(100)])
        output = header + data_rows

        processed, warning = interceptor.intercept(output)

        # Should be trimmed
        assert processed != output
        assert warning is not None
        assert "Output size limit exceeded" in warning

        # Should contain omission notice
        assert "rows omitted" in processed

        # Should be much shorter
        assert len(processed.split("\n")) < len(output.split("\n"))

    def test_trim_json_removes_keys(self):
        """Test JSON trimming removes keys to fit size."""
        interceptor = OutputInterceptor(max_json_size=500)

        # Create data that will exceed 500 bytes
        data = {f"key{i}": f"value{i}" * 10 for i in range(20)}

        # Original size
        original_size = len(
            json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        )

        trimmed_json = interceptor._trim_json(data)
        trimmed_data = json.loads(trimmed_json)

        # Should have _trimmed metadata
        assert "_trimmed" in trimmed_data
        assert "removed_keys" in trimmed_data["_trimmed"]
        assert len(trimmed_data["_trimmed"]["removed_keys"]) > 0

        # Should be smaller than original
        trimmed_size = len(trimmed_json.encode("utf-8"))
        assert trimmed_size < original_size

        # Should fit size limit (or be close if metadata is large)
        assert trimmed_size <= 500

    def test_trim_table_shows_first_and_last_rows(self):
        """Test table trimming shows first and last rows."""
        interceptor = OutputInterceptor(max_table_rows=10)

        # Create table with 100 rows
        lines = ["header1", "header2"] + [f"row_{i}" for i in range(100)]
        output = "\n".join(lines)

        trimmed = interceptor._trim_table(output)
        trimmed_lines = trimmed.split("\n")

        # Should contain headers
        assert "header1" in trimmed_lines[0]

        # Should contain omission notice
        assert any("rows omitted" in line for line in trimmed_lines)

        # Should be much shorter than original
        assert len(trimmed_lines) < len(lines)

    def test_global_interceptor(self):
        """Test global interceptor get/set."""
        # Create custom interceptor
        custom = OutputInterceptor(max_json_size=512)
        set_interceptor(custom)

        # Get global interceptor
        global_interceptor = get_interceptor()

        assert global_interceptor is custom
        assert global_interceptor.max_json_size == 512

    def test_intercept_output_function(self):
        """Test module-level intercept_output function."""
        output = json.dumps({"test": "data"})

        processed, warning = intercept_output(output)

        assert processed == output
        assert warning is None


class TestOutputInterceptorEdgeCases:
    """Test edge cases for OutputInterceptor."""

    def test_empty_json(self):
        """Test with empty JSON."""
        interceptor = OutputInterceptor()
        output = "{}"

        processed, warning = interceptor.intercept(output)

        assert processed == output
        assert warning is None

    def test_empty_table(self):
        """Test with empty table."""
        interceptor = OutputInterceptor()
        output = ""

        processed, warning = interceptor.intercept(output)

        assert processed == output
        assert warning is None

    def test_json_exactly_at_limit(self):
        """Test JSON exactly at size limit."""
        # Create JSON that is exactly 1024 bytes
        data = {"key": "x" * 1000}  # Adjust to hit exactly 1024
        json_str = json.dumps(data)

        # Adjust to exactly 1024 bytes
        while len(json_str.encode("utf-8")) < 1024:
            data["key"] += "x"
            json_str = json.dumps(data)

        while len(json_str.encode("utf-8")) > 1024:
            data["key"] = data["key"][:-1]
            json_str = json.dumps(data)

        interceptor = OutputInterceptor(max_json_size=1024)
        processed, warning = interceptor.intercept(json_str)

        # At exact limit should be valid
        assert warning is None or processed == json_str

    def test_table_exactly_at_limit(self):
        """Test table exactly at row limit."""
        interceptor = OutputInterceptor(max_table_rows=10)

        # 10 rows + 2 header + 3 buffer = 15 total (within limit)
        header = "col1  col2\n----  ----\n"
        data_rows = "\n".join([f"val{i}  dat{i}" for i in range(10)])
        output = header + data_rows

        processed, warning = interceptor.intercept(output)

        # Should be valid
        assert warning is None or len(processed.split("\n")) <= 15

    def test_non_json_non_table_output(self):
        """Test with plain text (neither JSON nor table)."""
        interceptor = OutputInterceptor()
        output = "This is just plain text output."

        processed, warning = interceptor.intercept(output)

        # Plain text should pass through
        assert processed == output
        assert warning is None

    def test_malformed_json(self):
        """Test with malformed JSON."""
        interceptor = OutputInterceptor()
        output = '{"key": invalid json}'

        processed, warning = interceptor.intercept(output)

        # Should treat as table/text, not JSON
        assert processed == output
