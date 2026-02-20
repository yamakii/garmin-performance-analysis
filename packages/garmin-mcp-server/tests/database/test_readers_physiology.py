"""Tests for PhysiologyReader.

Covers get_hr_efficiency_analysis, get_heart_rate_zones_detail,
_get_vo2_max_category (5-branch parametrize), get_vo2_max_data,
and get_lactate_threshold_data.
"""

from pathlib import Path

import duckdb
import pytest

from garmin_mcp.database.readers.physiology import PhysiologyReader

ACTIVITY_ID = 77770001
MISSING_ID = 99999999


@pytest.fixture
def phys_reader(reader_db_path: Path) -> PhysiologyReader:
    """PhysiologyReader with seeded physiology data."""
    conn = duckdb.connect(str(reader_db_path))

    # Parent activity (needed for VO2 max fallback)
    conn.execute(
        "INSERT INTO activities (activity_id, activity_date, start_time_local) VALUES (?, ?, ?)",
        [ACTIVITY_ID, "2025-06-15", "2025-06-15 07:00:00"],
    )

    # hr_efficiency
    conn.execute(
        """INSERT INTO hr_efficiency VALUES (
            ?, 'Zone 2', '良好', '安定', '効率的', '高品質',
            true, false, 'easy_run',
            10.0, 55.0, 20.0, 10.0, 5.0
        )""",
        [ACTIVITY_ID],
    )

    # heart_rate_zones (5 zones)
    for z in range(1, 6):
        conn.execute(
            "INSERT INTO heart_rate_zones VALUES (?, ?, ?, ?, ?, ?)",
            [ACTIVITY_ID, z, 100 + z * 15, 115 + z * 15, 600.0 - z * 100, 20.0],
        )

    # vo2_max
    conn.execute(
        "INSERT INTO vo2_max VALUES (?, 48.5, 49.0, '2025-06-15', 1)",
        [ACTIVITY_ID],
    )

    # lactate_threshold
    conn.execute(
        "INSERT INTO lactate_threshold VALUES (?, 165, 3.5, '2025-06-10 08:00:00', 280, 3.73, 75.0, '2025-06-10 08:00:00')",
        [ACTIVITY_ID],
    )

    conn.close()
    return PhysiologyReader(db_path=str(reader_db_path))


# ---------------------------------------------------------------------------
# _get_vo2_max_category — 5-branch exhaustive
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetVo2MaxCategory:
    """Exhaustive parametrize of _get_vo2_max_category()."""

    @pytest.mark.parametrize(
        "value, expected",
        [
            (None, "不明"),
            (50.0, "優秀"),
            (47.0, "優秀"),
            (45.0, "良好"),
            (42.0, "良好"),
            (40.0, "平均"),
            (38.0, "平均"),
            (36.0, "やや低い"),
            (34.0, "やや低い"),
            (30.0, "低い"),
            (33.9, "低い"),
        ],
    )
    def test_category(self, value: float | None, expected: str):
        assert PhysiologyReader._get_vo2_max_category(value) == expected


# ---------------------------------------------------------------------------
# get_hr_efficiency_analysis
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetHrEfficiency:
    """Tests for PhysiologyReader.get_hr_efficiency_analysis()."""

    def test_returns_data(self, phys_reader: PhysiologyReader):
        result = phys_reader.get_hr_efficiency_analysis(ACTIVITY_ID)
        assert result is not None
        assert result["training_type"] == "easy_run"

    def test_bool_conversion(self, phys_reader: PhysiologyReader):
        """DuckDB BOOLEAN → Python bool."""
        result = phys_reader.get_hr_efficiency_analysis(ACTIVITY_ID)
        assert result is not None
        assert result["zone2_focus"] is True
        assert result["zone4_threshold_work"] is False
        assert isinstance(result["zone2_focus"], bool)

    def test_zone_percentages_nested(self, phys_reader: PhysiologyReader):
        result = phys_reader.get_hr_efficiency_analysis(ACTIVITY_ID)
        assert result is not None
        zp = result["zone_percentages"]
        assert zp["zone1"] == 10.0
        assert zp["zone2"] == 55.0

    def test_missing_activity(self, phys_reader: PhysiologyReader):
        assert phys_reader.get_hr_efficiency_analysis(MISSING_ID) is None


# ---------------------------------------------------------------------------
# get_heart_rate_zones_detail
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetHeartRateZones:
    """Tests for PhysiologyReader.get_heart_rate_zones_detail()."""

    def test_returns_zones_list(self, phys_reader: PhysiologyReader):
        result = phys_reader.get_heart_rate_zones_detail(ACTIVITY_ID)
        assert result is not None
        assert "zones" in result
        assert len(result["zones"]) == 5

    def test_zone_order(self, phys_reader: PhysiologyReader):
        result = phys_reader.get_heart_rate_zones_detail(ACTIVITY_ID)
        assert result is not None
        numbers = [z["zone_number"] for z in result["zones"]]
        assert numbers == [1, 2, 3, 4, 5]

    def test_zone_structure(self, phys_reader: PhysiologyReader):
        result = phys_reader.get_heart_rate_zones_detail(ACTIVITY_ID)
        assert result is not None
        zone = result["zones"][0]
        assert "low_boundary" in zone
        assert "high_boundary" in zone
        assert "time_in_zone_seconds" in zone
        assert "zone_percentage" in zone

    def test_missing_activity(self, phys_reader: PhysiologyReader):
        assert phys_reader.get_heart_rate_zones_detail(MISSING_ID) is None


# ---------------------------------------------------------------------------
# get_vo2_max_data
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetVo2MaxData:
    """Tests for PhysiologyReader.get_vo2_max_data()."""

    def test_direct_match(self, phys_reader: PhysiologyReader):
        result = phys_reader.get_vo2_max_data(ACTIVITY_ID)
        assert result is not None
        assert result["precise_value"] == 48.5
        assert result["category"] == "優秀"

    def test_date_is_str(self, phys_reader: PhysiologyReader):
        """Date must be stringified, not datetime.date."""
        result = phys_reader.get_vo2_max_data(ACTIVITY_ID)
        assert result is not None
        assert isinstance(result["date"], str)

    def test_missing_activity(self, phys_reader: PhysiologyReader):
        assert phys_reader.get_vo2_max_data(MISSING_ID) is None


# ---------------------------------------------------------------------------
# get_lactate_threshold_data
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetLactateThreshold:
    """Tests for PhysiologyReader.get_lactate_threshold_data()."""

    def test_returns_data(self, phys_reader: PhysiologyReader):
        result = phys_reader.get_lactate_threshold_data(ACTIVITY_ID)
        assert result is not None
        assert result["heart_rate"] == 165
        assert result["speed_mps"] == 3.5

    def test_date_is_str(self, phys_reader: PhysiologyReader):
        result = phys_reader.get_lactate_threshold_data(ACTIVITY_ID)
        assert result is not None
        assert isinstance(result["date_hr"], str)
        assert isinstance(result["date_power"], str)

    def test_missing_activity(self, phys_reader: PhysiologyReader):
        assert phys_reader.get_lactate_threshold_data(MISSING_ID) is None
