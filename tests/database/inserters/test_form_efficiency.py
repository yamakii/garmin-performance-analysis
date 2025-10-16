"""
Tests for Form Efficiency Inserter

Test coverage:
- Unit tests for insert_form_efficiency function
- Integration tests with DuckDB
"""

import json

import pytest

from tools.database.inserters.form_efficiency import insert_form_efficiency


class TestFormEfficiencyInserter:
    """Test suite for Form Efficiency Inserter."""

    @pytest.fixture
    def sample_performance_file(self, tmp_path):
        """Create sample performance.json file with form_efficiency_summary."""
        performance_data = {
            "basic_metrics": {
                "distance_km": 5.0,
            },
            "form_efficiency_summary": {
                "gct_stats": {
                    "average": 251.45,
                    "min": 218.80,
                    "max": 286.40,
                    "std": 25.32,
                },
                "gct_rating": "★★★☆☆",
                "vo_stats": {
                    "average": 7.21,
                    "min": 5.98,
                    "max": 8.12,
                    "std": 0.76,
                },
                "vo_rating": "★★★★★",
                "vr_stats": {
                    "average": 8.74,
                    "min": 7.05,
                    "max": 10.98,
                    "std": 1.47,
                },
                "vr_rating": "★★★☆☆",
                "evaluation": "優秀な接地時間、効率的な地面反力利用",
            },
        }

        performance_file = tmp_path / "20464005432.json"
        with open(performance_file, "w", encoding="utf-8") as f:
            json.dump(performance_data, f, ensure_ascii=False, indent=2)

        return performance_file

    @pytest.mark.unit
    def test_insert_form_efficiency_success(self, sample_performance_file, tmp_path):
        """Test insert_form_efficiency inserts data successfully."""
        db_path = tmp_path / "test.duckdb"

        result = insert_form_efficiency(
            performance_file=str(sample_performance_file),
            activity_id=20464005432,
            db_path=str(db_path),
        )

        assert result is True
        assert db_path.exists()

    @pytest.mark.unit
    def test_insert_form_efficiency_missing_file(self, tmp_path):
        """Test insert_form_efficiency handles missing file."""
        db_path = tmp_path / "test.duckdb"

        result = insert_form_efficiency(
            performance_file="/nonexistent/file.json",
            activity_id=12345,
            db_path=str(db_path),
        )

        assert result is False

    @pytest.mark.unit
    def test_insert_form_efficiency_no_data(self, tmp_path):
        """Test insert_form_efficiency handles missing form_efficiency_summary."""
        performance_data = {"basic_metrics": {"distance_km": 5.0}}
        performance_file = tmp_path / "test.json"
        with open(performance_file, "w", encoding="utf-8") as f:
            json.dump(performance_data, f)

        db_path = tmp_path / "test.duckdb"

        result = insert_form_efficiency(
            performance_file=str(performance_file),
            activity_id=12345,
            db_path=str(db_path),
        )

        assert result is False

    @pytest.mark.integration
    def test_insert_form_efficiency_db_integration(
        self, sample_performance_file, tmp_path
    ):
        """Test insert_form_efficiency actually writes to DuckDB."""
        import duckdb

        db_path = tmp_path / "test.duckdb"

        result = insert_form_efficiency(
            performance_file=str(sample_performance_file),
            activity_id=20464005432,
            db_path=str(db_path),
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
            "SELECT * FROM form_efficiency WHERE activity_id = 20464005432"
        ).fetchall()
        assert len(form_eff) == 1

        # Verify data values
        row = form_eff[0]
        assert row[0] == 20464005432  # activity_id
        assert abs(row[1] - 251.45) < 0.01  # gct_average
        assert abs(row[2] - 218.80) < 0.01  # gct_min
        assert abs(row[3] - 286.40) < 0.01  # gct_max
        assert abs(row[4] - 25.32) < 0.01  # gct_std
        assert row[6] == "★★★☆☆"  # gct_rating
        assert abs(row[8] - 7.21) < 0.01  # vo_average
        assert row[13] == "★★★★★"  # vo_rating
        assert abs(row[15] - 8.74) < 0.01  # vr_average
        assert row[19] == "★★★☆☆"  # vr_rating

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
        """Test insert_form_efficiency with raw data mode."""
        db_path = tmp_path / "test.duckdb"

        result = insert_form_efficiency(
            performance_file=None,
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
            performance_file=None,
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
        """Test insert_form_efficiency raw mode handles missing files."""
        db_path = tmp_path / "test.duckdb"

        result = insert_form_efficiency(
            performance_file=None,
            activity_id=12345,
            db_path=str(db_path),
            raw_splits_file="/nonexistent/splits.json",
        )

        assert result is False
