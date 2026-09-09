"""DuckDBRegenerator: per-activity vs table-wide deletion, date-range scoped deletion."""

import pytest

from garmin_mcp.scripts.regenerate_duckdb import DuckDBRegenerator


@pytest.mark.unit
class TestDeleteTableAllRecords:
    """Test delete_table_all_records method (Phase 2: Table-Wide Deletion)."""

    def test_delete_table_all_records_deletes_entire_table(self, tmp_path, mocker):
        """Test that delete_table_all_records deletes all records from table."""
        mock_conn = mocker.MagicMock()
        mock_conn.__enter__ = mocker.MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = mocker.MagicMock(return_value=False)
        mocker.patch(
            "garmin_mcp.scripts.regenerate.deletion_strategy.duckdb.connect",
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
            "garmin_mcp.scripts.regenerate.deletion_strategy.duckdb.connect",
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
            "garmin_mcp.scripts.regenerate.deletion_strategy.duckdb.connect",
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
            "garmin_mcp.scripts.regenerate.deletion_strategy.duckdb.connect",
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
