"""
Tests for GarminDBReader

Test coverage:
- get_splits_pace_hr: Retrieve pace and HR data from splits
- get_splits_form_metrics: Retrieve form metrics (GCT, VO, VR) from splits
- get_splits_elevation: Retrieve elevation data from splits
"""

import pytest

from tools.database.db_reader import GarminDBReader


class TestGarminDBReader:
    """Test suite for GarminDBReader."""

    @pytest.fixture
    def db_reader(self, tmp_path):
        """Create GarminDBReader with test database."""
        db_path = tmp_path / "test.duckdb"

        # Create test performance.json file with split data
        performance_file = tmp_path / "20615445009.json"
        import json

        performance_data = {
            "split_metrics": [
                {
                    "split_number": 1,
                    "distance_km": 1.0,
                    "avg_pace_seconds_per_km": 420,
                    "avg_heart_rate": 145,
                    "ground_contact_time_ms": 250,
                    "vertical_oscillation_cm": 7.5,
                    "vertical_ratio_percent": 8.5,
                    "elevation_gain_m": 5,
                    "elevation_loss_m": 2,
                    "max_elevation_m": 10,
                    "min_elevation_m": 8,
                    "terrain_type": "平坦",
                },
                {
                    "split_number": 2,
                    "distance_km": 1.0,
                    "avg_pace_seconds_per_km": 315,
                    "avg_heart_rate": 155,
                    "ground_contact_time_ms": 245,
                    "vertical_oscillation_cm": 7.2,
                    "vertical_ratio_percent": 8.2,
                    "elevation_gain_m": 8,
                    "elevation_loss_m": 3,
                    "max_elevation_m": 12,
                    "min_elevation_m": 9,
                    "terrain_type": "起伏",
                },
            ]
        }

        with open(performance_file, "w") as f:
            json.dump(performance_data, f)

        # Insert splits into DuckDB using splits inserter
        from tools.database.inserters.splits import insert_splits

        insert_splits(
            performance_file=str(performance_file),
            activity_id=20615445009,
            db_path=str(db_path),
        )

        return GarminDBReader(db_path=str(db_path))

    @pytest.mark.unit
    def test_get_splits_pace_hr_success(self, db_reader):
        """Test get_splits_pace_hr returns pace and HR data."""
        result = db_reader.get_splits_pace_hr(20615445009)

        assert "splits" in result
        assert len(result["splits"]) == 2

        # Check first split
        split1 = result["splits"][0]
        assert split1["split_number"] == 1
        assert split1["distance_km"] == 1.0
        assert split1["avg_pace_seconds_per_km"] == 420
        assert split1["avg_heart_rate"] == 145

        # Check second split
        split2 = result["splits"][1]
        assert split2["split_number"] == 2
        assert split2["distance_km"] == 1.0
        assert split2["avg_pace_seconds_per_km"] == 315
        assert split2["avg_heart_rate"] == 155

    @pytest.mark.unit
    def test_get_splits_form_metrics_success(self, db_reader):
        """Test get_splits_form_metrics returns form metrics."""
        result = db_reader.get_splits_form_metrics(20615445009)

        assert "splits" in result
        assert len(result["splits"]) == 2

        # Check first split
        split1 = result["splits"][0]
        assert split1["split_number"] == 1
        assert split1["ground_contact_time_ms"] == 250
        assert split1["vertical_oscillation_cm"] == 7.5
        assert split1["vertical_ratio_percent"] == 8.5

        # Check second split
        split2 = result["splits"][1]
        assert split2["split_number"] == 2
        assert split2["ground_contact_time_ms"] == 245
        assert split2["vertical_oscillation_cm"] == 7.2
        assert split2["vertical_ratio_percent"] == 8.2

    @pytest.mark.unit
    def test_get_splits_elevation_success(self, db_reader):
        """Test get_splits_elevation returns elevation data."""
        result = db_reader.get_splits_elevation(20615445009)

        assert "splits" in result
        assert len(result["splits"]) == 2

        # Check first split
        split1 = result["splits"][0]
        assert split1["split_number"] == 1
        assert split1["elevation_gain_m"] == 5
        assert split1["elevation_loss_m"] == 2
        assert split1["max_elevation_m"] is None  # Not available in splits table
        assert split1["min_elevation_m"] is None  # Not available in splits table
        assert split1["terrain_type"] == "平坦"

        # Check second split
        split2 = result["splits"][1]
        assert split2["split_number"] == 2
        assert split2["elevation_gain_m"] == 8
        assert split2["elevation_loss_m"] == 3
        assert split2["max_elevation_m"] is None  # Not available in splits table
        assert split2["min_elevation_m"] is None  # Not available in splits table
        assert split2["terrain_type"] == "起伏"

    @pytest.mark.unit
    def test_get_splits_pace_hr_nonexistent_activity(self, db_reader):
        """Test get_splits_pace_hr with nonexistent activity returns empty."""
        result = db_reader.get_splits_pace_hr(99999)

        assert "splits" in result
        assert len(result["splits"]) == 0

    @pytest.mark.unit
    def test_get_splits_form_metrics_nonexistent_activity(self, db_reader):
        """Test get_splits_form_metrics with nonexistent activity returns empty."""
        result = db_reader.get_splits_form_metrics(99999)

        assert "splits" in result
        assert len(result["splits"]) == 0

    @pytest.mark.unit
    def test_get_splits_elevation_nonexistent_activity(self, db_reader):
        """Test get_splits_elevation with nonexistent activity returns empty."""
        result = db_reader.get_splits_elevation(99999)

        assert "splits" in result
        assert len(result["splits"]) == 0

    @pytest.mark.unit
    def test_get_performance_trends_3phase(self, tmp_path):
        """Test get_performance_trends returns 3-phase (warmup/run/cooldown) data."""
        db_path = tmp_path / "test_trends.duckdb"

        # Create test database with performance_trends data (3-phase run)
        import duckdb

        conn = duckdb.connect(str(db_path))

        conn.execute(
            """
            CREATE TABLE performance_trends (
                activity_id BIGINT PRIMARY KEY,
                pace_consistency DOUBLE,
                hr_drift_percentage DOUBLE,
                cadence_consistency VARCHAR,
                fatigue_pattern VARCHAR,
                warmup_splits VARCHAR,
                warmup_avg_pace_seconds_per_km DOUBLE,
                warmup_avg_hr DOUBLE,
                run_splits VARCHAR,
                run_avg_pace_seconds_per_km DOUBLE,
                run_avg_hr DOUBLE,
                recovery_splits VARCHAR,
                recovery_avg_pace_seconds_per_km DOUBLE,
                recovery_avg_hr DOUBLE,
                cooldown_splits VARCHAR,
                cooldown_avg_pace_seconds_per_km DOUBLE,
                cooldown_avg_hr DOUBLE
            )
        """
        )

        # Insert 3-phase run data (no recovery phase)
        conn.execute(
            """
            INSERT INTO performance_trends VALUES (
                12345678901,
                5.2,
                3.5,
                '高い安定性',
                '適切な疲労管理',
                '[1, 2]',
                420.0,
                145.0,
                '[3, 4, 5]',
                360.0,
                165.0,
                NULL,
                NULL,
                NULL,
                '[6]',
                390.0,
                150.0
            )
        """
        )

        conn.close()

        reader = GarminDBReader(db_path=str(db_path))
        result = reader.get_performance_trends(12345678901)

        assert result is not None
        assert result["pace_consistency"] == 5.2
        assert result["hr_drift_percentage"] == 3.5
        assert result["cadence_consistency"] == "高い安定性"
        assert result["fatigue_pattern"] == "適切な疲労管理"

        # Check warmup phase
        assert "warmup_phase" in result
        assert result["warmup_phase"]["splits"] == [1, 2]
        assert result["warmup_phase"]["avg_pace"] == 420.0
        assert result["warmup_phase"]["avg_hr"] == 145.0

        # Check run phase
        assert "run_phase" in result
        assert result["run_phase"]["splits"] == [3, 4, 5]
        assert result["run_phase"]["avg_pace"] == 360.0
        assert result["run_phase"]["avg_hr"] == 165.0

        # Check cooldown phase
        assert "cooldown_phase" in result
        assert result["cooldown_phase"]["splits"] == [6]
        assert result["cooldown_phase"]["avg_pace"] == 390.0
        assert result["cooldown_phase"]["avg_hr"] == 150.0

        # 3-phase run should NOT have recovery phase
        assert "recovery_phase" not in result

    @pytest.mark.unit
    def test_get_performance_trends_4phase(self, tmp_path):
        """Test get_performance_trends returns 4-phase (warmup/run/recovery/cooldown) data."""
        db_path = tmp_path / "test_trends.duckdb"

        # Create test database with performance_trends data (4-phase interval training)
        import duckdb

        conn = duckdb.connect(str(db_path))

        conn.execute(
            """
            CREATE TABLE performance_trends (
                activity_id BIGINT PRIMARY KEY,
                pace_consistency DOUBLE,
                hr_drift_percentage DOUBLE,
                cadence_consistency VARCHAR,
                fatigue_pattern VARCHAR,
                warmup_splits VARCHAR,
                warmup_avg_pace_seconds_per_km DOUBLE,
                warmup_avg_hr DOUBLE,
                run_splits VARCHAR,
                run_avg_pace_seconds_per_km DOUBLE,
                run_avg_hr DOUBLE,
                recovery_splits VARCHAR,
                recovery_avg_pace_seconds_per_km DOUBLE,
                recovery_avg_hr DOUBLE,
                cooldown_splits VARCHAR,
                cooldown_avg_pace_seconds_per_km DOUBLE,
                cooldown_avg_hr DOUBLE
            )
        """
        )

        # Insert 4-phase interval training data
        conn.execute(
            """
            INSERT INTO performance_trends VALUES (
                20615445009,
                8.5,
                5.2,
                '変動あり',
                '軽度の疲労蓄積',
                '[1]',
                480.0,
                135.0,
                '[2, 4, 6]',
                300.0,
                175.0,
                '[3, 5]',
                540.0,
                140.0,
                '[7]',
                450.0,
                145.0
            )
        """
        )

        conn.close()

        reader = GarminDBReader(db_path=str(db_path))
        result = reader.get_performance_trends(20615445009)

        assert result is not None

        # 4-phase interval training MUST have recovery phase
        assert "recovery_phase" in result
        assert result["recovery_phase"]["splits"] == [3, 5]
        assert result["recovery_phase"]["avg_pace"] == 540.0
        assert result["recovery_phase"]["avg_hr"] == 140.0

    @pytest.mark.unit
    def test_get_performance_trends_not_found(self, tmp_path):
        """Test get_performance_trends returns None for nonexistent activity."""
        db_path = tmp_path / "test_trends.duckdb"

        # Create empty database
        import duckdb

        conn = duckdb.connect(str(db_path))
        conn.execute(
            """
            CREATE TABLE performance_trends (
                activity_id BIGINT PRIMARY KEY,
                pace_consistency DOUBLE,
                hr_drift_percentage DOUBLE,
                cadence_consistency VARCHAR,
                fatigue_pattern VARCHAR,
                warmup_splits VARCHAR,
                warmup_avg_pace_seconds_per_km DOUBLE,
                warmup_avg_hr DOUBLE,
                run_splits VARCHAR,
                run_avg_pace_seconds_per_km DOUBLE,
                run_avg_hr DOUBLE,
                recovery_splits VARCHAR,
                recovery_avg_pace_seconds_per_km DOUBLE,
                recovery_avg_hr DOUBLE,
                cooldown_splits VARCHAR,
                cooldown_avg_pace_seconds_per_km DOUBLE,
                cooldown_avg_hr DOUBLE
            )
        """
        )
        conn.close()

        reader = GarminDBReader(db_path=str(db_path))
        result = reader.get_performance_trends(99999999999)

        assert result is None

    @pytest.mark.unit
    def test_get_weather_data_success(self, tmp_path):
        """Test get_weather_data returns weather data from activities table."""
        db_path = tmp_path / "test_weather.duckdb"

        # Create test database with activities data
        import duckdb

        conn = duckdb.connect(str(db_path))

        conn.execute(
            """
            CREATE TABLE activities (
                activity_id BIGINT PRIMARY KEY,
                date DATE,
                name VARCHAR,
                distance DOUBLE,
                duration DOUBLE,
                external_temp_c DOUBLE,
                external_temp_f DOUBLE,
                humidity INTEGER,
                wind_speed_ms DOUBLE,
                wind_direction_compass VARCHAR
            )
        """
        )

        # Insert activity with weather data
        conn.execute(
            """
            INSERT INTO activities VALUES (
                12345678901,
                '2025-10-12',
                'Morning Run',
                10.0,
                3600.0,
                18.5,
                65.3,
                75,
                2.5,
                'NE'
            )
        """
        )

        conn.close()

        reader = GarminDBReader(db_path=str(db_path))
        result = reader.get_weather_data(12345678901)

        assert result is not None
        assert result["temperature_c"] == 18.5
        assert result["temperature_f"] == 65.3
        assert result["humidity"] == 75
        assert result["wind_speed_ms"] == 2.5
        assert result["wind_direction"] == "NE"

    @pytest.mark.unit
    def test_get_weather_data_not_found(self, tmp_path):
        """Test get_weather_data returns None for nonexistent activity."""
        db_path = tmp_path / "test_weather.duckdb"

        # Create empty database
        import duckdb

        conn = duckdb.connect(str(db_path))
        conn.execute(
            """
            CREATE TABLE activities (
                activity_id BIGINT PRIMARY KEY,
                date DATE,
                name VARCHAR,
                distance DOUBLE,
                duration DOUBLE,
                external_temp_c DOUBLE,
                external_temp_f DOUBLE,
                humidity INTEGER,
                wind_speed_ms DOUBLE,
                wind_direction_compass VARCHAR
            )
        """
        )
        conn.close()

        reader = GarminDBReader(db_path=str(db_path))
        result = reader.get_weather_data(99999999999)

        assert result is None
