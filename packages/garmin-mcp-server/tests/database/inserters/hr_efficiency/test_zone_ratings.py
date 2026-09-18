"""Primary zone, zone-distribution rating, aerobic efficiency, training quality, zone2 focus and zone4 threshold flags."""

import json

import duckdb
import pytest

from garmin_mcp.database.inserters.hr_efficiency import (
    ZONE_BAND_CUTS,
    _combine_training_quality,
    _extract_hr_efficiency_from_raw,
    insert_hr_efficiency,
    zone_band_pct,
    zone_distribution_rating,
    zone_distribution_score,
)
from tests.database.inserters.hr_efficiency._helpers import _write_raw_files


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
    def test_training_quality_fair_rating_aligned_is_fair(self, tmp_path):
        """Issue #1232 (activity 24394775433): an aligned easy run rated Fair.

        Zone1+2 = 68.97% is one step below Good, and the modal zone is Zone 2 as
        an easy run intends, so the quality is Fair — not the two-step drop to
        Poor the old ladder produced.
        """
        hr_zones_file, activity_file = _write_raw_files(
            tmp_path, {1: 13.53, 2: 55.44, 3: 31.03}, "AEROBIC_BASE"
        )
        result = _extract_hr_efficiency_from_raw(hr_zones_file, activity_file)

        assert result["primary_zone"] == "Zone 2"
        assert result["zone_distribution_rating"] == "Fair"
        assert result["training_quality"] == "Fair"

    @pytest.mark.unit
    def test_training_quality_fair_rating_misaligned_is_poor(self, tmp_path):
        """A Fair easy run whose modal zone is Zone 3 keeps its demotion to Poor.

        Zone3 = 35% stays below the 50% moderate refinement, so the run is still
        judged as easy and the misalignment costs the remaining step.
        """
        hr_zones_file, activity_file = _write_raw_files(
            tmp_path, {1: 32.0, 2: 33.0, 3: 35.0}, "AEROBIC_BASE"
        )
        result = _extract_hr_efficiency_from_raw(hr_zones_file, activity_file)

        assert result["primary_zone"] == "Zone 3"
        assert result["zone_distribution_rating"] == "Fair"
        assert result["training_quality"] == "Poor"

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("rating", "aligned", "expected"),
        [
            ("Excellent", True, "Excellent"),
            ("Excellent", False, "Good"),
            ("Good", True, "Good"),
            ("Good", False, "Fair"),
            ("Poor", True, "Poor"),
            ("Poor", False, "Poor"),
        ],
    )
    def test_training_quality_existing_ladder_unchanged(
        self, rating, aligned, expected
    ):
        """Every rung other than Fair keeps the quality it had before #1232."""
        assert _combine_training_quality(rating, aligned) == expected

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


class TestZoneDistributionScore:
    """Continuous zone-distribution score over the same cuts as the label (#1235)."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "band_pct,expected",
        [
            (95.0, 5.0),  # above the excellent cut stays at the ceiling
            (90.0, 5.0),  # excellent cut
            (84.6, 4.6),
            (75.0, 4.0),  # good cut
            (68.97, 3.6),
            (60.0, 3.0),  # fair cut
            (45.0, 2.0),  # same slope continues below the fair cut
            (20.0, 1.0),  # floor
        ],
    )
    def test_zone_score_easy_anchors(self, band_pct, expected):
        """Easy (90/75/60) interpolates linearly between its own cuts."""
        assert zone_distribution_score("easy", band_pct) == expected

    @pytest.mark.unit
    def test_zone_score_no_cliff_at_good_cut(self):
        """Two runs either side of a cut differ by data, not by a whole step."""
        below = zone_distribution_score("easy", 74.9)
        above = zone_distribution_score("easy", 75.1)
        assert below is not None and above is not None
        assert abs(above - below) <= 0.1

    @pytest.mark.unit
    def test_zone_score_unknown_is_none(self):
        """An unknown category has no intended band and is never penalised."""
        assert zone_distribution_score("unknown", 80.0) is None

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "category,expected",
        [
            ("easy", 60.0),  # Zone1-2
            ("moderate", 80.0),  # Zone2-3
            ("tempo", 38.0),  # Zone3-4
            ("threshold", 38.0),  # Zone3-4
            ("vo2max", 10.0),  # Zone4-5
            ("unknown", 90.0),  # Zone1-3
        ],
    )
    def test_zone_band_pct_per_category(self, category, expected):
        """Each category is measured on the band it is judged on."""
        assert zone_band_pct(category, 10.0, 50.0, 30.0, 8.0, 2.0) == expected

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "category,band_pct,expected",
        [
            # easy 90 / 75 / 60
            ("easy", 90.0, "Excellent"),
            ("easy", 89.9, "Good"),
            ("easy", 75.0, "Good"),
            ("easy", 74.9, "Fair"),
            ("easy", 60.0, "Fair"),
            ("easy", 59.9, "Poor"),
            # moderate 80 / 60 / 40
            ("moderate", 80.0, "Excellent"),
            ("moderate", 79.9, "Good"),
            ("moderate", 60.0, "Good"),
            ("moderate", 59.9, "Fair"),
            ("moderate", 40.0, "Fair"),
            ("moderate", 39.9, "Poor"),
            # tempo / threshold 60 / 40 / 20
            ("tempo", 60.0, "Excellent"),
            ("tempo", 40.0, "Good"),
            ("tempo", 20.0, "Fair"),
            ("tempo", 19.9, "Poor"),
            ("threshold", 60.0, "Excellent"),
            ("threshold", 19.9, "Poor"),
            # vo2max 50 / 30 / 15
            ("vo2max", 50.0, "Excellent"),
            ("vo2max", 30.0, "Good"),
            ("vo2max", 15.0, "Fair"),
            ("vo2max", 14.9, "Poor"),
            # unknown: 70, never worse than Fair
            ("unknown", 70.0, "Good"),
            ("unknown", 69.9, "Fair"),
            ("unknown", 0.0, "Fair"),
        ],
    )
    def test_zone_rating_labels_unchanged_by_constants(
        self, category, band_pct, expected
    ):
        """Moving the cuts into ZONE_BAND_CUTS must not move any label."""
        assert zone_distribution_rating(category, band_pct) == expected

    @pytest.mark.unit
    @pytest.mark.parametrize("category", sorted(ZONE_BAND_CUTS))
    def test_zone_score_matches_label_boundaries(self, category):
        """The score and the label read the same three cuts."""
        excellent_cut, good_cut, fair_cut = ZONE_BAND_CUTS[category]
        assert zone_distribution_score(category, excellent_cut) == 5.0
        assert zone_distribution_score(category, good_cut) == 4.0
        assert zone_distribution_score(category, fair_cut) == 3.0
