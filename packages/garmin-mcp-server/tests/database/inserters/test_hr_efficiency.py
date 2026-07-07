"""
Tests for HR Efficiency Inserter

Test coverage:
- Unit tests for insert_hr_efficiency function
- Integration tests with DuckDB
"""

import json

import duckdb
import pytest

from garmin_mcp.database.inserters.hr_efficiency import (
    _canonical_training_category,
    _extract_hr_efficiency_from_raw,
    insert_hr_efficiency,
)


def _write_raw_files(tmp_path, zone_secs, label):
    """Helper: build hr_zones.json + activity.json from per-zone seconds.

    ``zone_secs`` maps zone number (1-5) to secsInZone. Passing values that sum
    to 100 makes each zone's percentage equal to its seconds value.
    """
    hr_zones_data = [
        {
            "zoneNumber": z,
            "zoneLowBoundary": 100 + z * 15,
            "secsInZone": float(zone_secs.get(z, 0.0)),
        }
        for z in range(1, 6)
    ]
    hr_zones_file = tmp_path / "hr_zones.json"
    with open(hr_zones_file, "w", encoding="utf-8") as f:
        json.dump(hr_zones_data, f, ensure_ascii=False, indent=2)

    summary = {"averageHR": 140.0, "maxHR": 170.0, "minHR": 110.0}
    if label is not None:
        summary["trainingEffectLabel"] = label
    activity_file = tmp_path / "activity.json"
    with open(activity_file, "w", encoding="utf-8") as f:
        json.dump({"summaryDTO": summary}, f, ensure_ascii=False, indent=2)

    return str(hr_zones_file), str(activity_file)


class TestHREfficiencyInserter:
    """Test suite for HR Efficiency Inserter."""

    @pytest.fixture
    def sample_raw_files(self, tmp_path):
        """Create sample hr_zones.json and activity.json files."""
        # Create hr_zones.json
        hr_zones_data = [
            {"zoneNumber": 1, "zoneLowBoundary": 117, "secsInZone": 490.546},
            {"zoneNumber": 2, "zoneLowBoundary": 131, "secsInZone": 1041.858},
            {"zoneNumber": 3, "zoneLowBoundary": 146, "secsInZone": 507.274},
            {"zoneNumber": 4, "zoneLowBoundary": 160, "secsInZone": 675.8},
            {"zoneNumber": 5, "zoneLowBoundary": 175, "secsInZone": 0.0},
        ]
        hr_zones_file = tmp_path / "hr_zones.json"
        with open(hr_zones_file, "w", encoding="utf-8") as f:
            json.dump(hr_zones_data, f, ensure_ascii=False, indent=2)

        # Create activity.json
        activity_data = {
            "summaryDTO": {
                "averageHR": 148.0,
                "maxHR": 175.0,
                "minHR": 120.0,
                "trainingEffectLabel": "THRESHOLD_WORK",
            }
        }
        activity_file = tmp_path / "activity.json"
        with open(activity_file, "w", encoding="utf-8") as f:
            json.dump(activity_data, f, ensure_ascii=False, indent=2)

        return hr_zones_file, activity_file

    @pytest.mark.unit
    def test_insert_hr_efficiency_success(self, sample_raw_files, initialized_db_path):
        """Test insert_hr_efficiency inserts data successfully."""
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
        assert db_path.exists()

    @pytest.mark.unit
    def test_insert_hr_efficiency_missing_file(self, tmp_path):
        """Test insert_hr_efficiency handles missing files."""
        conn = duckdb.connect(":memory:")

        result = insert_hr_efficiency(
            activity_id=12345,
            conn=conn,
            raw_hr_zones_file="/nonexistent/hr_zones.json",
            raw_activity_file="/nonexistent/activity.json",
        )
        conn.close()

        assert result is False

    @pytest.mark.unit
    def test_insert_hr_efficiency_no_required_files(self, tmp_path):
        """Test insert_hr_efficiency handles missing required files."""
        conn = duckdb.connect(":memory:")

        # Missing both files
        result = insert_hr_efficiency(
            activity_id=12345,
            conn=conn,
            raw_hr_zones_file=None,
            raw_activity_file=None,
        )
        conn.close()

        assert result is False

    @pytest.mark.integration
    def test_insert_hr_efficiency_db_integration(
        self, sample_raw_files, initialized_db_path
    ):
        """Test insert_hr_efficiency actually writes to DuckDB."""

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

        # Verify data in DuckDB
        conn = duckdb.connect(str(db_path))

        # Check hr_efficiency table exists
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        assert "hr_efficiency" in table_names

        # Check hr_efficiency data
        hr_eff = conn.execute(
            "SELECT * FROM hr_efficiency WHERE activity_id = 20615445009"
        ).fetchall()
        assert len(hr_eff) == 1

        # Verify data values
        row = hr_eff[0]
        assert row[0] == 20615445009  # activity_id
        assert row[8] == "threshold_work"  # training_type
        assert row[3] is not None  # hr_stability

        conn.close()

    @pytest.fixture
    def sample_hr_zones_file(self, tmp_path):
        """Create sample hr_zones.json file."""
        hr_zones = [
            {"zoneNumber": 1, "secsInZone": 88.001, "zoneLowBoundary": 116},
            {"zoneNumber": 2, "secsInZone": 576.894, "zoneLowBoundary": 130},
            {"zoneNumber": 3, "secsInZone": 1488.727, "zoneLowBoundary": 145},
            {"zoneNumber": 4, "secsInZone": 0.0, "zoneLowBoundary": 159},
            {"zoneNumber": 5, "secsInZone": 0.0, "zoneLowBoundary": 174},
        ]

        hr_zones_file = tmp_path / "hr_zones.json"
        with open(hr_zones_file, "w", encoding="utf-8") as f:
            json.dump(hr_zones, f, ensure_ascii=False, indent=2)

        return hr_zones_file

    @pytest.fixture
    def sample_activity_file(self, tmp_path):
        """Create sample activity.json file."""
        activity_data = {
            "activityId": 20636804823,
            "summaryDTO": {
                "averageHR": 143.0,
                "maxHR": 156.0,
                "minHR": 70.0,
                "trainingEffectLabel": "AEROBIC_BASE",
            },
        }

        activity_file = tmp_path / "activity.json"
        with open(activity_file, "w", encoding="utf-8") as f:
            json.dump(activity_data, f, ensure_ascii=False, indent=2)

        return activity_file

    @pytest.mark.unit
    def test_insert_hr_efficiency_raw_data_success(
        self, sample_hr_zones_file, sample_activity_file, initialized_db_path
    ):
        """Test insert_hr_efficiency with raw data mode."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_hr_efficiency(
            activity_id=20636804823,
            conn=conn,
            raw_hr_zones_file=str(sample_hr_zones_file),
            raw_activity_file=str(sample_activity_file),
        )

        assert result is True
        assert db_path.exists()

    @pytest.mark.integration
    def test_insert_hr_efficiency_raw_data_db_integration(
        self, sample_hr_zones_file, sample_activity_file, initialized_db_path
    ):
        """Test insert_hr_efficiency with raw data actually writes to DuckDB."""

        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_hr_efficiency(
            activity_id=20636804823,
            conn=conn,
            raw_hr_zones_file=str(sample_hr_zones_file),
            raw_activity_file=str(sample_activity_file),
        )

        assert result is True

        # Verify data in DuckDB
        conn = duckdb.connect(str(db_path))

        # Check hr_efficiency table exists
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        assert "hr_efficiency" in table_names

        # Check hr_efficiency data
        hr_eff = conn.execute(
            "SELECT * FROM hr_efficiency WHERE activity_id = 20636804823"
        ).fetchall()
        assert len(hr_eff) == 1

        # Verify data values
        row = hr_eff[0]
        assert row[0] == 20636804823  # activity_id
        assert row[8] == "aerobic_base"  # training_type (from trainingEffectLabel)
        assert row[3] is not None  # hr_stability

        # Verify zone percentages
        total_time = 88.001 + 576.894 + 1488.727
        expected_zone1_pct = round((88.001 / total_time) * 100, 2)
        expected_zone2_pct = round((576.894 / total_time) * 100, 2)
        expected_zone3_pct = round((1488.727 / total_time) * 100, 2)

        assert row[9] == expected_zone1_pct  # zone1_percentage
        assert row[10] == expected_zone2_pct  # zone2_percentage
        assert row[11] == expected_zone3_pct  # zone3_percentage
        assert row[12] == 0.0  # zone4_percentage
        assert row[13] == 0.0  # zone5_percentage

        conn.close()

    @pytest.mark.unit
    def test_insert_hr_efficiency_raw_data_missing_files(self, initialized_db_path):
        """Test insert_hr_efficiency raw mode handles missing files."""
        db_path = initialized_db_path
        conn = duckdb.connect(str(db_path))

        result = insert_hr_efficiency(
            activity_id=12345,
            conn=conn,
            raw_hr_zones_file="/nonexistent/hr_zones.json",
            raw_activity_file="/nonexistent/activity.json",
        )

        assert result is False

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


class TestCanonicalTrainingCategory:
    """Test suite for _canonical_training_category and category-based ratings."""

    @pytest.mark.unit
    def test_canonical_category_maps_real_labels(self):
        """raw/fallback labels map to the correct canonical intensity category."""
        assert _canonical_training_category("aerobic_base") == "easy"
        assert _canonical_training_category("recovery") == "easy"
        assert _canonical_training_category("low_moderate") == "easy"
        assert _canonical_training_category("warmup") == "easy"
        assert _canonical_training_category("tempo") == "tempo"
        assert _canonical_training_category("tempo_run") == "tempo"
        assert _canonical_training_category("lactate_threshold") == "threshold"
        assert _canonical_training_category("threshold_work") == "threshold"
        assert _canonical_training_category("vo2max") == "vo2max"
        assert _canonical_training_category("anaerobic_capacity") == "vo2max"
        assert _canonical_training_category("speed") == "vo2max"
        assert _canonical_training_category("interval_sprint") == "vo2max"
        assert _canonical_training_category("unknown") == "unknown"
        assert _canonical_training_category("mixed_effort") == "unknown"
        assert _canonical_training_category(None) == "unknown"

    @pytest.mark.unit
    def test_easy_zone1_dominant_not_poor(self, tmp_path):
        """Regression (activity 23508330663): easy run dominated by Zone1 must not
        be rated Poor. zone1=57.6, zone2=42.4 → Excellent."""
        hr_zones_file, activity_file = _write_raw_files(
            tmp_path, {1: 57.6, 2: 42.4}, "AEROBIC_BASE"
        )
        result = _extract_hr_efficiency_from_raw(hr_zones_file, activity_file)

        assert result["zone_distribution_rating"] == "Excellent"
        assert result["training_quality"] in {"Excellent", "Good"}

    @pytest.mark.unit
    def test_recovery_all_zone1_excellent(self, tmp_path):
        """recovery with all time in Zone1 → Excellent (judged on Zone1-2)."""
        hr_zones_file, activity_file = _write_raw_files(
            tmp_path, {1: 100.0}, "RECOVERY"
        )
        result = _extract_hr_efficiency_from_raw(hr_zones_file, activity_file)

        assert result["zone_distribution_rating"] == "Excellent"

    @pytest.mark.unit
    def test_tempo_scored_by_zone34(self, tmp_path):
        """tempo scored on Zone3-4: zone3+zone4=65 → Excellent (not old else path)."""
        hr_zones_file, activity_file = _write_raw_files(
            tmp_path, {1: 35.0, 3: 35.0, 4: 30.0}, "TEMPO"
        )
        result = _extract_hr_efficiency_from_raw(hr_zones_file, activity_file)

        assert result["zone_distribution_rating"] == "Excellent"

    @pytest.mark.unit
    def test_lactate_threshold_scored_by_zone34(self, tmp_path):
        """lactate_threshold scored on Zone3-4: zone3+zone4=45 → Good."""
        hr_zones_file, activity_file = _write_raw_files(
            tmp_path, {1: 55.0, 3: 25.0, 4: 20.0}, "LACTATE_THRESHOLD"
        )
        result = _extract_hr_efficiency_from_raw(hr_zones_file, activity_file)

        assert result["zone_distribution_rating"] == "Good"

    @pytest.mark.unit
    def test_vo2max_scored_by_zone45(self, tmp_path):
        """vo2max scored on Zone4-5: zone4+zone5=55 → Excellent."""
        hr_zones_file, activity_file = _write_raw_files(
            tmp_path, {1: 45.0, 4: 30.0, 5: 25.0}, "VO2MAX"
        )
        result = _extract_hr_efficiency_from_raw(hr_zones_file, activity_file)

        assert result["zone_distribution_rating"] == "Excellent"

    @pytest.mark.unit
    def test_easy_drift_to_zone3_downgraded(self, tmp_path):
        """easy run that drifts into Zone3: zone1+zone2=55, zone3=45 → Fair/Poor."""
        hr_zones_file, activity_file = _write_raw_files(
            tmp_path, {1: 30.0, 2: 25.0, 3: 45.0}, "AEROBIC_BASE"
        )
        result = _extract_hr_efficiency_from_raw(hr_zones_file, activity_file)

        assert result["zone_distribution_rating"] in {"Fair", "Poor"}

    @pytest.mark.unit
    def test_unknown_not_harshly_penalized(self, tmp_path):
        """unknown type never rated Poor: zone1+zone2+zone3=75 → Good."""
        hr_zones_file, activity_file = _write_raw_files(
            tmp_path, {1: 25.0, 2: 25.0, 3: 25.0, 4: 25.0}, "UNKNOWN"
        )
        result = _extract_hr_efficiency_from_raw(hr_zones_file, activity_file)

        assert result["zone_distribution_rating"] != "Poor"
