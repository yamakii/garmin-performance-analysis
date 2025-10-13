"""
Unit tests for DuckDB regeneration script.

Tests for table filtering, validation, and selective deletion features.
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

    def test_filter_tables_single_table_adds_activities(self):
        """Test that single table automatically adds activities table."""
        regenerator = DuckDBRegenerator()

        result = regenerator.filter_tables(["splits"])

        assert "activities" in result
        assert "splits" in result
        assert len(result) == 2
        assert result == ["activities", "splits"]

    def test_filter_tables_multiple_tables_adds_activities(self):
        """Test that multiple tables automatically add activities table."""
        regenerator = DuckDBRegenerator()

        result = regenerator.filter_tables(["splits", "form_efficiency"])

        assert "activities" in result
        assert "splits" in result
        assert "form_efficiency" in result
        assert len(result) == 3
        assert result == ["activities", "splits", "form_efficiency"]

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

    def test_filter_tables_already_includes_activities(self):
        """Test that activities is not duplicated if already in list."""
        regenerator = DuckDBRegenerator()

        result = regenerator.filter_tables(["activities", "splits"])

        assert result.count("activities") == 1
        assert "splits" in result
        assert len(result) == 2


class TestValidateArguments:
    """Test CLI argument validation."""

    def test_init_with_delete_db_and_tables_raises_error(self):
        """Test that --delete-db and --tables are mutually exclusive."""
        with pytest.raises(ValueError) as exc_info:
            DuckDBRegenerator(delete_old_db=True, tables=["splits"])

        assert "--delete-db cannot be used with --tables" in str(exc_info.value)
        assert "Use --force to delete existing records" in str(exc_info.value)

    def test_init_with_force_without_tables_raises_error(self):
        """Test that --force requires --tables."""
        with pytest.raises(ValueError) as exc_info:
            DuckDBRegenerator(force=True, tables=None)

        assert "--force requires --tables" in str(exc_info.value)

    def test_init_with_delete_db_no_tables_succeeds(self):
        """Test that --delete-db alone is valid (full regeneration)."""
        # Should not raise
        regenerator = DuckDBRegenerator(delete_old_db=True, tables=None)
        assert regenerator.delete_old_db is True
        assert regenerator.tables is None

    def test_init_with_tables_and_force_succeeds(self):
        """Test that --tables and --force together is valid."""
        # Should not raise
        regenerator = DuckDBRegenerator(tables=["splits"], force=True)
        assert regenerator.tables == ["splits"]
        assert regenerator.force is True

    def test_init_with_tables_no_force_succeeds(self):
        """Test that --tables alone is valid."""
        # Should not raise
        regenerator = DuckDBRegenerator(tables=["splits"], force=False)
        assert regenerator.tables == ["splits"]
        assert regenerator.force is False


class TestTablesParameter:
    """Test that tables parameter is stored correctly."""

    def test_init_stores_tables_parameter(self):
        """Test that tables parameter is stored in instance."""
        tables = ["splits", "form_efficiency"]
        regenerator = DuckDBRegenerator(tables=tables)

        assert regenerator.tables == tables

    def test_init_stores_force_parameter(self):
        """Test that force parameter is stored in instance."""
        regenerator = DuckDBRegenerator(tables=["splits"], force=True)

        assert regenerator.force is True

    def test_init_default_force_is_false(self):
        """Test that force defaults to False."""
        regenerator = DuckDBRegenerator(tables=["splits"])

        assert regenerator.force is False

    def test_init_default_tables_is_none(self):
        """Test that tables defaults to None (all tables)."""
        regenerator = DuckDBRegenerator()

        assert regenerator.tables is None
