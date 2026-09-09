"""DuckDBRegenerator: --force semantics and parent-table dependency validation."""

import pytest

from garmin_mcp.scripts.regenerate_duckdb import DuckDBRegenerator


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
            "garmin_mcp.scripts.regenerate.validator.duckdb.connect",
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
            "garmin_mcp.scripts.regenerate.validator.duckdb.connect",
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
            "garmin_mcp.scripts.regenerate.validator.duckdb.connect",
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
            "garmin_mcp.scripts.regenerate.validator.duckdb.connect",
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
            "garmin_mcp.scripts.regenerate.validator.duckdb.connect",
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


@pytest.mark.unit
class TestDateRangeScopedDeletion:
    """Test that --tables + date range + --force uses scoped deletion (not table-wide)."""

    def test_date_range_uses_scoped_deletion(self, tmp_path, mocker):
        """Date range should use delete_activity_records with resolved IDs,
        NOT delete_table_all_records."""
        mock_delete_table_all = mocker.patch.object(
            DuckDBRegenerator, "delete_table_all_records"
        )
        mock_delete_activity = mocker.patch.object(
            DuckDBRegenerator, "delete_activity_records"
        )
        mocker.patch.object(DuckDBRegenerator, "validate_table_dependencies")
        mocker.patch.object(
            DuckDBRegenerator,
            "get_activities_by_date_range",
            return_value=[(12345, "2025-05-01"), (67890, "2025-05-15")],
        )
        mocker.patch.object(
            DuckDBRegenerator,
            "regenerate_single_activity",
            return_value={"status": "success"},
        )

        db_path = tmp_path / "test.db"
        regenerator = DuckDBRegenerator(
            db_path=db_path, tables=["performance_trends"], force=True
        )

        regenerator.regenerate_all(start_date="2025-05-01", end_date="2025-05-31")

        mock_delete_activity.assert_called_once_with([12345, 67890])
        mock_delete_table_all.assert_not_called()

    def test_date_range_runs_validation(self, tmp_path, mocker):
        """Date range should call validate_table_dependencies with resolved IDs."""
        mock_validate = mocker.patch.object(
            DuckDBRegenerator, "validate_table_dependencies"
        )
        mocker.patch.object(DuckDBRegenerator, "delete_activity_records")
        mocker.patch.object(
            DuckDBRegenerator,
            "get_activities_by_date_range",
            return_value=[(12345, "2025-05-01")],
        )
        mocker.patch.object(
            DuckDBRegenerator,
            "regenerate_single_activity",
            return_value={"status": "success"},
        )

        db_path = tmp_path / "test.db"
        regenerator = DuckDBRegenerator(db_path=db_path, tables=["splits"], force=True)

        regenerator.regenerate_all(start_date="2025-05-01", end_date="2025-05-31")

        mock_validate.assert_called_once_with(["splits"], [12345])

    def test_no_filter_still_uses_table_wide_deletion(self, tmp_path, mocker):
        """Without activity_ids or date range, table-wide deletion is preserved."""
        mock_delete_table_all = mocker.patch.object(
            DuckDBRegenerator, "delete_table_all_records"
        )
        mock_delete_activity = mocker.patch.object(
            DuckDBRegenerator, "delete_activity_records"
        )
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

        regenerator.regenerate_all()

        mock_delete_table_all.assert_called_once_with(["splits"])
        mock_delete_activity.assert_not_called()
