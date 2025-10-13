"""Unit tests for GarminDBReader time series methods."""

import duckdb
import pytest

from tools.database.db_reader import GarminDBReader


class TestGarminDBReaderTimeSeries:
    """Test time series query methods in GarminDBReader."""

    @pytest.fixture
    def db_reader(self, tmp_path):
        """Create GarminDBReader with temporary database."""
        db_path = tmp_path / "test_garmin.duckdb"

        # Create test database with time_series_metrics table
        conn = duckdb.connect(str(db_path))

        # Create schema
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS time_series_metrics (
                activity_id BIGINT NOT NULL,
                timestamp_s INTEGER NOT NULL,
                heart_rate DOUBLE,
                speed DOUBLE,
                cadence DOUBLE,
                power DOUBLE,
                ground_contact_time DOUBLE,
                vertical_oscillation DOUBLE,
                vertical_ratio DOUBLE,
                elevation DOUBLE,
                PRIMARY KEY (activity_id, timestamp_s)
            );
        """
        )

        # Insert test data for activity 12345 (100 seconds)
        test_data = []
        for t in range(100):
            # Create anomaly at t=75 (power spike to 500)
            power_value = 250.0
            if t < 50:
                power_value = 250.0
            elif t == 75:
                power_value = 500.0  # Anomaly: 3+ std deviations from mean
            else:
                power_value = 260.0

            test_data.append(
                {
                    "activity_id": 12345,
                    "timestamp_s": t,
                    "heart_rate": 150 + (t % 10),  # Oscillates between 150-159
                    "speed": 3.5 + (t * 0.01),  # Gradually increases
                    "cadence": 180 + (t % 5),  # Oscillates
                    "power": power_value,  # Step change at t=50
                    "ground_contact_time": 200 + (t % 3),
                    "vertical_oscillation": 8.5 + (t * 0.01),
                    "vertical_ratio": 6.0 + (t % 2) * 0.5,
                    "elevation": 100 + (t * 0.5),  # Climbing
                }
            )

        conn.executemany(
            """
            INSERT INTO time_series_metrics VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """,
            [
                (
                    d["activity_id"],
                    d["timestamp_s"],
                    d["heart_rate"],
                    d["speed"],
                    d["cadence"],
                    d["power"],
                    d["ground_contact_time"],
                    d["vertical_oscillation"],
                    d["vertical_ratio"],
                    d["elevation"],
                )
                for d in test_data
            ],
        )

        conn.close()

        # Create reader
        reader = GarminDBReader(db_path=db_path)
        return reader

    def test_get_time_series_statistics_basic(self, db_reader):
        """Test get_time_series_statistics with basic metrics."""
        # Test time range: 0-50 seconds, metrics: heart_rate, speed
        result = db_reader.get_time_series_statistics(
            activity_id=12345,
            start_time_s=0,
            end_time_s=50,
            metrics=["heart_rate", "speed"],
        )

        # Verify structure
        assert "activity_id" in result
        assert result["activity_id"] == 12345
        assert "time_range" in result
        assert result["time_range"]["start_time_s"] == 0
        assert result["time_range"]["end_time_s"] == 50
        assert "statistics" in result
        assert "data_points" in result

        # Verify statistics for heart_rate
        assert "heart_rate" in result["statistics"]
        hr_stats = result["statistics"]["heart_rate"]
        assert "avg" in hr_stats
        assert "std" in hr_stats
        assert "min" in hr_stats
        assert "max" in hr_stats

        # Verify heart_rate values (oscillates 150-159 in pattern)
        assert 150 <= hr_stats["min"] <= 151
        assert 158 <= hr_stats["max"] <= 159
        assert 154 <= hr_stats["avg"] <= 155  # Approximate average

        # Verify speed statistics
        assert "speed" in result["statistics"]
        speed_stats = result["statistics"]["speed"]
        assert speed_stats["min"] == pytest.approx(3.5, rel=0.01)
        assert speed_stats["max"] == pytest.approx(3.99, rel=0.01)

    def test_get_time_series_statistics_multiple_metrics(self, db_reader):
        """Test get_time_series_statistics with multiple form metrics."""
        result = db_reader.get_time_series_statistics(
            activity_id=12345,
            start_time_s=0,
            end_time_s=100,
            metrics=["ground_contact_time", "vertical_oscillation", "vertical_ratio"],
        )

        # Verify all metrics present
        assert len(result["statistics"]) == 3
        assert "ground_contact_time" in result["statistics"]
        assert "vertical_oscillation" in result["statistics"]
        assert "vertical_ratio" in result["statistics"]

        # Verify data points count
        assert result["data_points"] == 100

    def test_get_time_series_statistics_partial_range(self, db_reader):
        """Test get_time_series_statistics with partial time range."""
        # Test second half (50-100s) where power is mostly 260 with spike at t=75
        result = db_reader.get_time_series_statistics(
            activity_id=12345, start_time_s=50, end_time_s=100, metrics=["power"]
        )

        # Power is mostly 260 in this range (with one spike to 500 at t=75)
        power_stats = result["statistics"]["power"]
        # Average: 49 values of 260 + 1 value of 500 = (49*260 + 500)/50 = 264.8
        assert power_stats["avg"] == pytest.approx(264.8, rel=0.01)
        assert power_stats["min"] == 260
        assert power_stats["max"] == 500

    def test_get_time_series_raw_basic(self, db_reader):
        """Test get_time_series_raw basic functionality."""
        result = db_reader.get_time_series_raw(
            activity_id=12345,
            start_time_s=0,
            end_time_s=10,
            metrics=["heart_rate", "speed"],
        )

        # Verify structure
        assert "activity_id" in result
        assert result["activity_id"] == 12345
        assert "time_range" in result
        assert "time_series" in result

        # Verify data points
        assert len(result["time_series"]) == 10

        # Verify first data point
        first_point = result["time_series"][0]
        assert "timestamp_s" in first_point
        assert first_point["timestamp_s"] == 0
        assert "heart_rate" in first_point
        assert first_point["heart_rate"] == 150
        assert "speed" in first_point
        assert first_point["speed"] == pytest.approx(3.5, rel=0.01)

    def test_get_time_series_raw_with_limit(self, db_reader):
        """Test get_time_series_raw with limit parameter."""
        result = db_reader.get_time_series_raw(
            activity_id=12345,
            start_time_s=0,
            end_time_s=100,
            metrics=["cadence"],
            limit=20,
        )

        # Verify limited results
        assert len(result["time_series"]) == 20

    def test_detect_anomalies_sql_basic(self, db_reader):
        """Test detect_anomalies_sql basic functionality."""
        # Power has an anomaly at t=75 (spike to 500)
        # This should be detected as anomaly (z-score > 2.0)
        result = db_reader.detect_anomalies_sql(
            activity_id=12345, metrics=["power"], z_threshold=2.0
        )

        # Verify structure
        assert "activity_id" in result
        assert result["activity_id"] == 12345
        assert "anomalies" in result
        assert "summary" in result

        # Should detect anomalies around the step change
        assert len(result["anomalies"]) > 0

        # Check anomaly structure
        anomaly = result["anomalies"][0]
        assert "timestamp_s" in anomaly
        assert "metric" in anomaly
        assert anomaly["metric"] == "power"
        assert "value" in anomaly
        assert "z_score" in anomaly
        assert abs(anomaly["z_score"]) > 2.0

    def test_detect_anomalies_sql_multiple_metrics(self, db_reader):
        """Test detect_anomalies_sql with multiple metrics."""
        result = db_reader.detect_anomalies_sql(
            activity_id=12345,
            metrics=["ground_contact_time", "vertical_oscillation", "vertical_ratio"],
            z_threshold=2.5,
        )

        # Verify summary counts
        assert "summary" in result
        summary = result["summary"]
        assert "total_anomalies" in summary
        assert "by_metric" in summary

    def test_get_time_series_statistics_nonexistent_activity(self, db_reader):
        """Test get_time_series_statistics with non-existent activity."""
        result = db_reader.get_time_series_statistics(
            activity_id=99999, start_time_s=0, end_time_s=100, metrics=["heart_rate"]
        )

        # Should return error or empty result
        assert result["data_points"] == 0

    def test_get_time_series_raw_empty_range(self, db_reader):
        """Test get_time_series_raw with time range outside data."""
        result = db_reader.get_time_series_raw(
            activity_id=12345, start_time_s=200, end_time_s=300, metrics=["heart_rate"]
        )

        # Should return empty time series
        assert len(result["time_series"]) == 0
