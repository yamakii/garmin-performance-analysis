"""
Tests for Form Efficiency Inserter

Test coverage:
- Unit tests for insert_form_efficiency function
- Integration tests with DuckDB
"""

import json

import pytest

from garmin_mcp.database.inserters.form_efficiency import insert_form_efficiency


class TestFormEfficiencyInserter:
    """Test suite for Form Efficiency Inserter."""

    @pytest.mark.unit
    def test_insert_form_efficiency_success(self, sample_splits_file, tmp_path):
        """Test insert_form_efficiency inserts data successfully."""
        db_path = tmp_path / "test.duckdb"

        result = insert_form_efficiency(
            activity_id=20636804823,
            db_path=str(db_path),
            raw_splits_file=str(sample_splits_file),
        )

        assert result is True
        assert db_path.exists()

    @pytest.mark.unit
    def test_insert_form_efficiency_missing_file(self, tmp_path):
        """Test insert_form_efficiency handles missing file."""
        db_path = tmp_path / "test.duckdb"

        result = insert_form_efficiency(
            activity_id=12345,
            db_path=str(db_path),
            raw_splits_file="/nonexistent/splits.json",
        )

        assert result is False

    @pytest.mark.unit
    def test_insert_form_efficiency_no_data(self, tmp_path):
        """Test insert_form_efficiency handles missing form metrics."""
        splits_data = {
            "activityId": 12345,
            "lapDTOs": [
                {
                    "distance": 1000.0,
                    # No form metrics
                }
            ],
        }
        splits_file = tmp_path / "splits.json"
        with open(splits_file, "w", encoding="utf-8") as f:
            json.dump(splits_data, f)

        db_path = tmp_path / "test.duckdb"

        result = insert_form_efficiency(
            activity_id=12345,
            db_path=str(db_path),
            raw_splits_file=str(splits_file),
        )

        assert result is False

    @pytest.mark.integration
    def test_insert_form_efficiency_db_integration(self, sample_splits_file, tmp_path):
        """Test insert_form_efficiency actually writes to DuckDB."""
        import duckdb

        db_path = tmp_path / "test.duckdb"

        result = insert_form_efficiency(
            activity_id=20636804823,
            db_path=str(db_path),
            raw_splits_file=str(sample_splits_file),
        )

        assert result is True

        # Verify data in DuckDB
        conn = duckdb.connect(str(db_path))

        # Check form_efficiency table exists
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        assert "form_efficiency" in table_names

        # Check form_efficiency data
        form_eff = conn.execute(
            "SELECT * FROM form_efficiency WHERE activity_id = 20636804823"
        ).fetchall()
        assert len(form_eff) == 1

        # Verify calculated statistics
        row = form_eff[0]
        assert row[0] == 20636804823  # activity_id

        # GCT stats: mean([251.4, 249.3, 249.3, 249.5]) = 249.875
        assert abs(row[1] - 249.875) < 0.01  # gct_average
        assert abs(row[2] - 249.3) < 0.01  # gct_min
        assert abs(row[3] - 251.4) < 0.01  # gct_max
        assert row[4] is not None  # gct_std

        # VO stats: mean([7.22, 7.07, 7.16, 7.09]) = 7.135
        assert abs(row[8] - 7.135) < 0.01  # vo_average
        assert abs(row[9] - 7.07) < 0.01  # vo_min
        assert abs(row[10] - 7.22) < 0.01  # vo_max
        assert row[11] is not None  # vo_std

        # VR stats: mean([8.78, 8.68, 8.64, 8.68]) = 8.695
        assert abs(row[15] - 8.695) < 0.01  # vr_average
        assert abs(row[16] - 8.64) < 0.01  # vr_min
        assert abs(row[17] - 8.78) < 0.01  # vr_max
        assert row[18] is not None  # vr_std

        conn.close()

    @pytest.fixture
    def sample_splits_file(self, tmp_path):
        """Create sample splits.json file with form metrics."""
        splits_data = {
            "activityId": 20636804823,
            "lapDTOs": [
                {
                    "groundContactTime": 251.4,
                    "verticalOscillation": 7.22,
                    "verticalRatio": 8.78,
                    "distance": 1000.0,
                },
                {
                    "groundContactTime": 249.3,
                    "verticalOscillation": 7.07,
                    "verticalRatio": 8.68,
                    "distance": 1000.0,
                },
                {
                    "groundContactTime": 249.3,
                    "verticalOscillation": 7.16,
                    "verticalRatio": 8.64,
                    "distance": 1000.0,
                },
                {
                    "groundContactTime": 249.5,
                    "verticalOscillation": 7.09,
                    "verticalRatio": 8.68,
                    "distance": 1000.0,
                },
            ],
        }

        splits_file = tmp_path / "splits.json"
        with open(splits_file, "w", encoding="utf-8") as f:
            json.dump(splits_data, f, ensure_ascii=False, indent=2)

        return splits_file

    @pytest.mark.unit
    def test_insert_form_efficiency_raw_data_success(
        self, sample_splits_file, tmp_path
    ):
        """Test insert_form_efficiency with raw data."""
        db_path = tmp_path / "test.duckdb"

        result = insert_form_efficiency(
            activity_id=20636804823,
            db_path=str(db_path),
            raw_splits_file=str(sample_splits_file),
        )

        assert result is True
        assert db_path.exists()

    @pytest.mark.integration
    def test_insert_form_efficiency_raw_data_db_integration(
        self, sample_splits_file, tmp_path
    ):
        """Test insert_form_efficiency with raw data actually writes to DuckDB."""
        import duckdb

        db_path = tmp_path / "test.duckdb"

        result = insert_form_efficiency(
            activity_id=20636804823,
            db_path=str(db_path),
            raw_splits_file=str(sample_splits_file),
        )

        assert result is True

        # Verify data in DuckDB
        conn = duckdb.connect(str(db_path))

        # Check form_efficiency data
        form_eff = conn.execute(
            "SELECT * FROM form_efficiency WHERE activity_id = 20636804823"
        ).fetchall()
        assert len(form_eff) == 1

        # Verify calculated statistics
        row = form_eff[0]
        assert row[0] == 20636804823  # activity_id

        # GCT stats: mean([251.4, 249.3, 249.3, 249.5]) = 249.875
        assert abs(row[1] - 249.875) < 0.01  # gct_average
        assert abs(row[2] - 249.3) < 0.01  # gct_min
        assert abs(row[3] - 251.4) < 0.01  # gct_max
        assert row[4] is not None  # gct_std

        # VO stats: mean([7.22, 7.07, 7.16, 7.09]) = 7.135
        assert abs(row[8] - 7.135) < 0.01  # vo_average
        assert abs(row[9] - 7.07) < 0.01  # vo_min
        assert abs(row[10] - 7.22) < 0.01  # vo_max
        assert row[11] is not None  # vo_std

        # VR stats: mean([8.78, 8.68, 8.64, 8.68]) = 8.695
        assert abs(row[15] - 8.695) < 0.01  # vr_average
        assert abs(row[16] - 8.64) < 0.01  # vr_min
        assert abs(row[17] - 8.78) < 0.01  # vr_max
        assert row[18] is not None  # vr_std

        conn.close()

    @pytest.mark.unit
    def test_insert_form_efficiency_raw_data_missing_file(self, tmp_path):
        """Test insert_form_efficiency handles missing files."""
        db_path = tmp_path / "test.duckdb"

        result = insert_form_efficiency(
            activity_id=12345,
            db_path=str(db_path),
            raw_splits_file="/nonexistent/splits.json",
        )

        assert result is False

    @pytest.mark.unit
    def test_calculate_gct_evaluation(self):
        """Test GCT (ground contact time) evaluation."""
        from garmin_mcp.database.inserters.form_efficiency import (
            _calculate_gct_evaluation,
        )

        # Test optimal range (200-250ms)
        assert _calculate_gct_evaluation(220) == "Excellent (220ms, optimal range)"
        assert _calculate_gct_evaluation(200) == "Excellent (200ms, optimal range)"
        assert _calculate_gct_evaluation(250) == "Excellent (250ms, optimal range)"

        # Test good range (180-200 or 250-280)
        assert _calculate_gct_evaluation(190) == "Good (190ms)"
        assert _calculate_gct_evaluation(260) == "Good (260ms)"

        # Test too short (<180ms)
        assert (
            _calculate_gct_evaluation(170)
            == "Too short (170ms, may indicate overstriding)"
        )

        # Test too long (>280ms)
        assert _calculate_gct_evaluation(290) == "Too long (290ms, target <250ms)"

        # Test None handling
        assert _calculate_gct_evaluation(None) is None

    @pytest.mark.unit
    def test_calculate_vo_evaluation(self):
        """Test vertical oscillation evaluation."""
        from garmin_mcp.database.inserters.form_efficiency import (
            _calculate_vo_evaluation,
        )

        # Test excellent (<8cm)
        assert _calculate_vo_evaluation(7.5) == "Excellent (7.5cm, minimal bounce)"

        # Test good (8-10cm)
        assert (
            _calculate_vo_evaluation(8.2)
            == "Good (8.2cm, target <8cm for optimal efficiency)"
        )
        assert (
            _calculate_vo_evaluation(9.5)
            == "Good (9.5cm, target <8cm for optimal efficiency)"
        )

        # Test acceptable (10-12cm)
        assert _calculate_vo_evaluation(11.0) == "Acceptable (11.0cm, reduce bounce)"

        # Test poor (>12cm)
        assert (
            _calculate_vo_evaluation(13.5)
            == "Poor (13.5cm, excessive vertical movement)"
        )

        # Test None handling
        assert _calculate_vo_evaluation(None) is None

    @pytest.mark.unit
    def test_calculate_vr_evaluation(self):
        """Test vertical ratio evaluation."""
        from garmin_mcp.database.inserters.form_efficiency import (
            _calculate_vr_evaluation,
        )

        # Test excellent (<6%)
        assert _calculate_vr_evaluation(5.2) == "Excellent (5.2%, optimal efficiency)"

        # Test good (6-8%)
        assert _calculate_vr_evaluation(6.8) == "Good (6.8%)"
        assert _calculate_vr_evaluation(7.5) == "Good (7.5%)"

        # Test acceptable (8-10%)
        assert (
            _calculate_vr_evaluation(9.0) == "Acceptable (9.0%, room for improvement)"
        )

        # Test poor (>10%)
        assert _calculate_vr_evaluation(11.5) == "Poor (11.5%, high energy waste)"

        # Test None handling
        assert _calculate_vr_evaluation(None) is None

    @pytest.mark.unit
    def test_calculate_vo_trend(self, mocker):
        """Test vertical oscillation trend analysis.

        Note: This requires DB connection, so we mock it for unit testing.
        """
        from garmin_mcp.database.inserters.form_efficiency import _calculate_vo_trend

        # Mock DuckDB connection
        mock_conn = mocker.Mock()

        # Test case 1: Stable VO with low coefficient of variation
        mock_conn.execute.return_value.fetchall.return_value = [
            (8.5,),
            (8.4,),
            (8.6,),
            (8.5,),
            (8.5,),
            (8.4,),
        ]
        result = _calculate_vo_trend(12345, 8.5, mock_conn)
        assert result is not None
        assert "Stable" in result or "Very stable" in result
        assert "8.5cm" in result
        assert "consistent" in result

        # Test case 2: Increasing VO (fatigue)
        mock_conn.execute.return_value.fetchall.return_value = [
            (8.0,),
            (8.2,),
            (8.5,),
            (9.0,),
            (9.5,),
            (10.0,),
        ]
        result = _calculate_vo_trend(12345, 8.9, mock_conn)
        assert result is not None
        assert "increasing" in result
        assert "fatigue indicator" in result

        # Test case 3: Insufficient data
        mock_conn.execute.return_value.fetchall.return_value = [(8.5,), (8.6,)]
        result = _calculate_vo_trend(12345, 8.5, mock_conn)
        assert result == "Insufficient data (2 splits)"

        # Test case 4: None handling
        result = _calculate_vo_trend(12345, None, mock_conn)
        assert result is None
