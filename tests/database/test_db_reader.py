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
