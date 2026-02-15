"""LLM-safe data handling utilities for controlled output sizes.

This module provides helper functions for loading, processing, and outputting
data in LLM execution environments with strict size limits to prevent context
expansion and token waste.

Design Principles:
- Data processing in Python/DuckDB, not LLM
- Size limits enforced (JSON: 1KB, Table: 10 rows, Load: 10,000 rows)
- Helpful error messages with reduction strategies
- Polars/Pandas compatibility
"""

import json
from pathlib import Path

import pandas as pd
import polars as pl

# Safety limits
MAX_JSON_SIZE = 1024  # 1KB
MAX_TABLE_ROWS = 10
MAX_LOAD_ROWS = 10000


def _to_polars(df: pl.DataFrame | pd.DataFrame) -> pl.DataFrame:
    """Convert Pandas DataFrame to Polars if needed.

    Args:
        df: Input DataFrame (Polars or Pandas)

    Returns:
        Polars DataFrame
    """
    if isinstance(df, pd.DataFrame):
        return pl.from_pandas(df)
    return df


def safe_load_export(handle: str, max_rows: int = MAX_LOAD_ROWS) -> pl.DataFrame:
    """Load exported Parquet/CSV with size limit.

    Args:
        handle: Path to Parquet or CSV file (from export() MCP function)
        max_rows: Maximum rows to load (default 10,000)

    Returns:
        Polars DataFrame

    Raises:
        DataSizeError: If file exceeds max_rows
        FileNotFoundError: If file doesn't exist

    Example:
        >>> handle = "/tmp/garmin_exports/export_xxx.parquet"
        >>> df = safe_load_export(handle)
        >>> print(len(df))  # Will error if > 10,000 rows
    """
    from garmin_mcp.utils.error_handling import raise_export_size_error

    path = Path(handle)

    if not path.exists():
        raise FileNotFoundError(f"Export file not found: {handle}")

    # Determine file type
    suffix = path.suffix.lower()

    if suffix == ".parquet":
        # Lazy load Parquet
        df = pl.scan_parquet(str(path))
    elif suffix == ".csv":
        # Lazy load CSV
        df = pl.scan_csv(str(path))
    else:
        raise ValueError(f"Unsupported file format: {suffix}. Use .parquet or .csv")

    # Check row count before collecting
    row_count = df.select(pl.len()).collect().item()

    if row_count > max_rows:
        raise_export_size_error(row_count, max_rows)

    return df.collect()


def safe_summary_table(
    df: pl.DataFrame | pd.DataFrame,
    max_rows: int = MAX_TABLE_ROWS,
    columns: list[str] | None = None,
) -> str:
    """Generate summary table with row limit.

    Args:
        df: Input DataFrame (Polars or Pandas)
        max_rows: Maximum rows to display (default 10)
        columns: Optional column subset

    Returns:
        Formatted table string (max 10 rows)

    Example:
        >>> df = pl.DataFrame({"a": range(100)})
        >>> table = safe_summary_table(df)
        >>> print(table)
        # Shows first 5 + last 5 rows with "... (90 rows omitted) ..."
    """
    # Convert to Polars for consistent handling
    df_polars = _to_polars(df)

    # Empty DataFrame
    if len(df_polars) == 0:
        return ""

    # Column subset
    if columns:
        df_polars = df_polars.select(columns)

    # Truncate if needed
    if len(df_polars) > max_rows:
        half = max_rows // 2
        df_head = df_polars.head(half)
        df_tail = df_polars.tail(max_rows - half)
        df_display = pl.concat([df_head, df_tail])

        # Convert to string
        table_str: str = df_display.to_pandas().to_string(index=False)
        omitted = len(df_polars) - max_rows
        table_str += f"\n... ({omitted:,} rows omitted) ..."
    else:
        table_str = df_polars.to_pandas().to_string(index=False)

    return table_str


def safe_json_output(data: dict, max_size: int = MAX_JSON_SIZE) -> str:
    """Generate JSON output with size limit.

    Args:
        data: Dictionary to serialize
        max_size: Maximum JSON size in bytes (default 1KB)

    Returns:
        JSON string

    Raises:
        OutputSizeError: If JSON exceeds max_size

    Example:
        >>> data = {"pace": 305.2, "hr": 162}
        >>> json_str = safe_json_output(data)
        >>> print(len(json_str.encode('utf-8')))  # Will error if > 1KB
    """
    from garmin_mcp.utils.error_handling import raise_json_size_error

    json_str = json.dumps(data, ensure_ascii=False, indent=2)
    byte_size = len(json_str.encode("utf-8"))

    if byte_size > max_size:
        raise_json_size_error(byte_size, max_size)

    return json_str


def validate_output(output: str) -> tuple[bool, str | None]:
    """Validate output against size limits.

    Args:
        output: Output string to validate (JSON or table)

    Returns:
        (is_valid, error_message)

    Example:
        >>> output = '{"a": 1}'
        >>> is_valid, error = validate_output(output)
        >>> assert is_valid
    """
    # Try to parse as JSON
    try:
        json.loads(output)
        # It's valid JSON, check size
        byte_size = len(output.encode("utf-8"))
        if byte_size > MAX_JSON_SIZE:
            return (
                False,
                f"JSON output exceeds limit: {byte_size:,} bytes > {MAX_JSON_SIZE:,} bytes",
            )
        return (True, None)
    except json.JSONDecodeError:
        pass  # Not JSON, check as table

    # Check as table (line count)
    lines = output.strip().split("\n")
    # Allow +5 lines for header/footer/separator
    if len(lines) > MAX_TABLE_ROWS + 5:
        return (
            False,
            f"Table output exceeds limit: {len(lines)} lines > {MAX_TABLE_ROWS + 5} lines",
        )

    return (True, None)
