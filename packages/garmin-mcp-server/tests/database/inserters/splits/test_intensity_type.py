"""estimate_intensity_type() and how insert_splits fills, preserves or mixes intensity_type."""

import json

import duckdb
import pytest

from garmin_mcp.database.inserters.splits import insert_splits
from garmin_mcp.database.inserters.splits_helpers.phase_mapping import PhaseMapper


class TestIntensityType:
    @pytest.mark.unit
    def test_estimate_intensity_type_warmup_first_two_splits(self):
        """Test WARMUP estimation for first 2 splits."""

        # Test case 1: 10 splits total (first 2 should be WARMUP)
        splits = [
            {"pace_seconds_per_km": 300, "avg_heart_rate": 140},  # Split 0 → WARMUP
            {"pace_seconds_per_km": 290, "avg_heart_rate": 145},  # Split 1 → WARMUP
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},  # Split 2 → not warmup
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 300, "avg_heart_rate": 140},
            {"pace_seconds_per_km": 310, "avg_heart_rate": 130},
        ]

        result = PhaseMapper.estimate_intensity_type(splits)

        assert result[0] == "WARMUP"
        assert result[1] == "WARMUP"
        assert result[2] != "WARMUP"

    @pytest.mark.unit
    def test_estimate_intensity_type_warmup_single_for_short_run(self):
        """Test WARMUP estimation for short runs (≤6 splits, only first 1)."""

        # Test case: 6 splits total (only first 1 should be WARMUP)
        splits = [
            {"pace_seconds_per_km": 300, "avg_heart_rate": 140},  # Split 0 → WARMUP
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},  # Split 1 → not warmup
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 300, "avg_heart_rate": 140},
        ]

        result = PhaseMapper.estimate_intensity_type(splits)

        assert result[0] == "WARMUP"
        assert result[1] != "WARMUP"

    @pytest.mark.unit
    def test_estimate_intensity_type_cooldown_last_two_splits(self):
        """Test COOLDOWN estimation for last 2 splits."""

        # Test case: 10 splits total (last 2 should be COOLDOWN)
        splits = [
            {"pace_seconds_per_km": 300, "avg_heart_rate": 140},
            {"pace_seconds_per_km": 290, "avg_heart_rate": 145},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 300, "avg_heart_rate": 140},  # Split 8 → COOLDOWN
            {"pace_seconds_per_km": 310, "avg_heart_rate": 130},  # Split 9 → COOLDOWN
        ]

        result = PhaseMapper.estimate_intensity_type(splits)

        assert result[-2] == "COOLDOWN"
        assert result[-1] == "COOLDOWN"
        assert result[-3] != "COOLDOWN"

    @pytest.mark.unit
    def test_estimate_intensity_type_cooldown_single_for_short_run(self):
        """Test COOLDOWN estimation for short runs (≤6 splits, only last 1)."""

        # Test case: 6 splits total (only last 1 should be COOLDOWN)
        splits = [
            {"pace_seconds_per_km": 300, "avg_heart_rate": 140},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 240, "avg_heart_rate": 160},
            {"pace_seconds_per_km": 300, "avg_heart_rate": 140},  # Split 5 → COOLDOWN
        ]

        result = PhaseMapper.estimate_intensity_type(splits)

        assert result[-1] == "COOLDOWN"
        assert result[-2] != "COOLDOWN"

    @pytest.mark.unit
    def test_estimate_intensity_type_recovery_after_interval(self):
        """Test RECOVERY estimation (pace >400 AND previous was INTERVAL/RECOVERY)."""

        # Test case: Sprint pattern (WARMUP, INTERVAL, RECOVERY, INTERVAL, RECOVERY, COOLDOWN)
        splits = [
            {"pace_seconds_per_km": 300, "avg_heart_rate": 140},  # WARMUP
            {"pace_seconds_per_km": 300, "avg_heart_rate": 145},  # WARMUP
            {"pace_seconds_per_km": 210, "avg_heart_rate": 180},  # INTERVAL
            {
                "pace_seconds_per_km": 450,
                "avg_heart_rate": 130,
            },  # RECOVERY (pace >400, prev=INTERVAL)
            {"pace_seconds_per_km": 220, "avg_heart_rate": 185},  # INTERVAL
            {
                "pace_seconds_per_km": 460,
                "avg_heart_rate": 125,
            },  # RECOVERY (pace >400, prev=INTERVAL)
            {"pace_seconds_per_km": 210, "avg_heart_rate": 180},  # INTERVAL
            {
                "pace_seconds_per_km": 420,
                "avg_heart_rate": 120,
            },  # RECOVERY (pace >400, prev=INTERVAL)
            {"pace_seconds_per_km": 310, "avg_heart_rate": 140},  # COOLDOWN
            {"pace_seconds_per_km": 320, "avg_heart_rate": 130},  # COOLDOWN
        ]

        result = PhaseMapper.estimate_intensity_type(splits)

        assert result[0] == "WARMUP"
        assert result[1] == "WARMUP"
        assert result[2] == "INTERVAL"
        assert result[3] == "RECOVERY"  # pace >400, prev=INTERVAL
        assert result[4] == "INTERVAL"
        assert result[5] == "RECOVERY"  # pace >400, prev=INTERVAL
        assert result[6] == "INTERVAL"
        assert result[7] == "RECOVERY"  # pace >400, prev=INTERVAL
        assert result[8] == "COOLDOWN"
        assert result[9] == "COOLDOWN"

    @pytest.mark.unit
    def test_estimate_intensity_type_interval_by_fast_pace(self):
        """Test INTERVAL estimation by fast pace (pace < avg × 0.90)."""

        # Test case: Threshold run (WARMUP, INTERVAL zone, COOLDOWN)
        # Average pace ≈ 260 sec/km, threshold = 234 sec/km
        splits = [
            {"pace_seconds_per_km": 300, "avg_heart_rate": 140},  # WARMUP
            {"pace_seconds_per_km": 300, "avg_heart_rate": 145},  # WARMUP
            {"pace_seconds_per_km": 220, "avg_heart_rate": 175},  # INTERVAL (220 < 234)
            {"pace_seconds_per_km": 230, "avg_heart_rate": 175},  # INTERVAL (230 < 234)
            {"pace_seconds_per_km": 225, "avg_heart_rate": 175},  # INTERVAL (225 < 234)
            {"pace_seconds_per_km": 228, "avg_heart_rate": 175},  # INTERVAL (228 < 234)
            {"pace_seconds_per_km": 300, "avg_heart_rate": 140},  # COOLDOWN
            {"pace_seconds_per_km": 310, "avg_heart_rate": 130},  # COOLDOWN
        ]

        result = PhaseMapper.estimate_intensity_type(splits)

        assert result[0] == "WARMUP"
        assert result[1] == "WARMUP"
        assert result[2] == "INTERVAL"  # Fast pace
        assert result[3] == "INTERVAL"  # Fast pace
        assert result[4] == "INTERVAL"  # Fast pace
        assert result[5] == "INTERVAL"  # Fast pace
        assert result[6] == "COOLDOWN"
        assert result[7] == "COOLDOWN"

    @pytest.mark.unit
    def test_estimate_intensity_type_interval_by_high_hr(self):
        """Test INTERVAL estimation by high HR (HR > avg × 1.1)."""

        # Test case: High HR effort
        # Average HR = 153.75 bpm, threshold = 169.125 bpm
        # Only splits with HR >= 170 qualify as INTERVAL
        splits = [
            {"pace_seconds_per_km": 300, "avg_heart_rate": 140},  # WARMUP
            {"pace_seconds_per_km": 300, "avg_heart_rate": 145},  # WARMUP
            {
                "pace_seconds_per_km": 260,
                "avg_heart_rate": 170,
            },  # INTERVAL (170 > 169.125)
            {
                "pace_seconds_per_km": 260,
                "avg_heart_rate": 172,
            },  # INTERVAL (172 > 169.125)
            {
                "pace_seconds_per_km": 260,
                "avg_heart_rate": 168,
            },  # ACTIVE (168 < 169.125)
            {
                "pace_seconds_per_km": 260,
                "avg_heart_rate": 165,
            },  # ACTIVE (165 < 169.125)
            {"pace_seconds_per_km": 300, "avg_heart_rate": 140},  # COOLDOWN
            {"pace_seconds_per_km": 310, "avg_heart_rate": 130},  # COOLDOWN
        ]

        result = PhaseMapper.estimate_intensity_type(splits)

        assert result[0] == "WARMUP"
        assert result[1] == "WARMUP"
        assert result[2] == "INTERVAL"  # High HR (170 > 169.125)
        assert result[3] == "INTERVAL"  # High HR (172 > 169.125)
        assert result[4] == "ACTIVE"  # HR not high enough (168 < 169.125)
        assert result[5] == "ACTIVE"  # HR not high enough (165 < 169.125)
        assert result[6] == "COOLDOWN"
        assert result[7] == "COOLDOWN"

    @pytest.mark.unit
    def test_estimate_intensity_type_active_default(self):
        """Test ACTIVE estimation as default (doesn't match other rules)."""

        # Test case: Easy run (moderate pace, moderate HR)
        # With 4 splits (≤6), expect: WARMUP, ACTIVE, ACTIVE, COOLDOWN
        splits = [
            {"pace_seconds_per_km": 270, "avg_heart_rate": 145},  # WARMUP (position)
            {"pace_seconds_per_km": 275, "avg_heart_rate": 147},  # ACTIVE
            {"pace_seconds_per_km": 268, "avg_heart_rate": 144},  # ACTIVE
            {"pace_seconds_per_km": 272, "avg_heart_rate": 146},  # COOLDOWN (position)
        ]

        result = PhaseMapper.estimate_intensity_type(splits)

        # Position-based rules apply first for runs ≤6 splits
        assert result[0] == "WARMUP"  # First split
        assert result[1] == "ACTIVE"  # Middle splits
        assert result[2] == "ACTIVE"  # Middle splits
        assert result[3] == "COOLDOWN"  # Last split

    @pytest.mark.unit
    def test_estimate_intensity_type_missing_hr_values(self):
        """Test estimation handles missing HR values gracefully."""

        # Test case: Some splits without HR data (6 splits total)
        # With 6 splits (≤6): WARMUP (1), middle (4), COOLDOWN (1)
        splits: list[dict] = [
            {"pace_seconds_per_km": 300, "avg_heart_rate": 140},  # WARMUP (position)
            {
                "pace_seconds_per_km": 300,
                "avg_heart_rate": None,
            },  # ACTIVE (no HR, pace not fast)
            {"pace_seconds_per_km": 220, "avg_heart_rate": 175},  # INTERVAL (by pace)
            {
                "pace_seconds_per_km": 260,
                "avg_heart_rate": None,
            },  # ACTIVE (no HR, pace not fast)
            {"pace_seconds_per_km": 260, "avg_heart_rate": 145},  # ACTIVE
            {"pace_seconds_per_km": 300, "avg_heart_rate": None},  # COOLDOWN (position)
        ]

        result = PhaseMapper.estimate_intensity_type(splits)

        # Should not crash and produce reasonable estimates
        assert result[0] == "WARMUP"  # Position-based
        assert result[1] == "ACTIVE"  # No HR, pace not fast enough
        assert result[2] == "INTERVAL"  # Fast pace detected
        assert result[-1] == "COOLDOWN"  # Position-based

    @pytest.mark.unit
    def test_estimate_intensity_type_single_split(self):
        """Test estimation handles edge case of single split."""

        # Test case: Only 1 split (should not be both WARMUP and COOLDOWN)
        splits = [
            {"pace_seconds_per_km": 270, "avg_heart_rate": 150},
        ]

        result = PhaseMapper.estimate_intensity_type(splits)

        # Single split: no warmup/cooldown designation
        assert len(result) == 1
        assert result[0] == "ACTIVE"  # Default to ACTIVE

    @pytest.mark.unit
    def test_estimate_intensity_type_empty_splits(self):
        """Test estimation handles empty splits list."""

        splits: list[dict] = []

        result = PhaseMapper.estimate_intensity_type(splits)

        assert result == []

    @pytest.mark.integration
    def test_insert_splits_estimates_missing_intensity(
        self, tmp_path, initialized_db_path
    ):
        """Test insert_splits applies estimation when intensity_type is NULL."""

        # Create splits file with NULL intensity_type
        splits_data = {
            "lapDTOs": [
                {
                    "lapIndex": 0,
                    "distance": 1000,
                    "duration": 300,
                    "averageHR": 140,
                    "averageRunCadence": 170,
                    "groundContactTime": 250,
                    "verticalOscillation": 8.5,
                    "verticalRatio": 8.0,
                    "elevationGain": 5,
                    "elevationLoss": 2,
                    "intensityType": None,  # NULL - should be estimated
                },
                {
                    "lapIndex": 1,
                    "distance": 1000,
                    "duration": 240,
                    "averageHR": 175,
                    "averageRunCadence": 180,
                    "groundContactTime": 240,
                    "verticalOscillation": 8.0,
                    "verticalRatio": 7.5,
                    "elevationGain": 3,
                    "elevationLoss": 4,
                    "intensityType": None,  # NULL - should be estimated
                },
                {
                    "lapIndex": 2,
                    "distance": 1000,
                    "duration": 310,
                    "averageHR": 130,
                    "averageRunCadence": 165,
                    "groundContactTime": 255,
                    "verticalOscillation": 8.7,
                    "verticalRatio": 8.2,
                    "elevationGain": 2,
                    "elevationLoss": 5,
                    "intensityType": None,  # NULL - should be estimated
                },
            ]
        }

        splits_file = tmp_path / "splits.json"
        with open(splits_file, "w", encoding="utf-8") as f:
            json.dump(splits_data, f)

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        # Execute
        result = insert_splits(
            activity_id=12345,
            conn=conn,
            raw_splits_file=str(splits_file),
        )

        assert result is True

        # Verify estimation was applied
        splits = conn.execute("""
            SELECT split_index, intensity_type
            FROM splits
            WHERE activity_id = 12345
            ORDER BY split_index
            """).fetchall()

        assert len(splits) == 3

        # Expected: WARMUP (position), INTERVAL (fast pace), COOLDOWN (position)
        # Paces: 300, 240, 310 sec/km → avg = 283.3
        # Threshold (×0.9): 255 sec/km → split 1 (240) is INTERVAL
        assert splits[0][1] == "WARMUP"  # First split
        assert splits[1][1] == "INTERVAL"  # Fast pace (240 < 255)
        assert splits[2][1] == "COOLDOWN"  # Last split

        conn.close()

    @pytest.mark.integration
    def test_insert_splits_preserves_existing_intensity(
        self, tmp_path, initialized_db_path
    ):
        """Test insert_splits does NOT overwrite existing intensity_type values."""

        # Create splits file with existing intensity_type values
        splits_data = {
            "lapDTOs": [
                {
                    "lapIndex": 0,
                    "distance": 1000,
                    "duration": 300,
                    "averageHR": 140,
                    "averageRunCadence": 170,
                    "groundContactTime": 250,
                    "verticalOscillation": 8.5,
                    "verticalRatio": 8.0,
                    "elevationGain": 5,
                    "elevationLoss": 2,
                    "intensityType": "ACTIVE",  # Existing value
                },
                {
                    "lapIndex": 1,
                    "distance": 1000,
                    "duration": 240,
                    "averageHR": 175,
                    "averageRunCadence": 180,
                    "groundContactTime": 240,
                    "verticalOscillation": 8.0,
                    "verticalRatio": 7.5,
                    "elevationGain": 3,
                    "elevationLoss": 4,
                    "intensityType": "ACTIVE",  # Existing value
                },
                {
                    "lapIndex": 2,
                    "distance": 1000,
                    "duration": 310,
                    "averageHR": 130,
                    "averageRunCadence": 165,
                    "groundContactTime": 255,
                    "verticalOscillation": 8.7,
                    "verticalRatio": 8.2,
                    "elevationGain": 2,
                    "elevationLoss": 5,
                    "intensityType": "ACTIVE",  # Existing value
                },
            ]
        }

        splits_file = tmp_path / "splits.json"
        with open(splits_file, "w", encoding="utf-8") as f:
            json.dump(splits_data, f)

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        # Execute
        result = insert_splits(
            activity_id=12345,
            conn=conn,
            raw_splits_file=str(splits_file),
        )

        assert result is True

        # Verify existing values are preserved
        splits = conn.execute("""
            SELECT split_index, intensity_type
            FROM splits
            WHERE activity_id = 12345
            ORDER BY split_index
            """).fetchall()

        assert len(splits) == 3

        # All should remain ACTIVE (existing values preserved)
        assert splits[0][1] == "ACTIVE"
        assert splits[1][1] == "ACTIVE"
        assert splits[2][1] == "ACTIVE"

        conn.close()

    @pytest.mark.integration
    def test_insert_splits_mixed_null_and_existing(self, tmp_path, initialized_db_path):
        """Test insert_splits handles mix of NULL and existing intensity_type."""

        # Create splits file with mix of NULL and existing values
        splits_data = {
            "lapDTOs": [
                {
                    "lapIndex": 0,
                    "distance": 1000,
                    "duration": 300,
                    "averageHR": 140,
                    "averageRunCadence": 170,
                    "intensityType": None,  # NULL - should estimate WARMUP
                },
                {
                    "lapIndex": 1,
                    "distance": 1000,
                    "duration": 240,
                    "averageHR": 175,
                    "averageRunCadence": 180,
                    "intensityType": "INTERVAL",  # Existing - preserve
                },
                {
                    "lapIndex": 2,
                    "distance": 1000,
                    "duration": 310,
                    "averageHR": 130,
                    "averageRunCadence": 165,
                    "intensityType": None,  # NULL - should estimate COOLDOWN
                },
            ]
        }

        splits_file = tmp_path / "splits.json"
        with open(splits_file, "w", encoding="utf-8") as f:
            json.dump(splits_data, f)

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        # Execute
        result = insert_splits(
            activity_id=12345,
            conn=conn,
            raw_splits_file=str(splits_file),
        )

        assert result is True

        # Verify estimation applied only to NULL values
        splits = conn.execute("""
            SELECT split_index, intensity_type
            FROM splits
            WHERE activity_id = 12345
            ORDER BY split_index
            """).fetchall()

        assert len(splits) == 3

        # Expected: WARMUP (estimated), INTERVAL (preserved), COOLDOWN (estimated)
        assert splits[0][1] == "WARMUP"  # Estimated from NULL
        assert splits[1][1] == "INTERVAL"  # Preserved existing
        assert splits[2][1] == "COOLDOWN"  # Estimated from NULL

        conn.close()
