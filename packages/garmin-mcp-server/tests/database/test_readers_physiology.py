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


# ---------------------------------------------------------------------------
# get_form_baseline_trend (extracted from PhysiologyHandler in Issue #235)
# ---------------------------------------------------------------------------


def _seed_baseline_history(db_path: Path) -> None:
    """Insert current (October) and previous (September) baselines.

    Mirrors the previous handler's two-period comparison logic so the
    reader output can be validated against known expectations.
    """
    conn = duckdb.connect(str(db_path))
    rows = [
        # (user_id, condition_group, metric, coef_d, coef_b, period_start, period_end)
        ("default", "flat_road", "GCT", -0.15, 260.0, "2025-10-01", "2025-10-31"),
        ("default", "flat_road", "VO", 0.02, 8.0, "2025-10-01", "2025-10-31"),
        ("default", "flat_road", "GCT", -0.12, 265.0, "2025-09-01", "2025-09-30"),
        ("default", "flat_road", "VO", 0.025, 8.5, "2025-09-01", "2025-09-30"),
    ]
    for i, (uid, cg, metric, cd, cb, ps, pe) in enumerate(rows):
        conn.execute(
            """
            INSERT INTO form_baseline_history
                (history_id, user_id, condition_group, metric,
                 coef_d, coef_b, period_start, period_end)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [i, uid, cg, metric, cd, cb, ps, pe],
        )
    conn.close()


@pytest.mark.unit
class TestGetFormBaselineTrend:
    """Tests for PhysiologyReader.get_form_baseline_trend()."""

    def test_success_both_periods(self, reader_db_path: Path):
        _seed_baseline_history(reader_db_path)
        reader = PhysiologyReader(db_path=str(reader_db_path))

        result = reader.get_form_baseline_trend(12345, "2025-10-15")

        assert result["success"] is True
        assert result["activity_id"] == 12345
        assert result["activity_date"] == "2025-10-15"
        gct = result["metrics"]["GCT"]
        # coef columns are FLOAT in DuckDB → compare with tolerance.
        assert gct["current"]["coef_d"] == pytest.approx(-0.15)
        assert gct["previous"]["coef_d"] == pytest.approx(-0.12)
        assert gct["delta_d"] == pytest.approx(-0.15 - (-0.12))
        assert gct["delta_b"] == pytest.approx(260.0 - 265.0)

    def test_no_current_baseline(self, reader_db_path: Path):
        # No baselines seeded → no current period match.
        reader = PhysiologyReader(db_path=str(reader_db_path))
        result = reader.get_form_baseline_trend(12345, "2025-10-15")
        assert result["success"] is False
        assert "No baseline found" in result["error"]

    def test_no_previous_baseline(self, reader_db_path: Path):
        # Seed only the current (October) period.
        conn = duckdb.connect(str(reader_db_path))
        conn.execute("""
            INSERT INTO form_baseline_history
                (history_id, user_id, condition_group, metric,
                 coef_d, coef_b, period_start, period_end)
            VALUES (0, 'default', 'flat_road', 'GCT',
                    -0.15, 260.0, '2025-10-01', '2025-10-31')
            """)
        conn.close()
        reader = PhysiologyReader(db_path=str(reader_db_path))
        result = reader.get_form_baseline_trend(12345, "2025-10-15")
        assert result["success"] is False
        assert "No previous baseline found" in result["error"]

    def test_custom_user_id_and_condition_group(self, reader_db_path: Path):
        # Seed under a custom user_id/condition_group only.
        conn = duckdb.connect(str(reader_db_path))
        custom = [
            ("runner1", "hilly", "GCT", -0.15, 260.0, "2025-10-01", "2025-10-31"),
            ("runner1", "hilly", "GCT", -0.12, 265.0, "2025-09-01", "2025-09-30"),
        ]
        for i, (uid, cg, metric, cd, cb, ps, pe) in enumerate(custom):
            conn.execute(
                """
                INSERT INTO form_baseline_history
                    (history_id, user_id, condition_group, metric,
                     coef_d, coef_b, period_start, period_end)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [i, uid, cg, metric, cd, cb, ps, pe],
            )
        conn.close()
        reader = PhysiologyReader(db_path=str(reader_db_path))

        # Default user/group → not found.
        default_result = reader.get_form_baseline_trend(12345, "2025-10-15")
        assert default_result["success"] is False

        # Custom user/group → success.
        custom_result = reader.get_form_baseline_trend(
            12345, "2025-10-15", user_id="runner1", condition_group="hilly"
        )
        assert custom_result["success"] is True
        assert "GCT" in custom_result["metrics"]

    def test_delta_with_none_coef(self, reader_db_path: Path):
        conn = duckdb.connect(str(reader_db_path))
        rows = [
            ("default", "flat_road", "GCT", None, 260.0, "2025-10-01", "2025-10-31"),
            ("default", "flat_road", "GCT", -0.12, 265.0, "2025-09-01", "2025-09-30"),
        ]
        for i, (uid, cg, metric, cd, cb, ps, pe) in enumerate(rows):
            conn.execute(
                """
                INSERT INTO form_baseline_history
                    (history_id, user_id, condition_group, metric,
                     coef_d, coef_b, period_start, period_end)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [i, uid, cg, metric, cd, cb, ps, pe],
            )
        conn.close()
        reader = PhysiologyReader(db_path=str(reader_db_path))
        result = reader.get_form_baseline_trend(12345, "2025-10-15")
        gct = result["metrics"]["GCT"]
        # delta_d omitted because current coef_d is None.
        assert "delta_d" not in gct
        assert gct["delta_b"] == pytest.approx(260.0 - 265.0)

    def test_power_delta_both_periods(self, reader_db_path: Path):
        # Power stores its trend in power_a/power_b (coef_d/coef_b are NULL).
        conn = duckdb.connect(str(reader_db_path))
        rows = [
            # (hid, metric, coef_d, coef_b, power_a, power_b, start, end)
            (0, "power", None, None, 0.24, 0.63, "2025-10-01", "2025-10-31"),
            (1, "power", None, None, 0.20, 0.55, "2025-09-01", "2025-09-30"),
        ]
        for hid, metric, cd, cb, pa, pb, ps, pe in rows:
            conn.execute(
                """
                INSERT INTO form_baseline_history
                    (history_id, user_id, condition_group, metric,
                     coef_d, coef_b, power_a, power_b, period_start, period_end)
                VALUES (?, 'default', 'flat_road', ?, ?, ?, ?, ?, ?, ?)
                """,
                [hid, metric, cd, cb, pa, pb, ps, pe],
            )
        conn.close()
        reader = PhysiologyReader(db_path=str(reader_db_path))
        result = reader.get_form_baseline_trend(12345, "2025-10-15")

        assert result["success"] is True
        power = result["metrics"]["power"]
        assert power["current"]["power_a"] == pytest.approx(0.24)
        assert power["current"]["power_b"] == pytest.approx(0.63)
        assert power["previous"]["power_a"] == pytest.approx(0.20)
        assert power["delta_power_a"] == pytest.approx(0.24 - 0.20)
        assert power["delta_power_b"] == pytest.approx(0.63 - 0.55)
        # coef_* are NULL for power → no coef deltas emitted.
        assert power["current"]["coef_d"] is None
        assert power["current"]["coef_b"] is None
        assert "delta_d" not in power
        assert "delta_b" not in power

    def test_power_no_previous_omits_delta(self, reader_db_path: Path):
        # Current power row exists but no previous power row. A previous GCT row
        # keeps the overall comparison successful; power just gets no delta.
        conn = duckdb.connect(str(reader_db_path))
        rows = [
            (0, "GCT", -0.15, 260.0, None, None, "2025-10-01", "2025-10-31"),
            (1, "GCT", -0.12, 265.0, None, None, "2025-09-01", "2025-09-30"),
            (2, "power", None, None, 0.24, 0.63, "2025-10-01", "2025-10-31"),
        ]
        for hid, metric, cd, cb, pa, pb, ps, pe in rows:
            conn.execute(
                """
                INSERT INTO form_baseline_history
                    (history_id, user_id, condition_group, metric,
                     coef_d, coef_b, power_a, power_b, period_start, period_end)
                VALUES (?, 'default', 'flat_road', ?, ?, ?, ?, ?, ?, ?)
                """,
                [hid, metric, cd, cb, pa, pb, ps, pe],
            )
        conn.close()
        reader = PhysiologyReader(db_path=str(reader_db_path))
        result = reader.get_form_baseline_trend(12345, "2025-10-15")

        assert result["success"] is True
        power = result["metrics"]["power"]
        assert power["current"]["power_a"] == pytest.approx(0.24)
        assert "previous" not in power
        assert "delta_power_a" not in power
        assert "delta_power_b" not in power

    def test_power_a_b_keys_present_all_metrics(self, reader_db_path: Path):
        # Non-power metrics carry power_a/power_b keys (value None), mirroring
        # how power rows carry coef_d/coef_b as None.
        _seed_baseline_history(reader_db_path)
        reader = PhysiologyReader(db_path=str(reader_db_path))
        result = reader.get_form_baseline_trend(12345, "2025-10-15")

        gct = result["metrics"]["GCT"]
        assert gct["current"]["power_a"] is None
        assert gct["current"]["power_b"] is None
        assert gct["previous"]["power_a"] is None
        assert gct["previous"]["power_b"] is None

    def test_baseline_reader_matches_handler(self, reader_db_path: Path):
        """Extracted reader returns the exact dict the old handler produced.

        The previous PhysiologyHandler._get_form_baseline_trend built this
        structure inline; this asserts the migration is behavior-preserving.
        """
        _seed_baseline_history(reader_db_path)
        reader = PhysiologyReader(db_path=str(reader_db_path))

        result = reader.get_form_baseline_trend(12345, "2025-10-15")

        # Top-level envelope matches the old handler exactly.
        assert result["success"] is True
        assert result["activity_id"] == 12345
        assert result["activity_date"] == "2025-10-15"
        assert set(result["metrics"].keys()) == {"GCT", "VO"}

        # Expected per-metric coefficients (coef_* columns are FLOAT → approx).
        # Each tuple: (curr_d, curr_b, prev_d, prev_b).
        expected_metrics: dict[str, tuple[float, float, float, float]] = {
            "GCT": (-0.15, 260.0, -0.12, 265.0),
            "VO": (0.02, 8.0, 0.025, 8.5),
        }
        for metric, (curr_d, curr_b, prev_d, prev_b) in expected_metrics.items():
            block = result["metrics"][metric]
            # Structure preserved (current/previous/delta keys + period strings).
            assert set(block.keys()) == {
                "current",
                "previous",
                "delta_d",
                "delta_b",
            }
            assert block["current"]["coef_d"] == pytest.approx(curr_d)
            assert block["current"]["coef_b"] == pytest.approx(curr_b)
            assert block["current"]["period"] == "2025-10-01 to 2025-10-31"
            assert block["previous"]["coef_d"] == pytest.approx(prev_d)
            assert block["previous"]["coef_b"] == pytest.approx(prev_b)
            assert block["previous"]["period"] == "2025-09-01 to 2025-09-30"
            assert block["delta_d"] == pytest.approx(curr_d - prev_d)
            assert block["delta_b"] == pytest.approx(curr_b - prev_b)
