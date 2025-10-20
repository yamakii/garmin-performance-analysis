"""
Tests for GarminDBReader statistics_only mode

Test coverage:
- get_splits_pace_hr with statistics_only parameter
- get_splits_form_metrics with statistics_only parameter
- get_splits_elevation with statistics_only parameter
"""

import json

import pytest

from tools.database.db_reader import GarminDBReader


class TestGarminDBReaderStatistics:
    """Test suite for GarminDBReader statistics_only mode."""

    @pytest.fixture
    def db_reader(self, tmp_path):
        """Create GarminDBReader with test database containing multiple splits."""
        db_path = tmp_path / "test.duckdb"

        # Create test splits.json file (raw data format) with 10 splits
        splits_file = tmp_path / "splits.json"
        splits_data = {
            "activityId": 20615445009,
            "lapDTOs": [
                {
                    "lapIndex": i,
                    "distance": 1000.0,  # meters
                    "duration": 300 + i * 10,  # seconds: 310, 320, 330, ...
                    "averageHR": 150 + i * 2,  # 152, 154, 156, ...
                    "averageRunCadence": 170,
                    "groundContactTime": 240 + i * 2,  # 242, 244, 246, ...
                    "verticalOscillation": 7.0 + i * 0.2,  # cm: 7.2, 7.4, 7.6, ...
                    "verticalRatio": 8.0 + i * 0.1,  # %: 8.1, 8.2, 8.3, ...
                    "elevationGain": 5 + i,  # 6, 7, 8, ...
                    "elevationLoss": 2 + i * 0.5,  # 2.5, 3.0, 3.5, ...
                }
                for i in range(1, 11)
            ],
        }

        with open(splits_file, "w") as f:
            json.dump(splits_data, f)

        # Insert splits into DuckDB
        from tools.database.inserters.splits import insert_splits

        insert_splits(
            activity_id=20615445009,
            db_path=str(db_path),
            raw_splits_file=str(splits_file),
        )

        return GarminDBReader(db_path=str(db_path))

    # ========== get_splits_pace_hr tests ==========

    @pytest.mark.unit
    def test_get_splits_pace_hr_default_full_mode(self, db_reader):
        """Test get_splits_pace_hr returns full split data by default."""
        result = db_reader.get_splits_pace_hr(20615445009)

        assert "splits" in result
        assert len(result["splits"]) == 10
        assert "statistics_only" not in result

        # Verify first split has full data
        split1 = result["splits"][0]
        assert split1["split_number"] == 1
        assert split1["distance_km"] == 1.0
        assert split1["avg_pace_seconds_per_km"] == 310
        assert split1["avg_heart_rate"] == 152

    @pytest.mark.unit
    def test_get_splits_pace_hr_statistics_only_mode(self, db_reader):
        """Test get_splits_pace_hr with statistics_only=True returns aggregated stats."""
        result = db_reader.get_splits_pace_hr(20615445009, statistics_only=True)

        # Check structure
        assert "activity_id" in result
        assert result["activity_id"] == 20615445009
        assert "statistics_only" in result
        assert result["statistics_only"] is True
        assert "metrics" in result

        # Check pace statistics (310, 320, 330, ..., 390)
        pace_stats = result["metrics"]["pace"]
        assert "mean" in pace_stats
        assert "median" in pace_stats
        assert "std" in pace_stats
        assert "min" in pace_stats
        assert "max" in pace_stats

        # Verify approximate values (mean of 310,320,...,400 = 355)
        assert 350 <= pace_stats["mean"] <= 360
        assert pace_stats["min"] == 310
        assert pace_stats["max"] == 400
        assert pace_stats["median"] > 0

        # Check heart_rate statistics (152, 154, 156, ..., 170)
        hr_stats = result["metrics"]["heart_rate"]
        assert 158 <= hr_stats["mean"] <= 164
        assert hr_stats["min"] == 152
        assert hr_stats["max"] == 170

    @pytest.mark.unit
    def test_get_splits_pace_hr_statistics_only_size_reduction(self, db_reader):
        """Test that statistics_only mode significantly reduces output size."""
        full_result = db_reader.get_splits_pace_hr(20615445009, statistics_only=False)
        stats_result = db_reader.get_splits_pace_hr(20615445009, statistics_only=True)

        full_size = len(json.dumps(full_result))
        stats_size = len(json.dumps(stats_result))

        # Statistics mode should be at least 50% smaller
        assert stats_size < full_size * 0.5
        # Statistics output should be < 500 bytes
        assert stats_size < 500

    # ========== get_splits_form_metrics tests ==========

    @pytest.mark.unit
    def test_get_splits_form_metrics_default_full_mode(self, db_reader):
        """Test get_splits_form_metrics returns full split data by default."""
        result = db_reader.get_splits_form_metrics(20615445009)

        assert "splits" in result
        assert len(result["splits"]) == 10
        assert "statistics_only" not in result

        # Verify first split has full form metrics
        split1 = result["splits"][0]
        assert split1["split_number"] == 1
        assert split1["ground_contact_time_ms"] == 242
        assert split1["vertical_oscillation_cm"] == 7.2
        assert split1["vertical_ratio_percent"] == 8.1

    @pytest.mark.unit
    def test_get_splits_form_metrics_statistics_only_mode(self, db_reader):
        """Test get_splits_form_metrics with statistics_only=True returns aggregated stats."""
        result = db_reader.get_splits_form_metrics(20615445009, statistics_only=True)

        # Check structure
        assert "activity_id" in result
        assert result["activity_id"] == 20615445009
        assert "statistics_only" in result
        assert result["statistics_only"] is True
        assert "metrics" in result

        # Check GCT statistics (242, 244, 246, ..., 260)
        gct_stats = result["metrics"]["ground_contact_time"]
        assert "mean" in gct_stats
        assert "median" in gct_stats
        assert "std" in gct_stats
        assert "min" in gct_stats
        assert "max" in gct_stats
        assert 248 <= gct_stats["mean"] <= 254
        assert gct_stats["min"] == 242
        assert gct_stats["max"] == 260

        # Check VO statistics (7.2, 7.4, 7.6, ..., 9.0)
        vo_stats = result["metrics"]["vertical_oscillation"]
        assert 7.8 <= vo_stats["mean"] <= 8.4
        assert vo_stats["min"] == 7.2
        assert vo_stats["max"] == 9.0

        # Check VR statistics (8.1, 8.2, 8.3, ..., 9.0)
        vr_stats = result["metrics"]["vertical_ratio"]
        assert 8.4 <= vr_stats["mean"] <= 8.7
        assert vr_stats["min"] == 8.1
        assert vr_stats["max"] == 9.0

    @pytest.mark.unit
    def test_get_splits_form_metrics_statistics_only_size_reduction(self, db_reader):
        """Test that statistics_only mode significantly reduces output size."""
        full_result = db_reader.get_splits_form_metrics(
            20615445009, statistics_only=False
        )
        stats_result = db_reader.get_splits_form_metrics(
            20615445009, statistics_only=True
        )

        full_size = len(json.dumps(full_result))
        stats_size = len(json.dumps(stats_result))

        # Statistics mode should be at least 50% smaller
        assert stats_size < full_size * 0.5
        # Statistics output should be < 600 bytes
        assert stats_size < 600

    # ========== get_splits_elevation tests ==========

    @pytest.mark.unit
    def test_get_splits_elevation_default_full_mode(self, db_reader):
        """Test get_splits_elevation returns full split data by default."""
        result = db_reader.get_splits_elevation(20615445009)

        assert "splits" in result
        assert len(result["splits"]) == 10
        assert "statistics_only" not in result

        # Verify first split has full elevation data
        split1 = result["splits"][0]
        assert split1["split_number"] == 1
        assert split1["elevation_gain_m"] == 6
        assert split1["elevation_loss_m"] == 2.5

    @pytest.mark.unit
    def test_get_splits_elevation_statistics_only_mode(self, db_reader):
        """Test get_splits_elevation with statistics_only=True returns aggregated stats."""
        result = db_reader.get_splits_elevation(20615445009, statistics_only=True)

        # Check structure
        assert "activity_id" in result
        assert result["activity_id"] == 20615445009
        assert "statistics_only" in result
        assert result["statistics_only"] is True
        assert "metrics" in result

        # Check elevation_gain statistics (6, 7, 8, ..., 15)
        gain_stats = result["metrics"]["elevation_gain"]
        assert "mean" in gain_stats
        assert "median" in gain_stats
        assert "std" in gain_stats
        assert "min" in gain_stats
        assert "max" in gain_stats
        assert 9.5 <= gain_stats["mean"] <= 11.5
        assert gain_stats["min"] == 6
        assert gain_stats["max"] == 15

        # Check elevation_loss statistics (2.5, 3.0, 3.5, ..., 7.0)
        loss_stats = result["metrics"]["elevation_loss"]
        assert 4.0 <= loss_stats["mean"] <= 5.5
        assert loss_stats["min"] == 2.5
        assert loss_stats["max"] == 7.0

    @pytest.mark.unit
    def test_get_splits_elevation_statistics_only_size_reduction(self, db_reader):
        """Test that statistics_only mode significantly reduces output size."""
        full_result = db_reader.get_splits_elevation(20615445009, statistics_only=False)
        stats_result = db_reader.get_splits_elevation(20615445009, statistics_only=True)

        full_size = len(json.dumps(full_result))
        stats_size = len(json.dumps(stats_result))

        # Statistics mode should be at least 50% smaller
        assert stats_size < full_size * 0.5
        # Statistics output should be < 500 bytes
        assert stats_size < 500

    # ========== Backward compatibility tests ==========

    @pytest.mark.unit
    def test_backward_compatibility_default_false(self, db_reader):
        """Test that statistics_only defaults to False for backward compatibility."""
        # Call without statistics_only parameter
        result1 = db_reader.get_splits_pace_hr(20615445009)
        result2 = db_reader.get_splits_pace_hr(20615445009, statistics_only=False)

        # Both should return full data
        assert result1 == result2
        assert "splits" in result1
        assert len(result1["splits"]) == 10

    @pytest.mark.unit
    def test_empty_activity_statistics_mode(self, db_reader):
        """Test statistics_only mode with non-existent activity."""
        result = db_reader.get_splits_pace_hr(99999999, statistics_only=True)

        # Should return structure with empty metrics
        assert "activity_id" in result
        assert result["activity_id"] == 99999999
        assert "statistics_only" in result
        assert result["statistics_only"] is True
        assert "metrics" in result

    # ========== get_splits_comprehensive tests ==========

    @pytest.mark.unit
    def test_get_splits_comprehensive_default_full_mode(self, db_reader):
        """Test get_splits_comprehensive returns full split data by default."""
        result = db_reader.get_splits_comprehensive(20615445009)

        assert "splits" in result
        assert len(result["splits"]) == 10
        assert "statistics_only" not in result

        # Verify first split has all 12 comprehensive fields
        split1 = result["splits"][0]
        assert split1["split_number"] == 1
        assert split1["distance_km"] == 1.0
        # Pace & HR fields
        assert split1["avg_pace_seconds_per_km"] == 310
        assert split1["avg_heart_rate"] == 152
        # max_heart_rate may be None if not in raw data
        assert "max_heart_rate_bpm" in split1
        # Form fields
        assert split1["ground_contact_time_ms"] == 242
        assert split1["vertical_oscillation_cm"] == 7.2
        assert split1["vertical_ratio_percent"] == 8.1
        # Power & rhythm fields (some may be None/0)
        assert "power_watts" in split1
        assert "stride_length_cm" in split1
        assert "cadence_spm" in split1
        assert "max_cadence_spm" in split1
        # Elevation fields
        assert split1["elevation_gain_m"] == 6
        assert split1["elevation_loss_m"] == 2.5

    @pytest.mark.unit
    def test_get_splits_comprehensive_statistics_only_mode(self, db_reader):
        """Test get_splits_comprehensive with statistics_only=True returns aggregated stats."""
        result = db_reader.get_splits_comprehensive(20615445009, statistics_only=True)

        # Check structure
        assert "activity_id" in result
        assert result["activity_id"] == 20615445009
        assert "statistics_only" in result
        assert result["statistics_only"] is True
        assert "metrics" in result

        # Check all 12 metrics are present
        expected_metrics = [
            "pace",
            "heart_rate",
            "ground_contact_time",
            "vertical_oscillation",
            "vertical_ratio",
            "power",
            "stride_length",
            "cadence",
            "elevation_gain",
            "elevation_loss",
            "max_heart_rate",
            "max_cadence",
        ]

        for metric in expected_metrics:
            assert metric in result["metrics"], f"Missing metric: {metric}"
            stats = result["metrics"][metric]
            assert "mean" in stats
            assert "median" in stats
            assert "std" in stats
            assert "min" in stats
            assert "max" in stats

        # Check specific values for pace (310, 320, 330, ..., 400)
        pace_stats = result["metrics"]["pace"]
        assert 350 <= pace_stats["mean"] <= 360
        assert pace_stats["min"] == 310
        assert pace_stats["max"] == 400

        # Check heart_rate statistics (152, 154, 156, ..., 170)
        hr_stats = result["metrics"]["heart_rate"]
        assert 158 <= hr_stats["mean"] <= 164
        assert hr_stats["min"] == 152
        assert hr_stats["max"] == 170

    @pytest.mark.unit
    def test_get_splits_comprehensive_statistics_only_size_reduction(self, db_reader):
        """Test that statistics_only mode significantly reduces output size (~80%)."""
        full_result = db_reader.get_splits_comprehensive(
            20615445009, statistics_only=False
        )
        stats_result = db_reader.get_splits_comprehensive(
            20615445009, statistics_only=True
        )

        full_size = len(json.dumps(full_result))
        stats_size = len(json.dumps(stats_result))

        # Statistics mode should be at least 60% smaller (40% of original or less)
        # With 12 fields, expect ~67% reduction (33% of original size)
        assert stats_size < full_size * 0.4
        # Statistics output should be < 1500 bytes (12 metrics * 5 stats * ~25 bytes)
        assert stats_size < 1500

    @pytest.mark.unit
    def test_get_splits_comprehensive_backward_compatibility(self, db_reader):
        """Test that statistics_only defaults to False for backward compatibility."""
        result1 = db_reader.get_splits_comprehensive(20615445009)
        result2 = db_reader.get_splits_comprehensive(20615445009, statistics_only=False)

        # Both should return full data
        assert result1 == result2
        assert "splits" in result1
        assert len(result1["splits"]) == 10

    @pytest.mark.unit
    def test_get_splits_comprehensive_empty_activity(self, db_reader):
        """Test get_splits_comprehensive with non-existent activity."""
        # Full mode
        result_full = db_reader.get_splits_comprehensive(
            99999999, statistics_only=False
        )
        assert "splits" in result_full
        assert result_full["splits"] == []

        # Statistics mode
        result_stats = db_reader.get_splits_comprehensive(
            99999999, statistics_only=True
        )
        assert "activity_id" in result_stats
        assert result_stats["activity_id"] == 99999999
        assert "statistics_only" in result_stats
        assert result_stats["statistics_only"] is True
        assert "metrics" in result_stats
        assert result_stats["metrics"] == {}
        # Metrics should be empty or have null values
