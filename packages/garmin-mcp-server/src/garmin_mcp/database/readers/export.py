"""
Export reader for saving query results to files.

Handles large dataset exports using DuckDB's COPY TO functionality.
"""

import logging
from pathlib import Path
from typing import Any, Literal

from garmin_mcp.database.readers.base import BaseDBReader

logger = logging.getLogger(__name__)


class ExportReader(BaseDBReader):
    """Reader for exporting query results to files."""

    def export_query_result(
        self,
        query: str,
        output_path: Path,
        export_format: Literal["parquet", "csv"] = "parquet",
        max_rows: int = 100000,
    ) -> dict[str, Any]:
        """Export query result to file using DuckDB COPY TO.

        Args:
            query: SQL query to execute
            output_path: Output file path
            export_format: Export format (parquet or csv)
            max_rows: Maximum rows to export (safety limit)

        Returns:
            Export metadata:
            {
                "rows": int,
                "columns": list[str],
                "size_mb": float
            }

        Raises:
            ValueError: If query returns more than max_rows
            Exception: If query execution fails
        """
        try:
            with self._get_connection() as conn:
                # First, check row count
                count_query = f"SELECT COUNT(*) FROM ({query}) AS subquery"
                count_result = conn.execute(count_query).fetchone()
                if count_result is None:
                    return {"rows": 0, "columns": [], "size_mb": 0.0}
                row_count = count_result[0]

                if row_count > max_rows:
                    raise ValueError(
                        f"Query result ({row_count} rows) exceeds max_rows ({max_rows}). "
                        f"Please refine your query with WHERE clauses or LIMIT."
                    )

                # Get column names
                sample_query = f"SELECT * FROM ({query}) AS subquery LIMIT 1"
                sample_result = conn.execute(sample_query).fetchone()
                if sample_result is None:
                    # Empty result
                    return {"rows": 0, "columns": [], "size_mb": 0.0}

                columns = [desc[0] for desc in conn.description]

                # Export using COPY TO
                if export_format == "parquet":
                    copy_query = f"COPY ({query}) TO '{output_path}' (FORMAT PARQUET)"
                else:  # csv
                    copy_query = (
                        f"COPY ({query}) TO '{output_path}' (FORMAT CSV, HEADER TRUE)"
                    )

                conn.execute(copy_query)

            # Get file size (after connection is closed)
            size_mb = output_path.stat().st_size / (1024 * 1024)

            return {
                "rows": row_count,
                "columns": columns,
                "size_mb": round(size_mb, 2),
            }

        except Exception as e:
            if isinstance(e, ValueError):
                raise
            logger.error(f"Error exporting query result: {e}")
            raise
