"""
Integration tests for GarminIngestWorker.process_activity()

Tests the complete workflow: data collection → performance.json → DuckDB insertion
"""

import tempfile
from pathlib import Path

import duckdb
import pytest


class TestProcessActivityIntegration:
    """Integration tests for process_activity() with DuckDB schema"""

    @pytest.mark.integration
    def test_db_schema_supports_inserters(self):
        """Test that db_writer creates tables compatible with all inserters"""
        # This test verifies that _ensure_tables() creates the correct schema
        # so that individual inserters can insert data without FK errors

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"

            # Import here to avoid circular dependency
            from tools.database.db_writer import GarminDBWriter

            # Create database with new schema
            writer = GarminDBWriter(db_path=str(db_path))
            writer._ensure_tables()

            # Verify all normalized tables exist
            conn = duckdb.connect(str(db_path))
            tables = conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
            table_names = [t[0] for t in tables]

            expected_tables = [
                "activities",
                "splits",
                "form_efficiency",
                "heart_rate_zones",
                "hr_efficiency",
                "performance_trends",
                "vo2_max",
                "lactate_threshold",
                "section_analyses",
            ]

            for table in expected_tables:
                assert table in table_names, f"{table} should exist"

            # Verify performance_data does NOT exist
            assert "performance_data" not in table_names

            # Test that we can insert into activities table
            conn.execute(
                """
                INSERT INTO activities (activity_id, date, activity_name)
                VALUES (123456, '2025-01-15', 'Test Run')
                """
            )

            # Test that we can insert into normalized tables with FK
            conn.execute(
                """
                INSERT INTO splits (activity_id, split_index, distance)
                VALUES (123456, 1, 1.0)
                """
            )

            conn.execute(
                """
                INSERT INTO form_efficiency (activity_id, gct_average)
                VALUES (123456, 240.0)
                """
            )

            conn.execute(
                """
                INSERT INTO heart_rate_zones (activity_id, zone_number, zone_low_boundary)
                VALUES (123456, 1, 100)
                """
            )

            # Test FK constraint - should fail without parent activity
            with pytest.raises(Exception) as exc_info:
                conn.execute(
                    """
                    INSERT INTO splits (activity_id, split_index)
                    VALUES (999999, 1)
                    """
                )

            error_msg = str(exc_info.value).lower()
            assert "foreign key" in error_msg or "constraint" in error_msg

            conn.close()

    @pytest.mark.integration
    def test_inserter_functions_work_with_schema(self):
        """Test that individual inserter functions work with new schema"""
        # This tests that the inserters can successfully insert data
        # into tables created by _ensure_tables()

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"
            perf_file = Path(tmpdir) / "performance.json"

            # Create mock performance.json
            performance_data = {
                "basic_metrics": {
                    "distance_km": 10.0,
                    "duration_seconds": 3000,
                    "avg_pace_seconds_per_km": 300,
                },
                "split_metrics": [
                    {
                        "split_number": 1,
                        "distance_km": 1.0,
                        "avg_pace_seconds_per_km": 295,
                        "avg_heart_rate": 148,
                        "avg_cadence": 164,
                        "avg_power": 245,
                        "ground_contact_time_ms": 240,
                        "vertical_oscillation_cm": 8.5,
                        "vertical_ratio_percent": 7.2,
                        "elevation_gain_m": 5.0,
                        "elevation_loss_m": 2.0,
                        "terrain_type": "flat",
                    }
                ],
                "form_efficiency_summary": {
                    "gct_stats": {"average": 240, "min": 235, "max": 245, "std": 3.0},
                    "vo_stats": {"average": 8.5, "min": 8.0, "max": 9.0, "std": 0.3},
                    "vr_stats": {"average": 7.2, "min": 7.0, "max": 7.5, "std": 0.2},
                    "gct_rating": "★★★★☆",
                    "vo_rating": "★★★★☆",
                    "vr_rating": "★★★★★",
                },
                "heart_rate_zones": {
                    "zone1": {"low": 100, "secs_in_zone": 600},
                    "zone2": {"low": 120, "secs_in_zone": 1200},
                    "zone3": {"low": 140, "secs_in_zone": 900},
                    "zone4": {"low": 160, "secs_in_zone": 300},
                    "zone5": {"low": 180, "secs_in_zone": 0},
                },
                "hr_efficiency_analysis": {
                    "training_type": "aerobic_base",
                    "hr_stability": "良好",
                    "zone_distribution": {
                        "zone1_percent": 20.0,
                        "zone2_percent": 40.0,
                        "zone3_percent": 30.0,
                        "zone4_percent": 10.0,
                        "zone5_percent": 0.0,
                    },
                },
                "performance_trends": {
                    "pace_consistency": 2.5,
                    "hr_drift_percentage": 3.2,
                    "cadence_consistency": "高い安定性",
                    "fatigue_pattern": "適切な疲労管理",
                    "warmup_phase": {"avg_pace_seconds_per_km": 305, "avg_hr": 145},
                    "main_phase": {"avg_pace_seconds_per_km": 295, "avg_hr": 150},
                    "finish_phase": {"avg_pace_seconds_per_km": 300, "avg_hr": 148},
                },
                "vo2_max": {"precise": 52.5},
                "lactate_threshold": {"heartRate": 165, "speed": 3.5},
            }

            import json

            with open(perf_file, "w") as f:
                json.dump(performance_data, f)

            # Create database schema
            from tools.database.db_writer import GarminDBWriter

            writer = GarminDBWriter(db_path=str(db_path))
            writer._ensure_tables()

            # Insert activity record first (required for FK)
            conn = duckdb.connect(str(db_path))
            conn.execute(
                """
                INSERT INTO activities (activity_id, date, activity_name)
                VALUES (123456, '2025-01-15', 'Test Run')
                """
            )
            conn.close()

            # Test individual inserters
            from tools.database.inserters.form_efficiency import insert_form_efficiency
            from tools.database.inserters.heart_rate_zones import (
                insert_heart_rate_zones,
            )
            from tools.database.inserters.hr_efficiency import insert_hr_efficiency
            from tools.database.inserters.lactate_threshold import (
                insert_lactate_threshold,
            )
            from tools.database.inserters.performance_trends import (
                insert_performance_trends,
            )
            from tools.database.inserters.splits import insert_splits
            from tools.database.inserters.vo2_max import insert_vo2_max

            # All inserters should complete without FK errors
            assert insert_splits(str(perf_file), 123456, str(db_path)) is True
            assert insert_form_efficiency(str(perf_file), 123456, str(db_path)) is True
            assert insert_heart_rate_zones(str(perf_file), 123456, str(db_path)) is True
            assert insert_hr_efficiency(str(perf_file), 123456, str(db_path)) is True
            assert (
                insert_performance_trends(str(perf_file), 123456, str(db_path)) is True
            )
            assert insert_vo2_max(str(perf_file), 123456, str(db_path)) is True
            assert (
                insert_lactate_threshold(str(perf_file), 123456, str(db_path)) is True
            )

            # Verify data was inserted
            conn = duckdb.connect(str(db_path))

            # Check splits
            result = conn.execute(
                "SELECT COUNT(*) FROM splits WHERE activity_id = 123456"
            ).fetchone()
            assert result is not None
            splits_count = result[0]
            assert splits_count == 1

            # Check form_efficiency
            result = conn.execute(
                "SELECT COUNT(*) FROM form_efficiency WHERE activity_id = 123456"
            ).fetchone()
            assert result is not None
            fe_count = result[0]
            assert fe_count == 1

            # Check heart_rate_zones (5 zones)
            result = conn.execute(
                "SELECT COUNT(*) FROM heart_rate_zones WHERE activity_id = 123456"
            ).fetchone()
            assert result is not None
            hrz_count = result[0]
            assert hrz_count == 5

            conn.close()
