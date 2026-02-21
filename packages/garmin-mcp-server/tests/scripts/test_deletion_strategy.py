"""Tests for regeneration deletion strategies.

Covers delete_activity_records and delete_table_all_records from
garmin_mcp.scripts.regenerate.deletion_strategy.
"""

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.scripts.regenerate.deletion_strategy import (
    delete_activity_records,
    delete_table_all_records,
)


@pytest.fixture
def db_with_data(tmp_path: Path) -> Path:
    """Create a small DuckDB with activities and splits tables."""
    db_path = tmp_path / "test.duckdb"
    conn = duckdb.connect(str(db_path))
    conn.execute(
        "CREATE TABLE activities (activity_id BIGINT PRIMARY KEY, activity_date DATE)"
    )
    conn.execute(
        "CREATE TABLE splits (activity_id BIGINT, split_index INTEGER, PRIMARY KEY (activity_id, split_index))"
    )
    conn.executemany(
        "INSERT INTO activities VALUES (?, ?)",
        [(1001, "2025-01-01"), (1002, "2025-01-02"), (1003, "2025-01-03")],
    )
    conn.executemany(
        "INSERT INTO splits VALUES (?, ?)",
        [(1001, 1), (1001, 2), (1002, 1), (1003, 1)],
    )
    conn.close()
    return db_path


def _count(db_path: Path, table: str) -> int:
    with duckdb.connect(str(db_path), read_only=True) as conn:
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        assert row is not None
        return int(row[0])


# ---------------------------------------------------------------------------
# delete_activity_records
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDeleteActivityRecords:
    """Tests for delete_activity_records()."""

    def test_deletes_specified_activity(self, db_with_data: Path):
        delete_activity_records([1001], ["splits"], db_with_data)
        assert _count(db_with_data, "splits") == 2  # 1002:1 + 1003:1

    def test_deletes_from_multiple_tables(self, db_with_data: Path):
        delete_activity_records([1001], ["activities", "splits"], db_with_data)
        assert _count(db_with_data, "activities") == 2
        assert _count(db_with_data, "splits") == 2

    def test_body_composition_skipped(self, db_with_data: Path):
        """body_composition should be silently skipped."""
        delete_activity_records([1001], ["body_composition", "splits"], db_with_data)
        assert _count(db_with_data, "splits") == 2

    def test_nonexistent_table_graceful(self, db_with_data: Path):
        """Non-existent table is skipped without error."""
        delete_activity_records([1001], ["nonexistent_table"], db_with_data)

    def test_rollback_on_error(self, db_with_data: Path):
        """Transaction rolls back on error, data preserved."""
        # Force error by closing underlying connection mechanism
        # We'll test that the function raises but doesn't corrupt
        original_count = _count(db_with_data, "splits")
        try:
            # Pass non-list to trigger error inside loop
            delete_activity_records([1001], ["splits", None], db_with_data)  # type: ignore[list-item]
        except Exception:
            pass
        # Data should still be intact (rollback)
        assert _count(db_with_data, "splits") == original_count


# ---------------------------------------------------------------------------
# delete_table_all_records
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDeleteTableAllRecords:
    """Tests for delete_table_all_records()."""

    def test_deletes_all_from_table(self, db_with_data: Path):
        delete_table_all_records(["splits"], db_with_data)
        assert _count(db_with_data, "splits") == 0

    def test_body_composition_skipped(self, db_with_data: Path):
        """body_composition-only list results in no deletion."""
        delete_table_all_records(["body_composition"], db_with_data)
        assert _count(db_with_data, "activities") == 3

    def test_nonexistent_table_graceful(self, db_with_data: Path):
        """CatalogException for missing table is handled gracefully."""
        delete_table_all_records(["nonexistent_table"], db_with_data)
