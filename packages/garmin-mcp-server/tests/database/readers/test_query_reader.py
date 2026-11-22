"""QueryReader: inline SELECTs on a sandboxed connection, and the catalog (#1604)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from garmin_mcp.database.connection import get_connection, get_write_connection
from garmin_mcp.database.readers.query import QueryReader

_IDS = (20760400001, 20760400002, 20760400003, 20760400004, 20760400005)


def _seed(db_path: Path, n: int) -> None:
    with get_write_connection(db_path) as conn:
        for i, activity_id in enumerate(_IDS[:n]):
            conn.execute(
                "INSERT INTO activities (activity_id, activity_date, activity_name) "
                "VALUES (?, ?, ?)",
                [activity_id, f"2026-11-{i + 1:02d}", f"run {i}"],
            )


def _activity_count(db_path: Path) -> int:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM activities").fetchone()
    assert row is not None
    return int(row[0])


@pytest.mark.integration
class TestRunInlineQuery:
    def test_run_inline_query_returns_rows(self, initialized_db_path: Path) -> None:
        _seed(initialized_db_path, 3)
        result = QueryReader(str(initialized_db_path)).run_inline_query(
            "SELECT activity_id FROM activities ORDER BY 1"
        )
        assert result["columns"] == ["activity_id"]
        assert result["row_count"] == 3
        assert result["rows"] == [[_IDS[0]], [_IDS[1]], [_IDS[2]]]
        assert result["truncated"] is False
        assert result["note"] is None

    def test_run_inline_query_truncates_at_max_rows(
        self, initialized_db_path: Path
    ) -> None:
        _seed(initialized_db_path, 5)
        result = QueryReader(str(initialized_db_path)).run_inline_query(
            "SELECT activity_id FROM activities ORDER BY 1", max_rows=2
        )
        assert result["row_count"] == 2
        assert result["truncated"] is True
        assert "2 rows" in result["note"]

    def test_run_inline_query_tolerates_trailing_semicolon(
        self, initialized_db_path: Path
    ) -> None:
        result = QueryReader(str(initialized_db_path)).run_inline_query(
            "SELECT 1 AS one;  "
        )
        assert result["rows"] == [[1]]

    def test_run_inline_query_cuts_long_cells(self, initialized_db_path: Path) -> None:
        result = QueryReader(str(initialized_db_path)).run_inline_query(
            "SELECT repeat('a', 2000) AS s"
        )
        cell = result["rows"][0][0]
        assert cell.startswith("a" * 400)
        assert len(cell) < 420
        assert "+1600" in cell

    def test_run_inline_query_serializes_dates_and_decimals(
        self, initialized_db_path: Path
    ) -> None:
        result = QueryReader(str(initialized_db_path)).run_inline_query(
            "SELECT DATE '2026-11-22' AS d, 1.5::DECIMAL(4,1) AS x, "
            "TIMESTAMP '2026-11-22 10:37:55' AS t"
        )
        assert result["rows"] == [["2026-11-22", 1.5, "2026-11-22T10:37:55"]]
        json.dumps(result)

    def test_run_inline_query_rejects_dml(self, initialized_db_path: Path) -> None:
        _seed(initialized_db_path, 2)
        result = QueryReader(str(initialized_db_path)).run_inline_query(
            "DELETE FROM activities"
        )
        assert "error" in result
        assert "get_db_catalog" in result["suggestion"]
        assert _activity_count(initialized_db_path) == 2

    def test_run_inline_query_rejects_copy(
        self, initialized_db_path: Path, tmp_path: Path
    ) -> None:
        target = tmp_path / "x.csv"
        result = QueryReader(str(initialized_db_path)).run_inline_query(
            f"COPY activities TO '{target}'"
        )
        assert "error" in result
        assert not target.exists()

    @pytest.mark.parametrize(
        "template",
        [
            "SELECT * FROM read_text('{path}')",
            "SELECT * FROM read_csv('{path}')",
            "SELECT * FROM '{path}'",
        ],
    )
    def test_run_inline_query_blocks_file_reads(
        self, initialized_db_path: Path, tmp_path: Path, template: str
    ) -> None:
        secret = tmp_path / "secret.csv"
        secret.write_text("a\n1\n")
        result = QueryReader(str(initialized_db_path)).run_inline_query(
            template.format(path=secret)
        )
        assert "error" in result

    def test_run_inline_query_leaves_other_connections_unrestricted(
        self, initialized_db_path: Path, tmp_path: Path
    ) -> None:
        """The sandbox setting must not leak into the shared file instance."""
        QueryReader(str(initialized_db_path)).run_inline_query("SELECT 1")
        target = tmp_path / "out.csv"
        with get_connection(initialized_db_path) as conn:
            conn.execute(f"COPY (SELECT 1 AS a) TO '{target}' (FORMAT CSV)")
        assert target.exists()


@pytest.mark.integration
class TestCatalog:
    def test_catalog_lists_domain_tables_with_purpose(
        self, initialized_db_path: Path
    ) -> None:
        _seed(initialized_db_path, 2)
        tables = QueryReader(str(initialized_db_path)).catalog()
        names = [t["table"] for t in tables]
        assert "schema_version" not in names
        assert "activities" in names and "daily_wellness" in names
        for entry in tables:
            assert entry["purpose"], entry["table"]
            assert isinstance(entry["row_count"], int)
        by_name = {t["table"]: t for t in tables}
        assert by_name["activities"]["row_count"] == 2

    def test_describe_table_returns_columns(self, initialized_db_path: Path) -> None:
        described = QueryReader(str(initialized_db_path)).describe_table("activities")
        assert described is not None
        assert described["table"] == "activities"
        assert described["purpose"]
        names = [c["name"] for c in described["columns"]]
        assert "activity_id" in names and "activity_date" in names
        assert all(c["type"] for c in described["columns"])

    def test_describe_table_unknown_returns_none(
        self, initialized_db_path: Path
    ) -> None:
        reader = QueryReader(str(initialized_db_path))
        assert reader.describe_table("no_such_table") is None
        assert reader.describe_table("schema_version") is None
