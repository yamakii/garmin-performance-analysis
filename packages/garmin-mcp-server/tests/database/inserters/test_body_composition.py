"""Tests for body_composition inserter."""

import json
from pathlib import Path

import pytest
from pytest_mock import MockerFixture


@pytest.mark.unit
class TestInsertBodyCompositionData:
    """Tests for insert_body_composition_data function."""

    SAMPLE_WEIGHT_DATA = {
        "dateTimestamp": 1696291200000,
        "weight": 70.5,
        "bmi": 22.3,
        "bodyFat": 15.0,
        "muscleMass": 55.0,
    }

    def test_happy_path(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Create tmp JSON file, mock GarminDBWriter, verify returns True."""
        raw_file = tmp_path / "2025-10-03.json"
        raw_file.write_text(json.dumps(self.SAMPLE_WEIGHT_DATA), encoding="utf-8")

        mock_writer_cls = mocker.patch(
            "garmin_mcp.database.inserters.body_composition.GarminDBWriter"
        )
        mock_writer = mock_writer_cls.return_value
        mock_writer.insert_body_composition.return_value = True

        from garmin_mcp.database.inserters.body_composition import (
            insert_body_composition_data,
        )

        result = insert_body_composition_data(
            raw_file=str(raw_file), date="2025-10-03", db_path="/tmp/test.duckdb"
        )

        assert result is True
        mock_writer_cls.assert_called_once_with(db_path="/tmp/test.duckdb")
        mock_writer.insert_body_composition.assert_called_once_with(
            date="2025-10-03", weight_data=self.SAMPLE_WEIGHT_DATA
        )

    def test_file_not_found(self, mocker: MockerFixture) -> None:
        """Pass non-existent path, verify returns False without calling writer."""
        mock_writer_cls = mocker.patch(
            "garmin_mcp.database.inserters.body_composition.GarminDBWriter"
        )

        from garmin_mcp.database.inserters.body_composition import (
            insert_body_composition_data,
        )

        result = insert_body_composition_data(
            raw_file="/nonexistent/path/2025-10-03.json", date="2025-10-03"
        )

        assert result is False
        mock_writer_cls.assert_not_called()

    def test_writer_exception(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Mock writer to raise exception, verify returns False."""
        raw_file = tmp_path / "2025-10-03.json"
        raw_file.write_text(json.dumps(self.SAMPLE_WEIGHT_DATA), encoding="utf-8")

        mock_writer_cls = mocker.patch(
            "garmin_mcp.database.inserters.body_composition.GarminDBWriter"
        )
        mock_writer_cls.return_value.insert_body_composition.side_effect = RuntimeError(
            "DB connection failed"
        )

        from garmin_mcp.database.inserters.body_composition import (
            insert_body_composition_data,
        )

        result = insert_body_composition_data(
            raw_file=str(raw_file), date="2025-10-03", db_path="/tmp/test.duckdb"
        )

        assert result is False

    def test_db_path_none_uses_default(
        self, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        """Pass db_path=None, verify GarminDBWriter called without db_path arg."""
        raw_file = tmp_path / "2025-10-03.json"
        raw_file.write_text(json.dumps(self.SAMPLE_WEIGHT_DATA), encoding="utf-8")

        mock_writer_cls = mocker.patch(
            "garmin_mcp.database.inserters.body_composition.GarminDBWriter"
        )
        mock_writer = mock_writer_cls.return_value
        mock_writer.insert_body_composition.return_value = True

        from garmin_mcp.database.inserters.body_composition import (
            insert_body_composition_data,
        )

        result = insert_body_composition_data(
            raw_file=str(raw_file), date="2025-10-03", db_path=None
        )

        assert result is True
        # When db_path is None, the source calls GarminDBWriter() without args
        mock_writer_cls.assert_called_once_with()
