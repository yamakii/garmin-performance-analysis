"""DuckDBRegenerator: table filter and argument validation."""

import pytest

from garmin_mcp.scripts.regenerate_duckdb import DuckDBRegenerator


@pytest.mark.unit
class TestFilterTables:
    """Test filter_tables method for table validation and filtering."""

    def test_filter_tables_none_returns_all(self, tmp_path):
        """Test that None returns all 11 tables."""
        db_path = tmp_path / "test.db"
        regenerator = DuckDBRegenerator(db_path=db_path)

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

    def test_filter_tables_single_table_no_auto_add(self, tmp_path):
        """Test that single table does NOT automatically add activities table."""
        db_path = tmp_path / "test.db"
        regenerator = DuckDBRegenerator(db_path=db_path)

        result = regenerator.filter_tables(["splits"])

        # Phase 1 change: NO auto-add activities
        assert result == ["splits"]
        assert "activities" not in result
        assert len(result) == 1

    def test_filter_tables_multiple_tables_no_auto_add(self, tmp_path):
        """Test that multiple tables do NOT automatically add activities table."""
        db_path = tmp_path / "test.db"
        regenerator = DuckDBRegenerator(db_path=db_path)

        result = regenerator.filter_tables(["splits", "form_efficiency"])

        # Phase 1 change: NO auto-add activities
        assert result == ["splits", "form_efficiency"]
        assert "activities" not in result
        assert len(result) == 2

    def test_filter_tables_body_composition_only_no_activities(self, tmp_path):
        """Test that body_composition alone does NOT add activities table."""
        db_path = tmp_path / "test.db"
        regenerator = DuckDBRegenerator(db_path=db_path)

        result = regenerator.filter_tables(["body_composition"])

        assert result == ["body_composition"]
        assert "activities" not in result
        assert len(result) == 1

    def test_filter_tables_invalid_table_name_raises_error(self, tmp_path):
        """Test that invalid table name raises ValueError."""
        db_path = tmp_path / "test.db"
        regenerator = DuckDBRegenerator(db_path=db_path)

        with pytest.raises(ValueError) as exc_info:
            regenerator.filter_tables(["invalid_table"])

        assert "Invalid table names" in str(exc_info.value)
        assert "invalid_table" in str(exc_info.value)

    def test_filter_tables_mixed_valid_invalid_raises_error(self, tmp_path):
        """Test that mix of valid and invalid tables raises ValueError."""
        db_path = tmp_path / "test.db"
        regenerator = DuckDBRegenerator(db_path=db_path)

        with pytest.raises(ValueError) as exc_info:
            regenerator.filter_tables(["splits", "invalid_table", "wrong_table"])

        assert "Invalid table names" in str(exc_info.value)
        # Should include both invalid names
        assert "invalid_table" in str(exc_info.value)
        assert "wrong_table" in str(exc_info.value)

    def test_filter_tables_with_activities_explicit(self, tmp_path):
        """Test that activities can be explicitly included without duplication."""
        db_path = tmp_path / "test.db"
        regenerator = DuckDBRegenerator(db_path=db_path)

        result = regenerator.filter_tables(["activities", "splits"])

        # Should preserve order and not duplicate
        assert result == ["activities", "splits"]
        assert result.count("activities") == 1
        assert len(result) == 2


@pytest.mark.unit
class TestValidateArguments:
    """Test CLI argument validation."""

    def test_init_with_delete_db_and_tables_raises_error(self, tmp_path):
        """Test that --delete-db and --tables are mutually exclusive."""
        db_path = tmp_path / "test.db"
        with pytest.raises(ValueError) as exc_info:
            DuckDBRegenerator(db_path=db_path, delete_old_db=True, tables=["splits"])

        assert "--delete-db cannot be used with --tables" in str(exc_info.value)
        # Phase 1 change: No mention of --force
        assert "Database file deletion is only allowed for full regeneration" in str(
            exc_info.value
        )

    def test_init_without_force_parameter(self, tmp_path):
        """Test that __init__ defaults force=False when not specified (Phase 4)."""
        db_path = tmp_path / "test.db"
        regenerator = DuckDBRegenerator(db_path=db_path, tables=["splits"])

        # Should have force attribute defaulting to False
        assert hasattr(regenerator, "force")
        assert regenerator.force is False
        assert regenerator.tables == ["splits"]

    def test_init_with_delete_db_no_tables_succeeds(self, tmp_path):
        """Test that --delete-db alone is valid (full regeneration)."""
        # Should not raise
        db_path = tmp_path / "test.db"
        regenerator = DuckDBRegenerator(
            db_path=db_path, delete_old_db=True, tables=None
        )
        assert regenerator.delete_old_db is True
        assert regenerator.tables is None

    def test_init_with_tables_succeeds(self, tmp_path):
        """Test that --tables alone is valid with force defaulting to False (Phase 4)."""
        db_path = tmp_path / "test.db"
        regenerator = DuckDBRegenerator(db_path=db_path, tables=["splits"])

        assert regenerator.tables == ["splits"]
        # force parameter should exist with default False
        assert hasattr(regenerator, "force")
        assert regenerator.force is False

    def test_init_stores_tables_parameter(self, tmp_path):
        """Test that tables parameter is stored in instance."""
        db_path = tmp_path / "test.db"
        tables = ["splits", "form_efficiency"]
        regenerator = DuckDBRegenerator(db_path=db_path, tables=tables)

        assert regenerator.tables == tables

    def test_init_default_tables_is_none(self, tmp_path):
        """Test that tables defaults to None (all tables)."""
        db_path = tmp_path / "test.db"
        regenerator = DuckDBRegenerator(db_path=db_path)

        assert regenerator.tables is None


@pytest.mark.unit
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
            "garmin_mcp.scripts.regenerate.deletion_strategy.duckdb.connect",
            return_value=mock_conn,
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
            "garmin_mcp.scripts.regenerate.deletion_strategy.duckdb.connect",
            return_value=mock_conn,
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
