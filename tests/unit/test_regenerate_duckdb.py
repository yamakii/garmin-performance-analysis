"""
Unit tests for DuckDB regeneration script.

Tests for table filtering, validation, and selective deletion features.
Phase 1: Core Infrastructure (Table Filtering & Validation)
"""

import pytest

from tools.scripts.regenerate_duckdb import DuckDBRegenerator


class TestFilterTables:
    """Test filter_tables method for table validation and filtering."""

    def test_filter_tables_none_returns_all(self):
        """Test that None returns all 11 tables."""
        regenerator = DuckDBRegenerator()

        result = regenerator.filter_tables(None)

        expected = [
            "activities",
            "splits",
            "form_efficiency",
            "hr_efficiency",
            "heart_rate_zones",
            "performance_trends",
            "vo2_max",
            "lactate_threshold",
            "time_series_metrics",
            "section_analyses",
            "body_composition",
        ]
        assert result == expected
        assert len(result) == 11

    def test_filter_tables_single_table_no_auto_add(self):
        """Test that single table does NOT automatically add activities table."""
        regenerator = DuckDBRegenerator()

        result = regenerator.filter_tables(["splits"])

        # Phase 1 change: NO auto-add activities
        assert result == ["splits"]
        assert "activities" not in result
        assert len(result) == 1

    def test_filter_tables_multiple_tables_no_auto_add(self):
        """Test that multiple tables do NOT automatically add activities table."""
        regenerator = DuckDBRegenerator()

        result = regenerator.filter_tables(["splits", "form_efficiency"])

        # Phase 1 change: NO auto-add activities
        assert result == ["splits", "form_efficiency"]
        assert "activities" not in result
        assert len(result) == 2

    def test_filter_tables_body_composition_only_no_activities(self):
        """Test that body_composition alone does NOT add activities table."""
        regenerator = DuckDBRegenerator()

        result = regenerator.filter_tables(["body_composition"])

        assert result == ["body_composition"]
        assert "activities" not in result
        assert len(result) == 1

    def test_filter_tables_invalid_table_name_raises_error(self):
        """Test that invalid table name raises ValueError."""
        regenerator = DuckDBRegenerator()

        with pytest.raises(ValueError) as exc_info:
            regenerator.filter_tables(["invalid_table"])

        assert "Invalid table names" in str(exc_info.value)
        assert "invalid_table" in str(exc_info.value)

    def test_filter_tables_mixed_valid_invalid_raises_error(self):
        """Test that mix of valid and invalid tables raises ValueError."""
        regenerator = DuckDBRegenerator()

        with pytest.raises(ValueError) as exc_info:
            regenerator.filter_tables(["splits", "invalid_table", "wrong_table"])

        assert "Invalid table names" in str(exc_info.value)
        # Should include both invalid names
        assert "invalid_table" in str(exc_info.value)
        assert "wrong_table" in str(exc_info.value)

    def test_filter_tables_with_activities_explicit(self):
        """Test that activities can be explicitly included without duplication."""
        regenerator = DuckDBRegenerator()

        result = regenerator.filter_tables(["activities", "splits"])

        # Should preserve order and not duplicate
        assert result == ["activities", "splits"]
        assert result.count("activities") == 1
        assert len(result) == 2


class TestValidateArguments:
    """Test CLI argument validation."""

    def test_init_with_delete_db_and_tables_raises_error(self):
        """Test that --delete-db and --tables are mutually exclusive."""
        with pytest.raises(ValueError) as exc_info:
            DuckDBRegenerator(delete_old_db=True, tables=["splits"])

        assert "--delete-db cannot be used with --tables" in str(exc_info.value)
        # Phase 1 change: No mention of --force
        assert "Database file deletion is only allowed for full regeneration" in str(
            exc_info.value
        )

    def test_init_without_force_parameter(self):
        """Test that __init__ works without force parameter (Phase 1)."""
        # Phase 1: force parameter removed
        regenerator = DuckDBRegenerator(tables=["splits"])

        # Should not have force attribute
        assert not hasattr(regenerator, "force")
        assert regenerator.tables == ["splits"]

    def test_init_with_delete_db_no_tables_succeeds(self):
        """Test that --delete-db alone is valid (full regeneration)."""
        # Should not raise
        regenerator = DuckDBRegenerator(delete_old_db=True, tables=None)
        assert regenerator.delete_old_db is True
        assert regenerator.tables is None

    def test_init_with_tables_succeeds(self):
        """Test that --tables alone is valid (Phase 1)."""
        # Phase 1: force parameter removed
        regenerator = DuckDBRegenerator(tables=["splits"])

        assert regenerator.tables == ["splits"]
        # force parameter no longer exists
        assert not hasattr(regenerator, "force")

    def test_init_stores_tables_parameter(self):
        """Test that tables parameter is stored in instance."""
        tables = ["splits", "form_efficiency"]
        regenerator = DuckDBRegenerator(tables=tables)

        assert regenerator.tables == tables

    def test_init_default_tables_is_none(self):
        """Test that tables defaults to None (all tables)."""
        regenerator = DuckDBRegenerator()

        assert regenerator.tables is None


# Phase 2 tests (deletion logic) will be added later
