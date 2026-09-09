"""DuckDBRegenerator: per-activity vs table-wide deletion, date-range scoped deletion."""

import pytest

from garmin_mcp.scripts.regenerate_duckdb import DuckDBRegenerator


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
