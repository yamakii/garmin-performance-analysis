"""Primary zone, zone-distribution rating, aerobic efficiency, training quality, zone2 focus and zone4 threshold flags."""

import json

import duckdb
import pytest

from garmin_mcp.database.inserters.hr_efficiency import (
    insert_hr_efficiency,
)


class TestZoneRatings:
    @pytest.mark.unit
    def test_primary_zone_calculation(self, sample_raw_files, initialized_db_path):
        """Test primary_zone field identifies the zone with highest time."""
        hr_zones_file, activity_file = sample_raw_files
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_hr_efficiency(
            activity_id=20615445009,
            conn=conn,
            raw_hr_zones_file=str(hr_zones_file),
            raw_activity_file=str(activity_file),
        )

        assert result is True

        # Verify primary_zone in DuckDB

        _row = conn.execute(
            "SELECT primary_zone FROM hr_efficiency WHERE activity_id = 20615445009"
        ).fetchone()
        assert _row is not None
        primary_zone = _row[0]

        # Zone 2 has highest time (1041.858s)
        assert primary_zone == "Zone 2"
        conn.close()

    @pytest.mark.unit
    def test_zone_distribution_rating_recovery(self, tmp_path, initialized_db_path):
        """Test zone_distribution_rating for recovery training type."""
        # Create hr_zones with Zone 2 dominant (72%)
        hr_zones_data = [
            {"zoneNumber": 1, "zoneLowBoundary": 117, "secsInZone": 100.0},
            {"zoneNumber": 2, "zoneLowBoundary": 131, "secsInZone": 720.0},
            {"zoneNumber": 3, "zoneLowBoundary": 146, "secsInZone": 180.0},
            {"zoneNumber": 4, "zoneLowBoundary": 160, "secsInZone": 0.0},
            {"zoneNumber": 5, "zoneLowBoundary": 175, "secsInZone": 0.0},
        ]
        hr_zones_file = tmp_path / "hr_zones.json"
        with open(hr_zones_file, "w", encoding="utf-8") as f:
            json.dump(hr_zones_data, f, ensure_ascii=False, indent=2)

        # Create activity with recovery training type
        activity_data = {
            "summaryDTO": {
                "averageHR": 135.0,
                "maxHR": 150.0,
                "minHR": 120.0,
                "trainingEffectLabel": "RECOVERY",
            }
        }
        activity_file = tmp_path / "activity.json"
        with open(activity_file, "w", encoding="utf-8") as f:
            json.dump(activity_data, f, ensure_ascii=False, indent=2)

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))
        result = insert_hr_efficiency(
            activity_id=12345,
            conn=conn,
            raw_hr_zones_file=str(hr_zones_file),
            raw_activity_file=str(activity_file),
        )

        assert result is True

        _row = conn.execute(
            "SELECT zone_distribution_rating FROM hr_efficiency WHERE activity_id = 12345"
        ).fetchone()
        assert _row is not None
        rating = _row[0]

        # recovery → easy category, judged on Zone1-2.
        # Zone1=10% + Zone2=72% = 82% → Good (≥75, <90)
        assert rating == "Good"
        conn.close()

    @pytest.mark.unit
    def test_zone_distribution_rating_tempo(self, tmp_path, initialized_db_path):
        """Test zone_distribution_rating for tempo training type."""
        # Create hr_zones with Zone 3-4 at 65%
        hr_zones_data = [
            {"zoneNumber": 1, "zoneLowBoundary": 117, "secsInZone": 100.0},
            {"zoneNumber": 2, "zoneLowBoundary": 131, "secsInZone": 250.0},
            {"zoneNumber": 3, "zoneLowBoundary": 146, "secsInZone": 400.0},
            {"zoneNumber": 4, "zoneLowBoundary": 160, "secsInZone": 250.0},
            {"zoneNumber": 5, "zoneLowBoundary": 175, "secsInZone": 0.0},
        ]
        hr_zones_file = tmp_path / "hr_zones.json"
        with open(hr_zones_file, "w", encoding="utf-8") as f:
            json.dump(hr_zones_data, f, ensure_ascii=False, indent=2)

        activity_data = {
            "summaryDTO": {
                "averageHR": 155.0,
                "maxHR": 165.0,
                "minHR": 145.0,
                "trainingEffectLabel": "TEMPO_RUN",
            }
        }
        activity_file = tmp_path / "activity.json"
        with open(activity_file, "w", encoding="utf-8") as f:
            json.dump(activity_data, f, ensure_ascii=False, indent=2)

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))
        result = insert_hr_efficiency(
            activity_id=12346,
            conn=conn,
            raw_hr_zones_file=str(hr_zones_file),
            raw_activity_file=str(activity_file),
        )

        assert result is True

        _row = conn.execute(
            "SELECT zone_distribution_rating FROM hr_efficiency WHERE activity_id = 12346"
        ).fetchone()
        assert _row is not None
        rating = _row[0]

        # 65% in Zone 3-4 → Excellent for tempo
        assert rating == "Excellent"
        conn.close()

    @pytest.mark.unit
    def test_aerobic_efficiency_excellent(self, tmp_path, initialized_db_path):
        """Test aerobic_efficiency calculation for excellent aerobic base."""
        # Create hr_zones with 85% in Zone 2-3
        hr_zones_data = [
            {"zoneNumber": 1, "zoneLowBoundary": 117, "secsInZone": 150.0},
            {"zoneNumber": 2, "zoneLowBoundary": 131, "secsInZone": 500.0},
            {"zoneNumber": 3, "zoneLowBoundary": 146, "secsInZone": 350.0},
            {"zoneNumber": 4, "zoneLowBoundary": 160, "secsInZone": 0.0},
            {"zoneNumber": 5, "zoneLowBoundary": 175, "secsInZone": 0.0},
        ]
        hr_zones_file = tmp_path / "hr_zones.json"
        with open(hr_zones_file, "w", encoding="utf-8") as f:
            json.dump(hr_zones_data, f, ensure_ascii=False, indent=2)

        activity_data = {
            "summaryDTO": {
                "averageHR": 140.0,
                "maxHR": 155.0,
                "minHR": 125.0,
                "trainingEffectLabel": "AEROBIC_BASE",
            }
        }
        activity_file = tmp_path / "activity.json"
        with open(activity_file, "w", encoding="utf-8") as f:
            json.dump(activity_data, f, ensure_ascii=False, indent=2)

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))
        result = insert_hr_efficiency(
            activity_id=12347,
            conn=conn,
            raw_hr_zones_file=str(hr_zones_file),
            raw_activity_file=str(activity_file),
        )

        assert result is True

        _row = conn.execute(
            "SELECT aerobic_efficiency FROM hr_efficiency WHERE activity_id = 12347"
        ).fetchone()
        assert _row is not None
        efficiency = _row[0]

        # 85% in Zone 2-3 → Excellent aerobic base
        assert efficiency == "Excellent aerobic base"
        conn.close()

    @pytest.mark.unit
    def test_training_quality_excellent(self, sample_raw_files, initialized_db_path):
        """Test training_quality calculation for excellent training."""
        hr_zones_file, activity_file = sample_raw_files
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_hr_efficiency(
            activity_id=20615445009,
            conn=conn,
            raw_hr_zones_file=str(hr_zones_file),
            raw_activity_file=str(activity_file),
        )

        assert result is True

        _row = conn.execute(
            "SELECT training_quality FROM hr_efficiency WHERE activity_id = 20615445009"
        ).fetchone()
        assert _row is not None
        quality = _row[0]

        # Should have a quality rating
        assert quality in ["Excellent", "Good", "Fair", "Poor"]
        conn.close()

    @pytest.mark.unit
    def test_zone2_focus_true(self, tmp_path, initialized_db_path):
        """Test zone2_focus flag when >60% in Zone 2."""
        # Create hr_zones with 65% in Zone 2
        hr_zones_data = [
            {"zoneNumber": 1, "zoneLowBoundary": 117, "secsInZone": 150.0},
            {"zoneNumber": 2, "zoneLowBoundary": 131, "secsInZone": 650.0},
            {"zoneNumber": 3, "zoneLowBoundary": 146, "secsInZone": 200.0},
            {"zoneNumber": 4, "zoneLowBoundary": 160, "secsInZone": 0.0},
            {"zoneNumber": 5, "zoneLowBoundary": 175, "secsInZone": 0.0},
        ]
        hr_zones_file = tmp_path / "hr_zones.json"
        with open(hr_zones_file, "w", encoding="utf-8") as f:
            json.dump(hr_zones_data, f, ensure_ascii=False, indent=2)

        activity_data = {
            "summaryDTO": {
                "averageHR": 135.0,
                "maxHR": 150.0,
                "minHR": 120.0,
                "trainingEffectLabel": "AEROBIC_BASE",
            }
        }
        activity_file = tmp_path / "activity.json"
        with open(activity_file, "w", encoding="utf-8") as f:
            json.dump(activity_data, f, ensure_ascii=False, indent=2)

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))
        result = insert_hr_efficiency(
            activity_id=12348,
            conn=conn,
            raw_hr_zones_file=str(hr_zones_file),
            raw_activity_file=str(activity_file),
        )

        assert result is True

        _row = conn.execute(
            "SELECT zone2_focus FROM hr_efficiency WHERE activity_id = 12348"
        ).fetchone()
        assert _row is not None
        zone2_focus = _row[0]

        # 65% in Zone 2 → True
        assert zone2_focus is True
        conn.close()

    @pytest.mark.unit
    def test_zone2_focus_false(self, tmp_path, initialized_db_path):
        """Test zone2_focus flag when <60% in Zone 2."""
        # Create hr_zones with 50% in Zone 2
        hr_zones_data = [
            {"zoneNumber": 1, "zoneLowBoundary": 117, "secsInZone": 100.0},
            {"zoneNumber": 2, "zoneLowBoundary": 131, "secsInZone": 500.0},
            {"zoneNumber": 3, "zoneLowBoundary": 146, "secsInZone": 400.0},
            {"zoneNumber": 4, "zoneLowBoundary": 160, "secsInZone": 0.0},
            {"zoneNumber": 5, "zoneLowBoundary": 175, "secsInZone": 0.0},
        ]
        hr_zones_file = tmp_path / "hr_zones.json"
        with open(hr_zones_file, "w", encoding="utf-8") as f:
            json.dump(hr_zones_data, f, ensure_ascii=False, indent=2)

        activity_data = {
            "summaryDTO": {
                "averageHR": 145.0,
                "maxHR": 160.0,
                "minHR": 130.0,
                "trainingEffectLabel": "TEMPO_RUN",
            }
        }
        activity_file = tmp_path / "activity.json"
        with open(activity_file, "w", encoding="utf-8") as f:
            json.dump(activity_data, f, ensure_ascii=False, indent=2)

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))
        result = insert_hr_efficiency(
            activity_id=12349,
            conn=conn,
            raw_hr_zones_file=str(hr_zones_file),
            raw_activity_file=str(activity_file),
        )

        assert result is True

        _row = conn.execute(
            "SELECT zone2_focus FROM hr_efficiency WHERE activity_id = 12349"
        ).fetchone()
        assert _row is not None
        zone2_focus = _row[0]

        # 50% in Zone 2 → False
        assert zone2_focus is False
        conn.close()

    @pytest.mark.unit
    def test_zone4_threshold_work_true(self, tmp_path, initialized_db_path):
        """Test zone4_threshold_work flag when >20% in Zone 4-5."""
        # Create hr_zones with 25% in Zone 4-5
        hr_zones_data = [
            {"zoneNumber": 1, "zoneLowBoundary": 117, "secsInZone": 100.0},
            {"zoneNumber": 2, "zoneLowBoundary": 131, "secsInZone": 350.0},
            {"zoneNumber": 3, "zoneLowBoundary": 146, "secsInZone": 300.0},
            {"zoneNumber": 4, "zoneLowBoundary": 160, "secsInZone": 150.0},
            {"zoneNumber": 5, "zoneLowBoundary": 175, "secsInZone": 100.0},
        ]
        hr_zones_file = tmp_path / "hr_zones.json"
        with open(hr_zones_file, "w", encoding="utf-8") as f:
            json.dump(hr_zones_data, f, ensure_ascii=False, indent=2)

        activity_data = {
            "summaryDTO": {
                "averageHR": 165.0,
                "maxHR": 180.0,
                "minHR": 150.0,
                "trainingEffectLabel": "THRESHOLD_WORK",
            }
        }
        activity_file = tmp_path / "activity.json"
        with open(activity_file, "w", encoding="utf-8") as f:
            json.dump(activity_data, f, ensure_ascii=False, indent=2)

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))
        result = insert_hr_efficiency(
            activity_id=12350,
            conn=conn,
            raw_hr_zones_file=str(hr_zones_file),
            raw_activity_file=str(activity_file),
        )

        assert result is True

        _row = conn.execute(
            "SELECT zone4_threshold_work FROM hr_efficiency WHERE activity_id = 12350"
        ).fetchone()
        assert _row is not None
        threshold_work = _row[0]

        # 25% in Zone 4-5 → True
        assert threshold_work is True
        conn.close()

    @pytest.mark.unit
    def test_zone4_threshold_work_false(self, sample_raw_files, initialized_db_path):
        """Test zone4_threshold_work flag when <20% in Zone 4-5."""
        hr_zones_file, activity_file = sample_raw_files
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_hr_efficiency(
            activity_id=20615445009,
            conn=conn,
            raw_hr_zones_file=str(hr_zones_file),
            raw_activity_file=str(activity_file),
        )

        assert result is True

        _row = conn.execute(
            "SELECT zone4_threshold_work FROM hr_efficiency WHERE activity_id = 20615445009"
        ).fetchone()
        assert _row is not None
        threshold_work = _row[0]

        # Zone 4-5 have 675.8s + 0s = 675.8s out of ~2715s total = ~25% → True
        assert threshold_work is True
        conn.close()
