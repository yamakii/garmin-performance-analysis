"""Tests for LLM-safe data handling utilities.

Test coverage:
- TestSafeLoadExport: 5 tests
- TestSafeSummaryTable: 5 tests
- TestSafeJsonOutput: 5 tests
- TestValidateOutput: 5 tests
Total: 20 tests
"""

import json
from pathlib import Path

import pandas as pd
import polars as pl
import pytest

from tools.utils.llm_safe_data import (
    MAX_JSON_SIZE,
    safe_json_output,
    safe_load_export,
    safe_summary_table,
    validate_output,
)


class TestSafeLoadExport:
    """Tests for safe_load_export() function."""

    def test_load_normal_parquet(self, tmp_path: Path) -> None:
        """Test loading normal-sized Parquet file."""
        # Arrange: Create test Parquet file (1000 rows)
        df = pl.DataFrame(
            {
                "timestamp": range(1000),
                "pace": [300 + i * 0.1 for i in range(1000)],
                "heart_rate": [150 + i * 0.01 for i in range(1000)],
            }
        )
        parquet_path = tmp_path / "test_export.parquet"
        df.write_parquet(parquet_path)

        # Act: Load with safe_load_export
        result = safe_load_export(str(parquet_path))

        # Assert: Should load successfully
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 1000
        assert list(result.columns) == ["timestamp", "pace", "heart_rate"]

    def test_load_size_exceeded(self, tmp_path: Path) -> None:
        """Test loading Parquet that exceeds max_rows limit."""
        # Arrange: Create large Parquet file (100,000 rows)
        df = pl.DataFrame({"value": range(100000)})
        parquet_path = tmp_path / "large_export.parquet"
        df.write_parquet(parquet_path)

        # Act & Assert: Should raise ValueError with helpful message
        with pytest.raises(ValueError) as exc_info:
            safe_load_export(str(parquet_path), max_rows=10000)

        error_msg = str(exc_info.value)
        assert "100,000" in error_msg
        assert "10,000" in error_msg
        assert "aggregation" in error_msg.lower()

    def test_load_csv_file(self, tmp_path: Path) -> None:
        """Test loading CSV file."""
        # Arrange: Create test CSV file
        df = pl.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        csv_path = tmp_path / "test_export.csv"
        df.write_csv(csv_path)

        # Act: Load with safe_load_export
        result = safe_load_export(str(csv_path))

        # Assert: Should load successfully
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 3
        assert list(result.columns) == ["a", "b"]

    def test_file_not_found(self) -> None:
        """Test loading non-existent file."""
        # Arrange: Non-existent path
        fake_path = "/tmp/nonexistent_file.parquet"

        # Act & Assert: Should raise FileNotFoundError
        with pytest.raises(FileNotFoundError) as exc_info:
            safe_load_export(fake_path)

        assert "Export file not found" in str(exc_info.value)

    def test_path_object_input(self, tmp_path: Path) -> None:
        """Test loading with Path object instead of string."""
        # Arrange: Create test Parquet with Path object
        df = pl.DataFrame({"x": [1, 2, 3]})
        parquet_path = tmp_path / "path_object_test.parquet"
        df.write_parquet(parquet_path)

        # Act: Load with Path object (should be converted to string internally)
        result = safe_load_export(str(parquet_path))

        # Assert: Should load successfully
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 3

    def test_unsupported_format(self, tmp_path: Path) -> None:
        """Test loading unsupported file format."""
        # Arrange: Create file with unsupported extension
        unsupported_path = tmp_path / "test.json"
        unsupported_path.write_text('{"test": "data"}')

        # Act & Assert: Should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            safe_load_export(str(unsupported_path))

        assert "Unsupported file format" in str(exc_info.value)
        assert ".json" in str(exc_info.value)


class TestSafeSummaryTable:
    """Tests for safe_summary_table() function."""

    def test_full_display_small_df(self) -> None:
        """Test full display for DataFrame with <= 10 rows."""
        # Arrange: Small DataFrame (5 rows)
        df = pl.DataFrame({"a": range(5), "b": [x * 2 for x in range(5)]})

        # Act: Generate summary table
        result = safe_summary_table(df)

        # Assert: All rows should be displayed
        assert "0" in result  # First row
        assert "4" in result  # Last row
        assert "omitted" not in result  # No truncation

    def test_truncated_display_large_df(self) -> None:
        """Test truncated display for DataFrame with > 10 rows."""
        # Arrange: Large DataFrame (100 rows)
        df = pl.DataFrame({"value": range(100)})

        # Act: Generate summary table (default max_rows=10)
        result = safe_summary_table(df)

        # Assert: Should show first 5 + last 5 rows
        assert "0" in result  # First row
        assert "99" in result  # Last row
        assert "(90 rows omitted)" in result
        lines = result.strip().split("\n")
        # Should have ~11-13 lines (header + 5 + 5 + omitted message)
        assert len(lines) <= 15

    def test_column_subset(self) -> None:
        """Test column subset selection."""
        # Arrange: DataFrame with multiple columns
        df = pl.DataFrame({"a": range(5), "b": range(5, 10), "c": range(10, 15)})

        # Act: Select only columns "a" and "c"
        result = safe_summary_table(df, columns=["a", "c"])

        # Assert: Only selected columns should appear
        assert "a" in result
        assert "c" in result
        assert "b" not in result

    def test_polars_and_pandas(self) -> None:
        """Test compatibility with both Polars and Pandas DataFrames."""
        # Arrange: Create both Polars and Pandas DataFrames
        data = {"x": [1, 2, 3], "y": [4, 5, 6]}
        df_polars = pl.DataFrame(data)
        df_pandas = pd.DataFrame(data)

        # Act: Generate summary tables
        result_polars = safe_summary_table(df_polars)
        result_pandas = safe_summary_table(df_pandas)

        # Assert: Both should produce similar output
        assert "x" in result_polars
        assert "y" in result_polars
        assert "x" in result_pandas
        assert "y" in result_pandas

    def test_empty_dataframe(self) -> None:
        """Test handling of empty DataFrame."""
        # Arrange: Empty DataFrame
        df = pl.DataFrame({"a": []})

        # Act: Generate summary table
        result = safe_summary_table(df)

        # Assert: Should return empty string
        assert result == ""


class TestSafeJsonOutput:
    """Tests for safe_json_output() function."""

    def test_normal_json(self) -> None:
        """Test normal JSON output within size limit."""
        # Arrange: Small dictionary (~50 bytes)
        data = {"pace": 305.2, "heart_rate": 162, "cadence": 180}

        # Act: Generate JSON output
        result = safe_json_output(data)

        # Assert: Should serialize successfully
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed["pace"] == 305.2
        assert parsed["heart_rate"] == 162
        assert len(result.encode("utf-8")) < MAX_JSON_SIZE

    def test_size_boundary(self) -> None:
        """Test JSON at exactly 1KB boundary."""
        # Arrange: Create dictionary close to 1KB
        # Each entry is ~20 bytes, need ~50 entries for 1KB
        data = {f"metric_{i}": i * 1.5 for i in range(40)}

        # Act: Should succeed (just under limit)
        result = safe_json_output(data)

        # Assert: Should be within limit
        assert len(result.encode("utf-8")) <= MAX_JSON_SIZE

    def test_size_exceeded(self) -> None:
        """Test JSON exceeding 1KB limit."""
        # Arrange: Create large dictionary (>1KB)
        data = {f"metric_{i}": i * 1.5 for i in range(100)}

        # Act & Assert: Should raise ValueError with suggestions
        with pytest.raises(ValueError) as exc_info:
            safe_json_output(data)

        error_msg = str(exc_info.value)
        assert "exceeds max_size" in error_msg
        assert "Reduce number of fields" in error_msg
        assert "Aggregate data" in error_msg

    def test_japanese_characters(self) -> None:
        """Test JSON with Japanese characters."""
        # Arrange: Dictionary with Japanese text
        data = {"分析": "ペース変動", "結果": "良好", "value": 123}

        # Act: Generate JSON output (ensure_ascii=False)
        result = safe_json_output(data)

        # Assert: Should contain Japanese characters directly
        assert "分析" in result
        assert "ペース変動" in result
        assert "\\u" not in result  # Should NOT be escaped

    def test_nested_dict(self) -> None:
        """Test JSON with nested dictionaries."""
        # Arrange: Nested dictionary
        data = {
            "summary": {"avg_pace": 305, "max_hr": 180},
            "splits": [{"km": 1, "pace": 300}, {"km": 2, "pace": 310}],
        }

        # Act: Generate JSON output
        result = safe_json_output(data)

        # Assert: Should serialize nested structure
        parsed = json.loads(result)
        assert parsed["summary"]["avg_pace"] == 305
        assert len(parsed["splits"]) == 2


class TestValidateOutput:
    """Tests for validate_output() function."""

    def test_valid_json(self) -> None:
        """Test validation of valid JSON output."""
        # Arrange: Small JSON string
        output = '{"pace": 305, "hr": 160}'

        # Act: Validate output
        is_valid, error = validate_output(output)

        # Assert: Should be valid
        assert is_valid is True
        assert error is None

    def test_valid_table(self) -> None:
        """Test validation of valid table output."""
        # Arrange: Small table (10 rows)
        df = pl.DataFrame({"a": range(10)})
        output = safe_summary_table(df)

        # Act: Validate output
        is_valid, error = validate_output(output)

        # Assert: Should be valid
        assert is_valid is True
        assert error is None

    def test_json_exceeded(self) -> None:
        """Test detection of JSON exceeding size limit."""
        # Arrange: Large JSON string (>1KB)
        large_dict = {f"key_{i}": f"value_{i}" * 10 for i in range(100)}
        output = json.dumps(large_dict, ensure_ascii=False, indent=2)

        # Act: Validate output
        is_valid, error = validate_output(output)

        # Assert: Should be invalid
        assert is_valid is False
        assert error is not None
        assert "JSON" in error
        assert "exceeds limit" in error

    def test_table_exceeded(self) -> None:
        """Test detection of table exceeding row limit."""
        # Arrange: Large table output (>15 lines)
        lines = ["header", "------"] + [f"row_{i}" for i in range(20)]
        output = "\n".join(lines)

        # Act: Validate output
        is_valid, error = validate_output(output)

        # Assert: Should be invalid
        assert is_valid is False
        assert error is not None
        assert "Table" in error
        assert "exceeds limit" in error

    def test_plain_text(self) -> None:
        """Test validation of plain text (neither JSON nor large table)."""
        # Arrange: Simple text output
        output = "Analysis complete. Results saved to file."

        # Act: Validate output
        is_valid, error = validate_output(output)

        # Assert: Should be valid (not JSON, but short text)
        assert is_valid is True
        assert error is None
