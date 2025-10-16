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


class TestDeleteActivityRecords:
    """Test delete_activity_records method (Phase 2: Deletion Logic Fix)."""

    def test_delete_activity_records_includes_activities(self, tmp_path, mocker):
        """Test that activities table is NOT skipped in delete_activity_records."""
        # Create mock DuckDB connection (context manager support)
        mock_conn = mocker.MagicMock()
        mock_cursor = mocker.MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = mocker.MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = mocker.MagicMock(return_value=False)
        mocker.patch(
            "tools.scripts.regenerate_duckdb.duckdb.connect", return_value=mock_conn
        )

        # Create regenerator with activities in tables
        db_path = tmp_path / "test.db"
        regenerator = DuckDBRegenerator(
            db_path=db_path, tables=["activities", "splits"]
        )

        # Call delete_activity_records
        regenerator.delete_activity_records([12345, 67890])

        # Phase 5: Verify activities table was NOT skipped (uses conn.execute not cursor)
        execute_calls = mock_conn.execute.call_args_list
        executed_sqls = [call[0][0] for call in execute_calls]

        # Should have DELETE for both activities and splits
        activities_deletes = [
            sql for sql in executed_sqls if "DELETE FROM activities" in sql
        ]
        splits_deletes = [sql for sql in executed_sqls if "DELETE FROM splits" in sql]

        assert len(activities_deletes) == 1, "activities table should be deleted"
        assert len(splits_deletes) == 1, "splits table should be deleted"

    def test_delete_activity_records_skips_body_composition(self, tmp_path, mocker):
        """Test that body_composition is skipped (no activity_id column)."""
        mock_conn = mocker.MagicMock()
        mock_conn.__enter__ = mocker.MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = mocker.MagicMock(return_value=False)
        mocker.patch(
            "tools.scripts.regenerate_duckdb.duckdb.connect", return_value=mock_conn
        )

        db_path = tmp_path / "test.db"
        regenerator = DuckDBRegenerator(
            db_path=db_path, tables=["body_composition", "splits"]
        )

        regenerator.delete_activity_records([12345])

        execute_calls = mock_conn.execute.call_args_list
        executed_sqls = [call[0][0] for call in execute_calls]

        # Should NOT have DELETE for body_composition
        body_comp_deletes = [
            sql for sql in executed_sqls if "DELETE FROM body_composition" in sql
        ]
        assert len(body_comp_deletes) == 0, "body_composition should be skipped"

        # Should have DELETE for splits (Phase 5: within transaction)
        splits_deletes = [sql for sql in executed_sqls if "DELETE FROM splits" in sql]
        assert len(splits_deletes) == 1, "splits table should be deleted"

        # Phase 5: Should have BEGIN and COMMIT for transaction
        assert any(
            "BEGIN TRANSACTION" in sql for sql in executed_sqls
        ), "Should start transaction"
        assert any(
            "COMMIT" in sql for sql in executed_sqls
        ), "Should commit transaction"


class TestDeleteTableAllRecords:
    """Test delete_table_all_records method (Phase 2: Table-Wide Deletion)."""

    def test_delete_table_all_records_deletes_entire_table(self, tmp_path, mocker):
        """Test that delete_table_all_records deletes all records from table."""
        mock_conn = mocker.MagicMock()
        mock_conn.__enter__ = mocker.MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = mocker.MagicMock(return_value=False)
        mocker.patch(
            "tools.scripts.regenerate_duckdb.duckdb.connect", return_value=mock_conn
        )

        db_path = tmp_path / "test.db"
        regenerator = DuckDBRegenerator(db_path=db_path, tables=["splits"])

        # Call delete_table_all_records
        regenerator.delete_table_all_records(["splits"])

        # Verify DELETE without WHERE clause
        execute_calls = mock_conn.execute.call_args_list
        executed_sqls = [call[0][0] for call in execute_calls]

        # Should have "DELETE FROM splits" without WHERE clause
        assert any("DELETE FROM splits" in sql for sql in executed_sqls)
        # Should NOT have WHERE clause
        splits_deletes = [sql for sql in executed_sqls if "DELETE FROM splits" in sql]
        assert len(splits_deletes) == 1
        assert "WHERE" not in splits_deletes[0], "Should not have WHERE clause"

    def test_delete_table_all_records_skips_body_composition(self, tmp_path, mocker):
        """Test that body_composition is skipped in table-wide deletion."""
        mock_conn = mocker.MagicMock()
        mock_conn.__enter__ = mocker.MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = mocker.MagicMock(return_value=False)
        mocker.patch(
            "tools.scripts.regenerate_duckdb.duckdb.connect", return_value=mock_conn
        )

        db_path = tmp_path / "test.db"
        regenerator = DuckDBRegenerator(
            db_path=db_path, tables=["body_composition", "splits"]
        )

        regenerator.delete_table_all_records(["body_composition", "splits"])

        execute_calls = mock_conn.execute.call_args_list
        executed_sqls = [call[0][0] for call in execute_calls]

        # Should NOT have DELETE for body_composition
        body_comp_deletes = [sql for sql in executed_sqls if "body_composition" in sql]
        assert len(body_comp_deletes) == 0, "body_composition should be skipped"

        # Should have DELETE for splits
        splits_deletes = [sql for sql in executed_sqls if "DELETE FROM splits" in sql]
        assert len(splits_deletes) == 1

    def test_delete_table_all_records_multiple_tables(self, tmp_path, mocker):
        """Test that delete_table_all_records handles multiple tables."""
        mock_conn = mocker.MagicMock()
        mock_conn.__enter__ = mocker.MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = mocker.MagicMock(return_value=False)
        mocker.patch(
            "tools.scripts.regenerate_duckdb.duckdb.connect", return_value=mock_conn
        )

        db_path = tmp_path / "test.db"
        regenerator = DuckDBRegenerator(
            db_path=db_path, tables=["splits", "form_efficiency"]
        )

        regenerator.delete_table_all_records(["splits", "form_efficiency"])

        execute_calls = mock_conn.execute.call_args_list
        executed_sqls = [call[0][0] for call in execute_calls]

        # Should have DELETE for both tables
        splits_deletes = [sql for sql in executed_sqls if "DELETE FROM splits" in sql]
        form_deletes = [
            sql for sql in executed_sqls if "DELETE FROM form_efficiency" in sql
        ]

        assert len(splits_deletes) == 1
        assert len(form_deletes) == 1


class TestRegenerateAllDeletionLogic:
    """Test regenerate_all deletion strategy (Phase 2: Logic Fix)."""

    def test_regenerate_all_uses_table_wide_deletion_without_activity_ids(
        self, tmp_path, mocker
    ):
        """Test that regenerate_all uses delete_table_all_records when no activity_ids."""
        # Mock delete methods
        mock_delete_table_all = mocker.patch.object(
            DuckDBRegenerator, "delete_table_all_records"
        )
        mock_delete_activity = mocker.patch.object(
            DuckDBRegenerator, "delete_activity_records"
        )

        # Mock other methods - return at least one activity to reach deletion logic
        mocker.patch.object(
            DuckDBRegenerator,
            "get_all_activities_from_raw",
            return_value=[(12345, "2025-01-01")],
        )
        mocker.patch.object(
            DuckDBRegenerator,
            "regenerate_single_activity",
            return_value={"status": "success"},
        )

        db_path = tmp_path / "test.db"
        regenerator = DuckDBRegenerator(db_path=db_path, tables=["splits"])

        # Call regenerate_all without activity_ids (table-wide mode)
        regenerator.regenerate_all()

        # Should use delete_table_all_records, NOT delete_activity_records
        mock_delete_table_all.assert_called_once_with(["splits"])
        mock_delete_activity.assert_not_called()

    def test_regenerate_all_uses_id_specific_deletion_with_activity_ids(
        self, tmp_path, mocker
    ):
        """Test that regenerate_all uses delete_activity_records when activity_ids provided."""
        # Mock delete methods
        mock_delete_table_all = mocker.patch.object(
            DuckDBRegenerator, "delete_table_all_records"
        )
        mock_delete_activity = mocker.patch.object(
            DuckDBRegenerator, "delete_activity_records"
        )

        # Mock regenerate_single_activity
        mocker.patch.object(
            DuckDBRegenerator,
            "regenerate_single_activity",
            return_value={"status": "success"},
        )

        db_path = tmp_path / "test.db"
        regenerator = DuckDBRegenerator(db_path=db_path, tables=["splits"])

        # Call regenerate_all with activity_ids (ID-specific mode)
        regenerator.regenerate_all(activity_ids=[12345, 67890])

        # Should use delete_activity_records, NOT delete_table_all_records
        mock_delete_activity.assert_called_once_with([12345, 67890])
        mock_delete_table_all.assert_not_called()

    def test_regenerate_all_no_deletion_without_tables_filter(self, tmp_path, mocker):
        """Test that no deletion occurs when tables=None (full regeneration)."""
        mock_delete_table_all = mocker.patch.object(
            DuckDBRegenerator, "delete_table_all_records"
        )
        mock_delete_activity = mocker.patch.object(
            DuckDBRegenerator, "delete_activity_records"
        )
        mocker.patch.object(
            DuckDBRegenerator, "get_all_activities_from_raw", return_value=[]
        )

        db_path = tmp_path / "test.db"
        regenerator = DuckDBRegenerator(db_path=db_path, tables=None)

        regenerator.regenerate_all()

        # No deletion should occur without tables filter
        mock_delete_table_all.assert_not_called()
        mock_delete_activity.assert_not_called()


# Phase 2 tests (deletion logic) will be added later
