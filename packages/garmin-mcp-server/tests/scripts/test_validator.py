"""Tests for regeneration validator.

Covers filter_tables, validate_table_dependencies, and _find_missing_activity_ids
from garmin_mcp.scripts.regenerate.validator.
"""

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.scripts.regenerate.validator import (
    AVAILABLE_TABLES,
    _find_missing_activity_ids,
    filter_tables,
    validate_table_dependencies,
)

# ---------------------------------------------------------------------------
# filter_tables
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFilterTables:
    """Tests for filter_tables()."""

    def test_none_returns_all(self):
        result = filter_tables(None)
        assert result == list(AVAILABLE_TABLES)

    def test_valid_subset(self):
        result = filter_tables(["splits", "activities"])
        assert result == ["splits", "activities"]

    def test_invalid_table_raises(self):
        with pytest.raises(ValueError, match="Invalid table names"):
            filter_tables(["splits", "nonexistent_table"])

    def test_all_valid_tables_accepted(self):
        result = filter_tables(list(AVAILABLE_TABLES))
        assert result == list(AVAILABLE_TABLES)

    def test_empty_list(self):
        result = filter_tables([])
        assert result == []


# ---------------------------------------------------------------------------
# validate_table_dependencies
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateTableDependencies:
    """Tests for validate_table_dependencies()."""

    def test_none_tables_skips_validation(self, tmp_path: Path):
        """Full regeneration (tables=None) skips validation."""
        db_path = tmp_path / "test.duckdb"
        duckdb.connect(str(db_path)).close()
        # Should not raise even with non-existent activity IDs
        validate_table_dependencies(None, [99999], db_path)

    def test_activities_included_skips_validation(self, tmp_path: Path):
        """activities in tables list skips parent check."""
        db_path = tmp_path / "test.duckdb"
        duckdb.connect(str(db_path)).close()
        validate_table_dependencies(["activities", "splits"], [99999], db_path)

    def test_child_only_with_existing_parent(self, tmp_path: Path):
        """Child tables with existing parent activities passes."""
        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute(
            "CREATE TABLE activities (activity_id BIGINT PRIMARY KEY, activity_date DATE)"
        )
        conn.execute("INSERT INTO activities VALUES (1001, '2025-01-01')")
        conn.close()
        validate_table_dependencies(["splits"], [1001], db_path)

    def test_child_only_missing_parent_raises(self, tmp_path: Path):
        """Child tables without parent activities raises ValueError."""
        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute(
            "CREATE TABLE activities (activity_id BIGINT PRIMARY KEY, activity_date DATE)"
        )
        conn.close()
        with pytest.raises(ValueError, match="Missing activity IDs"):
            validate_table_dependencies(["splits"], [99999], db_path)

    def test_partial_missing_raises(self, tmp_path: Path):
        """Some activity IDs missing raises ValueError."""
        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute(
            "CREATE TABLE activities (activity_id BIGINT PRIMARY KEY, activity_date DATE)"
        )
        conn.execute("INSERT INTO activities VALUES (1001, '2025-01-01')")
        conn.close()
        with pytest.raises(ValueError, match="Missing activity IDs"):
            validate_table_dependencies(["splits"], [1001, 99999], db_path)


# ---------------------------------------------------------------------------
# _find_missing_activity_ids
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFindMissingActivityIds:
    """Tests for _find_missing_activity_ids()."""

    def test_all_exist(self, tmp_path: Path):
        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute(
            "CREATE TABLE activities (activity_id BIGINT PRIMARY KEY, activity_date DATE)"
        )
        conn.executemany(
            "INSERT INTO activities VALUES (?, ?)",
            [(1001, "2025-01-01"), (1002, "2025-01-02")],
        )
        conn.close()
        assert _find_missing_activity_ids([1001, 1002], db_path) == []

    def test_some_missing(self, tmp_path: Path):
        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute(
            "CREATE TABLE activities (activity_id BIGINT PRIMARY KEY, activity_date DATE)"
        )
        conn.execute("INSERT INTO activities VALUES (1001, '2025-01-01')")
        conn.close()
        assert _find_missing_activity_ids([1001, 9999], db_path) == [9999]

    def test_db_not_exists(self, tmp_path: Path):
        """Non-existent DB returns all IDs as missing."""
        db_path = tmp_path / "nonexistent.duckdb"
        result = _find_missing_activity_ids([1001, 1002], db_path)
        assert result == [1001, 1002]

    def test_no_activities_table(self, tmp_path: Path):
        """DB without activities table returns all as missing (CatalogException)."""
        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute("CREATE TABLE other (x INT)")
        conn.close()
        result = _find_missing_activity_ids([1001], db_path)
        assert result == [1001]
