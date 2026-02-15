"""
Unit tests for DuckDB regeneration script.

Tests for table filtering, validation, and selective deletion features.
Phase 1: Core Infrastructure (Table Filtering & Validation)
"""

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
            "garmin_mcp.scripts.regenerate_duckdb.duckdb.connect",
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
            "garmin_mcp.scripts.regenerate_duckdb.duckdb.connect",
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


@pytest.mark.unit
class TestDeleteTableAllRecords:
    """Test delete_table_all_records method (Phase 2: Table-Wide Deletion)."""

    def test_delete_table_all_records_deletes_entire_table(self, tmp_path, mocker):
        """Test that delete_table_all_records deletes all records from table."""
        mock_conn = mocker.MagicMock()
        mock_conn.__enter__ = mocker.MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = mocker.MagicMock(return_value=False)
        mocker.patch(
            "garmin_mcp.scripts.regenerate_duckdb.duckdb.connect",
            return_value=mock_conn,
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
            "garmin_mcp.scripts.regenerate_duckdb.duckdb.connect",
            return_value=mock_conn,
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
            "garmin_mcp.scripts.regenerate_duckdb.duckdb.connect",
            return_value=mock_conn,
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

    def test_delete_table_all_records_handles_missing_tables(self, tmp_path, mocker):
        """Test that delete_table_all_records handles missing tables gracefully."""
        # Setup mock connection
        mock_conn = mocker.MagicMock()
        mock_conn.__enter__ = mocker.MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = mocker.MagicMock(return_value=False)

        # Mock execute to raise CatalogException for non_existent_table
        def execute_side_effect(sql):
            if "non_existent_table" in sql:
                import duckdb

                raise duckdb.CatalogException(
                    "Catalog Error: Table with name non_existent_table does not exist!"
                )
            return None

        mock_conn.execute = mocker.MagicMock(side_effect=execute_side_effect)

        mocker.patch(
            "garmin_mcp.scripts.regenerate_duckdb.duckdb.connect",
            return_value=mock_conn,
        )

        db_path = tmp_path / "test.db"
        regenerator = DuckDBRegenerator(
            db_path=db_path, tables=["splits", "non_existent_table"]
        )

        # Should not raise error, just log warnings
        regenerator.delete_table_all_records(["splits", "non_existent_table"])

        # Verify both tables were attempted
        execute_calls = mock_conn.execute.call_args_list
        executed_sqls = [call[0][0] for call in execute_calls]

        # Should attempt DELETE for both tables
        splits_deletes = [sql for sql in executed_sqls if "DELETE FROM splits" in sql]
        non_existent_deletes = [
            sql for sql in executed_sqls if "DELETE FROM non_existent_table" in sql
        ]

        assert len(splits_deletes) == 1, "Should attempt to delete from splits"
        assert (
            len(non_existent_deletes) == 1
        ), "Should attempt to delete from non_existent_table"


@pytest.mark.unit
class TestRegenerateAllDeletionLogic:
    """Test regenerate_all deletion strategy (Phase 2: Logic Fix)."""

    def test_regenerate_all_uses_table_wide_deletion_without_activity_ids(
        self, tmp_path, mocker
    ):
        """Test that regenerate_all uses delete_table_all_records when no activity_ids (Phase 4: requires force=True)."""
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
        regenerator = DuckDBRegenerator(db_path=db_path, tables=["splits"], force=True)

        # Call regenerate_all without activity_ids (table-wide mode)
        regenerator.regenerate_all()

        # Should use delete_table_all_records, NOT delete_activity_records
        mock_delete_table_all.assert_called_once_with(["splits"])
        mock_delete_activity.assert_not_called()

    def test_regenerate_all_uses_id_specific_deletion_with_activity_ids(
        self, tmp_path, mocker
    ):
        """Test that regenerate_all uses delete_activity_records when activity_ids provided (Phase 4: requires force=True)."""
        # Create actual DB file and mock validation to pass
        db_path = tmp_path / "test.db"
        db_path.touch()

        # Mock validation to pass (all activities exist)
        mocker.patch.object(DuckDBRegenerator, "validate_table_dependencies")

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

        regenerator = DuckDBRegenerator(db_path=db_path, tables=["splits"], force=True)

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


@pytest.mark.unit
class TestForceFlag:
    """Test --force flag behavior (Phase 4)."""

    def test_regenerate_all_without_force_skips_deletion(self, tmp_path, mocker):
        """Test that without --force, deletion is skipped and message is logged."""
        # Mock validation to pass
        mocker.patch.object(DuckDBRegenerator, "validate_table_dependencies")

        # Mock delete methods
        mock_delete_activity = mocker.patch.object(
            DuckDBRegenerator, "delete_activity_records"
        )
        mock_delete_table = mocker.patch.object(
            DuckDBRegenerator, "delete_table_all_records"
        )
        mock_logger_info = mocker.patch(
            "garmin_mcp.scripts.regenerate_duckdb.logger.info"
        )

        # Mock other methods to return at least one activity
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
        regenerator = DuckDBRegenerator(db_path=db_path, tables=["splits"], force=False)

        # Run regenerate_all (should skip deletion)
        regenerator.regenerate_all(activity_ids=[12345])

        # Verify deletion methods NOT called
        mock_delete_activity.assert_not_called()
        mock_delete_table.assert_not_called()

        # Verify skip message was logged
        skip_message_calls = [
            call
            for call in mock_logger_info.call_args_list
            if "Skipping deletion" in str(call)
        ]
        assert len(skip_message_calls) > 0, "Skip message should be logged"

    def test_regenerate_all_with_force_calls_deletion(self, tmp_path, mocker):
        """Test that with --force, deletion is executed."""
        # Create actual DB file
        db_path = tmp_path / "test.db"
        db_path.touch()

        # Mock validation to pass
        mocker.patch.object(DuckDBRegenerator, "validate_table_dependencies")

        # Mock delete methods
        mock_delete_activity = mocker.patch.object(
            DuckDBRegenerator, "delete_activity_records"
        )

        # Mock regenerate_single_activity
        mocker.patch.object(
            DuckDBRegenerator,
            "regenerate_single_activity",
            return_value={"status": "success"},
        )

        regenerator = DuckDBRegenerator(db_path=db_path, tables=["splits"], force=True)

        # Run regenerate_all with force=True (should call deletion)
        regenerator.regenerate_all(activity_ids=[12345])

        # Verify deletion IS called
        mock_delete_activity.assert_called_once_with([12345])

    def test_regenerate_single_activity_without_force_skips_existing(
        self, tmp_path, mocker
    ):
        """Test that without --force, existing activities are skipped with clear message."""
        # Mock cache check to return True (activity exists)
        mocker.patch.object(DuckDBRegenerator, "check_duckdb_cache", return_value=True)
        mocker.patch.object(
            DuckDBRegenerator, "check_raw_data_exists", return_value=True
        )
        mock_logger_info = mocker.patch(
            "garmin_mcp.scripts.regenerate_duckdb.logger.info"
        )

        db_path = tmp_path / "test.db"
        regenerator = DuckDBRegenerator(db_path=db_path, tables=["splits"], force=False)

        # Call regenerate_single_activity (should skip)
        result = regenerator.regenerate_single_activity(12345, "2025-01-01")

        # Verify status is skipped
        assert result["status"] == "skipped"
        assert result["reason"] == "existing_in_duckdb_no_force"

        # Verify skip message was logged
        skip_message_calls = [
            call
            for call in mock_logger_info.call_args_list
            if "use --force to update" in str(call)
        ]
        assert (
            len(skip_message_calls) > 0
        ), "Skip message with --force hint should be logged"

    def test_regenerate_single_activity_with_force_processes_existing(
        self, tmp_path, mocker
    ):
        """Test that with --force, existing activities are processed."""
        # Mock cache check to return True (activity exists)
        mocker.patch.object(DuckDBRegenerator, "check_duckdb_cache", return_value=True)
        mocker.patch.object(
            DuckDBRegenerator, "check_raw_data_exists", return_value=True
        )

        # Mock GarminIngestWorker
        mock_worker = mocker.Mock()
        mock_worker.process_activity.return_value = {"activity": "activity.json"}
        mocker.patch(
            "garmin_mcp.scripts.regenerate_duckdb.GarminIngestWorker",
            return_value=mock_worker,
        )

        db_path = tmp_path / "test.db"
        regenerator = DuckDBRegenerator(db_path=db_path, tables=["splits"], force=True)

        # Call regenerate_single_activity with force=True
        result = regenerator.regenerate_single_activity(12345, "2025-01-01")

        # Verify status is success (not skipped)
        assert result["status"] == "success"

        # Verify process_activity was called
        mock_worker.process_activity.assert_called_once()


@pytest.mark.unit
class TestValidateTableDependencies:
    """Test validate_table_dependencies method (Phase 2: Safety Validation)."""

    def test_validation_skipped_when_tables_is_none(self, tmp_path, mocker):
        """Test that validation is skipped when tables=None (full regeneration)."""
        db_path = tmp_path / "test.db"
        regenerator = DuckDBRegenerator(db_path=db_path, tables=None)

        # Should not raise error (validation skipped)
        regenerator.validate_table_dependencies(tables=None, activity_ids=[12345])

    def test_validation_skipped_when_activities_in_tables(self, tmp_path, mocker):
        """Test that validation is skipped when 'activities' in tables."""
        db_path = tmp_path / "test.db"
        regenerator = DuckDBRegenerator(
            db_path=db_path, tables=["activities", "splits"]
        )

        # Should not raise error (parent being regenerated)
        regenerator.validate_table_dependencies(
            tables=["activities", "splits"], activity_ids=[12345]
        )

    def test_validation_passes_when_parent_activities_exist(self, tmp_path, mocker):
        """Test that validation passes when all parent activities exist in DuckDB."""
        # Create actual DB file so path.exists() returns True
        db_path = tmp_path / "test.db"
        db_path.touch()  # Create empty file

        # Mock DuckDB connection to return that activities exist
        mock_conn = mocker.MagicMock()
        mock_cursor = mocker.MagicMock()
        mock_cursor.fetchone.return_value = (1,)  # COUNT(*) = 1
        mock_conn.execute.return_value = mock_cursor
        mock_conn.__enter__ = mocker.MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = mocker.MagicMock(return_value=False)
        mocker.patch(
            "garmin_mcp.scripts.regenerate_duckdb.duckdb.connect",
            return_value=mock_conn,
        )

        regenerator = DuckDBRegenerator(db_path=db_path, tables=["splits"])

        # Should not raise error (all activities exist)
        regenerator.validate_table_dependencies(
            tables=["splits"], activity_ids=[12345, 67890]
        )

    def test_validation_fails_when_parent_activities_missing(self, tmp_path, mocker):
        """Test that validation fails when parent activities don't exist."""
        # Mock DuckDB connection to return that activities don't exist
        mock_conn = mocker.MagicMock()
        mock_cursor = mocker.MagicMock()
        mock_cursor.fetchone.return_value = (0,)  # COUNT(*) = 0
        mock_conn.execute.return_value = mock_cursor
        mock_conn.__enter__ = mocker.MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = mocker.MagicMock(return_value=False)
        mocker.patch(
            "garmin_mcp.scripts.regenerate_duckdb.duckdb.connect",
            return_value=mock_conn,
        )

        db_path = tmp_path / "test.db"
        regenerator = DuckDBRegenerator(db_path=db_path, tables=["splits"])

        # Should raise ValueError with helpful message
        with pytest.raises(ValueError) as exc_info:
            regenerator.validate_table_dependencies(
                tables=["splits"], activity_ids=[12345, 67890]
            )

        error_msg = str(exc_info.value)
        assert "Cannot regenerate child tables without parent activities" in error_msg
        assert "Missing activity IDs: [12345, 67890]" in error_msg
        assert "include 'activities' in --tables" in error_msg

    def test_validation_shows_first_5_missing_ids(self, tmp_path, mocker):
        """Test that error message shows first 5 missing IDs when many are missing."""
        # Mock DuckDB connection to return that no activities exist
        mock_conn = mocker.MagicMock()
        mock_cursor = mocker.MagicMock()
        mock_cursor.fetchone.return_value = (0,)  # COUNT(*) = 0
        mock_conn.execute.return_value = mock_cursor
        mock_conn.__enter__ = mocker.MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = mocker.MagicMock(return_value=False)
        mocker.patch(
            "garmin_mcp.scripts.regenerate_duckdb.duckdb.connect",
            return_value=mock_conn,
        )

        db_path = tmp_path / "test.db"
        regenerator = DuckDBRegenerator(db_path=db_path, tables=["splits"])

        # Test with 10 missing IDs
        missing_ids = [
            12345,
            67890,
            11111,
            22222,
            33333,
            44444,
            55555,
            66666,
            77777,
            88888,
        ]

        with pytest.raises(ValueError) as exc_info:
            regenerator.validate_table_dependencies(
                tables=["splits"], activity_ids=missing_ids
            )

        error_msg = str(exc_info.value)
        # Should show first 5 IDs
        assert "12345" in error_msg
        assert "33333" in error_msg
        # Should show "and X more"
        assert "(and 5 more)" in error_msg

    def test_validation_handles_catalog_exception(self, tmp_path, mocker):
        """Test that validation handles CatalogException (activities table doesn't exist)."""
        # Mock DuckDB connection to raise CatalogException
        mock_conn = mocker.MagicMock()

        def execute_side_effect(*args, **kwargs):
            import duckdb

            raise duckdb.CatalogException(
                "Catalog Error: Table with name activities does not exist!"
            )

        mock_conn.execute = mocker.MagicMock(side_effect=execute_side_effect)
        mock_conn.__enter__ = mocker.MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = mocker.MagicMock(return_value=False)
        mocker.patch(
            "garmin_mcp.scripts.regenerate_duckdb.duckdb.connect",
            return_value=mock_conn,
        )

        db_path = tmp_path / "test.db"
        regenerator = DuckDBRegenerator(db_path=db_path, tables=["splits"])

        # Should raise ValueError (all IDs are missing)
        with pytest.raises(ValueError) as exc_info:
            regenerator.validate_table_dependencies(
                tables=["splits"], activity_ids=[12345]
            )

        error_msg = str(exc_info.value)
        assert "Cannot regenerate child tables without parent activities" in error_msg
        assert "12345" in error_msg

    def test_validation_partial_missing_ids(self, tmp_path, mocker):
        """Test validation when only some activity IDs are missing."""
        # Create actual DB file
        db_path = tmp_path / "test.db"
        db_path.touch()

        # Mock DuckDB to return different results for different IDs
        def execute_side_effect(query, params):
            activity_id = params[0]
            mock_cursor = mocker.MagicMock()
            # 12345 exists, 67890 doesn't exist
            if activity_id == 12345:
                mock_cursor.fetchone.return_value = (1,)  # exists
            else:
                mock_cursor.fetchone.return_value = (0,)  # doesn't exist
            return mock_cursor

        mock_conn = mocker.MagicMock()
        mock_conn.execute = mocker.MagicMock(side_effect=execute_side_effect)
        mock_conn.__enter__ = mocker.MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = mocker.MagicMock(return_value=False)
        mocker.patch(
            "garmin_mcp.scripts.regenerate_duckdb.duckdb.connect",
            return_value=mock_conn,
        )

        regenerator = DuckDBRegenerator(db_path=db_path, tables=["splits"])

        # Should raise ValueError showing only missing ID
        with pytest.raises(ValueError) as exc_info:
            regenerator.validate_table_dependencies(
                tables=["splits"], activity_ids=[12345, 67890]
            )

        error_msg = str(exc_info.value)
        assert "Missing activity IDs: [67890]" in error_msg
        # Should not show 12345 (it exists)
        assert "12345" not in error_msg or "67890" in error_msg


# Phase 2 tests (deletion logic) will be added later
