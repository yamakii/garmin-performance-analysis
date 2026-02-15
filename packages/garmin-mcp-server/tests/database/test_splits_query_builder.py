"""Tests for splits_query_builder module."""

import pytest

from garmin_mcp.database.readers.splits_query_builder import (
    COMPREHENSIVE_FULL_DEFAULTS,
    COMPREHENSIVE_FULL_KEYS,
    COMPREHENSIVE_STAT_FIELDS,
    ELEVATION_EXTRA_KEYS,
    ELEVATION_FULL_KEYS,
    FORM_FIELDS,
    FORM_FULL_KEYS,
    PACE_HR_FIELDS,
    PACE_HR_FULL_KEYS,
    STAT_FUNCS,
    STAT_KEYS,
    SplitField,
    build_full_sql,
    build_statistics_sql,
    empty_stats_result,
    parse_full_result,
    parse_statistics_result,
)


class TestBuildStatisticsSQL:
    """Tests for build_statistics_sql."""

    @pytest.mark.unit
    def test_generates_correct_aggregate_functions(self):
        """Each field should produce AVG/MEDIAN/STDDEV/MIN/MAX."""
        fields = (SplitField("col_a", "metric_a", "key_a"),)
        sql = build_statistics_sql(fields)
        for func in STAT_FUNCS:
            assert f"{func}(col_a)" in sql

    @pytest.mark.unit
    def test_multiple_fields(self):
        """Multiple fields produce N*5 select expressions."""
        sql = build_statistics_sql(PACE_HR_FIELDS)
        # 2 fields * 5 funcs = 10 expressions
        assert "AVG(pace_seconds_per_km)" in sql
        assert "MAX(heart_rate)" in sql
        assert "WHERE activity_id = ?" in sql

    @pytest.mark.unit
    def test_comprehensive_fields_count(self):
        """Comprehensive should have 12 fields * 5 funcs = 60 expressions."""
        sql = build_statistics_sql(COMPREHENSIVE_STAT_FIELDS)
        # Count occurrences of "as " which appears for each alias
        assert sql.count(" as ") == 60


class TestParseStatisticsResult:
    """Tests for parse_statistics_result."""

    @pytest.mark.unit
    def test_none_result_returns_empty_metrics(self):
        result = parse_statistics_result(None, PACE_HR_FIELDS, 123)
        assert result == {"activity_id": 123, "statistics_only": True, "metrics": {}}

    @pytest.mark.unit
    def test_first_element_none_returns_empty_metrics(self):
        result = parse_statistics_result((None,) * 10, PACE_HR_FIELDS, 123)
        assert result["metrics"] == {}

    @pytest.mark.unit
    def test_parses_pace_hr_correctly(self):
        # 2 fields * 5 stats = 10 values
        values = (300.0, 310.0, 5.0, 280.0, 350.0, 160.0, 158.0, 3.0, 150.0, 170.0)
        result = parse_statistics_result(values, PACE_HR_FIELDS, 42)

        assert result["activity_id"] == 42
        assert result["statistics_only"] is True
        assert result["metrics"]["pace"]["mean"] == 300.0
        assert result["metrics"]["pace"]["median"] == 310.0
        assert result["metrics"]["heart_rate"]["min"] == 150.0
        assert result["metrics"]["heart_rate"]["max"] == 170.0

    @pytest.mark.unit
    def test_none_values_become_zero(self):
        values = (300.0, None, 5.0, 280.0, None, 160.0, None, 3.0, 150.0, 170.0)
        result = parse_statistics_result(values, PACE_HR_FIELDS, 1)

        assert result["metrics"]["pace"]["median"] == 0.0
        assert result["metrics"]["pace"]["max"] == 0.0
        assert result["metrics"]["heart_rate"]["median"] == 0.0


class TestBuildFullSQL:
    """Tests for build_full_sql."""

    @pytest.mark.unit
    def test_generates_correct_columns(self):
        sql = build_full_sql(("split_index", "distance", "pace_seconds_per_km"))
        assert "split_index" in sql
        assert "distance" in sql
        assert "pace_seconds_per_km" in sql
        assert "ORDER BY split_index" in sql

    @pytest.mark.unit
    def test_where_clause(self):
        sql = build_full_sql(("split_index",))
        assert "WHERE activity_id = ?" in sql


class TestParseFullResult:
    """Tests for parse_full_result."""

    @pytest.mark.unit
    def test_empty_rows_returns_empty_splits(self):
        result = parse_full_result([], PACE_HR_FULL_KEYS)
        assert result == {"splits": []}

    @pytest.mark.unit
    def test_maps_keys_correctly(self):
        rows = [(1, 1.0, 310, 152), (2, 1.0, 320, 154)]
        result = parse_full_result(rows, PACE_HR_FULL_KEYS)

        assert len(result["splits"]) == 2
        assert result["splits"][0]["split_number"] == 1
        assert result["splits"][0]["avg_pace_seconds_per_km"] == 310
        assert result["splits"][1]["avg_heart_rate"] == 154

    @pytest.mark.unit
    def test_extra_keys_added(self):
        rows = [(1, 5.0, 3.0, "flat")]
        result = parse_full_result(
            rows, ELEVATION_FULL_KEYS, extra_keys=ELEVATION_EXTRA_KEYS
        )
        assert result["splits"][0]["max_elevation_m"] is None
        assert result["splits"][0]["min_elevation_m"] is None

    @pytest.mark.unit
    def test_defaults_applied_for_none(self):
        # Simulate comprehensive row with None for power (index 7) and intensity_type (index 14)
        row = (
            1,
            1.0,
            310,
            152,
            240,
            7.0,
            8.0,
            None,
            None,
            170,
            5,
            3,
            160,
            168,
            None,
            None,
        )
        result = parse_full_result(
            [row], COMPREHENSIVE_FULL_KEYS, defaults=COMPREHENSIVE_FULL_DEFAULTS
        )
        split = result["splits"][0]
        assert split["power_watts"] == 0.0
        assert split["stride_length_cm"] == 0.0
        assert split["intensity_type"] == ""
        assert split["role_phase"] == ""

    @pytest.mark.unit
    def test_no_defaults_preserves_none(self):
        rows = [(1, None, None, None)]
        result = parse_full_result(rows, PACE_HR_FULL_KEYS)
        assert result["splits"][0]["distance_km"] is None


class TestFieldDefinitions:
    """Tests for field constant definitions."""

    @pytest.mark.unit
    def test_stat_funcs_and_keys_aligned(self):
        assert len(STAT_FUNCS) == len(STAT_KEYS) == 5

    @pytest.mark.unit
    def test_form_fields_have_three_metrics(self):
        assert len(FORM_FIELDS) == 3
        keys = {f.stat_key for f in FORM_FIELDS}
        assert keys == {"ground_contact_time", "vertical_oscillation", "vertical_ratio"}

    @pytest.mark.unit
    def test_comprehensive_stat_fields_have_twelve_metrics(self):
        assert len(COMPREHENSIVE_STAT_FIELDS) == 12

    @pytest.mark.unit
    def test_full_columns_and_keys_aligned(self):
        """Full-mode column and key tuples must have same length."""
        from garmin_mcp.database.readers.splits_query_builder import (
            COMPREHENSIVE_FULL_COLUMNS,
            ELEVATION_FULL_COLUMNS,
            FORM_FULL_COLUMNS,
            PACE_HR_FULL_COLUMNS,
        )

        assert len(PACE_HR_FULL_COLUMNS) == len(PACE_HR_FULL_KEYS)
        assert len(FORM_FULL_COLUMNS) == len(FORM_FULL_KEYS)
        assert len(ELEVATION_FULL_COLUMNS) == len(ELEVATION_FULL_KEYS)
        assert len(COMPREHENSIVE_FULL_COLUMNS) == len(COMPREHENSIVE_FULL_KEYS)


class TestEmptyStatsResult:
    """Tests for empty_stats_result helper."""

    @pytest.mark.unit
    def test_returns_correct_structure(self):
        result = empty_stats_result(999)
        assert result == {
            "activity_id": 999,
            "statistics_only": True,
            "metrics": {},
        }
