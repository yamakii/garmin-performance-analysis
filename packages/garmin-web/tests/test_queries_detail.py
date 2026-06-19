"""Unit tests for garmin_web.queries.detail.get_activity_detail."""

import pytest
from garmin_mcp.database.connection import get_connection

from garmin_web.queries.detail import get_activity_detail

FULL_ACTIVITY_ID = 9000000101
PARTIAL_ACTIVITY_ID = 9000000102

# Full expected key sets per sub-table, mirroring the explicit-column lists in
# queries/detail.py (= the production schema in db_writer.py + migrations).
# Guards against a column silently dropped from the SELECT lists (Issue #369).
_EXPECTED_ACTIVITY_KEYS = {
    "activity_id",
    "activity_date",
    "activity_name",
    "start_time_local",
    "start_time_gmt",
    "location_name",
    "total_distance_km",
    "total_time_seconds",
    "avg_speed_ms",
    "avg_pace_seconds_per_km",
    "avg_heart_rate",
    "max_heart_rate",
    "temp_celsius",
    "relative_humidity_percent",
    "wind_speed_kmh",
    "wind_direction",
    "gear_type",
    "gear_model",
    "base_weight_kg",
    "body_mass_kg",
}

_EXPECTED_SPLIT_KEYS = {
    "activity_id",
    "split_index",
    "distance",
    "duration_seconds",
    "start_time_gmt",
    "start_time_s",
    "end_time_s",
    "intensity_type",
    "role_phase",
    "pace_str",
    "pace_seconds_per_km",
    "heart_rate",
    "hr_zone",
    "cadence",
    "cadence_rating",
    "power",
    "power_efficiency",
    "stride_length",
    "ground_contact_time",
    "vertical_oscillation",
    "vertical_ratio",
    "elevation_gain",
    "elevation_loss",
    "terrain_type",
    "environmental_conditions",
    "wind_impact",
    "temp_impact",
    "environmental_impact",
    "max_heart_rate",
    "max_cadence",
    "max_power",
    "normalized_power",
    "average_speed",
    "grade_adjusted_speed",
}

_EXPECTED_FORM_EFFICIENCY_KEYS = {
    "activity_id",
    "gct_average",
    "gct_min",
    "gct_max",
    "gct_std",
    "gct_variability",
    "gct_rating",
    "gct_evaluation",
    "vo_average",
    "vo_min",
    "vo_max",
    "vo_std",
    "vo_trend",
    "vo_rating",
    "vo_evaluation",
    "vr_average",
    "vr_min",
    "vr_max",
    "vr_std",
    "vr_rating",
    "vr_evaluation",
}

_EXPECTED_HR_ZONE_KEYS = {
    "activity_id",
    "zone_number",
    "zone_low_boundary",
    "zone_high_boundary",
    "time_in_zone_seconds",
    "zone_percentage",
}

_EXPECTED_PERFORMANCE_TRENDS_KEYS = {
    "activity_id",
    "pace_consistency",
    "hr_drift_percentage",
    "cadence_consistency",
    "fatigue_pattern",
    "warmup_splits",
    "warmup_avg_pace_seconds_per_km",
    "warmup_avg_pace_str",
    "warmup_avg_hr",
    "warmup_avg_cadence",
    "warmup_avg_power",
    "warmup_evaluation",
    "run_splits",
    "run_avg_pace_seconds_per_km",
    "run_avg_pace_str",
    "run_avg_hr",
    "run_avg_cadence",
    "run_avg_power",
    "run_evaluation",
    "recovery_splits",
    "recovery_avg_pace_seconds_per_km",
    "recovery_avg_pace_str",
    "recovery_avg_hr",
    "recovery_avg_cadence",
    "recovery_avg_power",
    "recovery_evaluation",
    "cooldown_splits",
    "cooldown_avg_pace_seconds_per_km",
    "cooldown_avg_pace_str",
    "cooldown_avg_hr",
    "cooldown_avg_cadence",
    "cooldown_avg_power",
    "cooldown_evaluation",
}

_EXPECTED_FORM_EVALUATIONS_KEYS = {
    "eval_id",
    "activity_id",
    "gct_ms_expected",
    "vo_cm_expected",
    "vr_pct_expected",
    "gct_ms_actual",
    "vo_cm_actual",
    "vr_pct_actual",
    "gct_delta_pct",
    "vo_delta_cm",
    "vr_delta_pct",
    "gct_penalty",
    "gct_star_rating",
    "gct_score",
    "gct_needs_improvement",
    "gct_evaluation_text",
    "vo_penalty",
    "vo_star_rating",
    "vo_score",
    "vo_needs_improvement",
    "vo_evaluation_text",
    "vr_penalty",
    "vr_star_rating",
    "vr_score",
    "vr_needs_improvement",
    "vr_evaluation_text",
    "cadence_actual",
    "cadence_minimum",
    "cadence_achieved",
    "overall_score",
    "overall_star_rating",
    "power_avg_w",
    "power_wkg",
    "speed_actual_mps",
    "speed_expected_mps",
    "power_efficiency_score",
    "power_efficiency_rating",
    "power_efficiency_needs_improvement",
    "integrated_score",
    "training_mode",
    "evaluated_at",
    "cadence_expected",
    "cadence_delta_pct",
    "cadence_star_rating",
    "cadence_score",
    "cadence_needs_improvement",
    "cadence_evaluation_text",
}


@pytest.mark.unit
def test_detail_aggregates_tables(detail_db_path):
    with get_connection(detail_db_path) as conn:
        detail = get_activity_detail(conn, FULL_ACTIVITY_ID)

    assert detail is not None
    for key in (
        "activity",
        "splits",
        "form_efficiency",
        "hr_zones",
        "performance_trends",
        "form_evaluations",
    ):
        assert key in detail

    assert detail["activity"]["activity_id"] == FULL_ACTIVITY_ID
    assert detail["activity"]["activity_date"] == "2025-10-09"
    assert isinstance(detail["activity"]["activity_date"], str)

    # splits: 5 rows sorted by split_index ascending
    assert len(detail["splits"]) == 5
    assert [s["split_index"] for s in detail["splits"]] == [1, 2, 3, 4, 5]

    assert detail["form_efficiency"]["gct_average"] == 248.0
    assert len(detail["hr_zones"]) == 5
    assert [z["zone_number"] for z in detail["hr_zones"]] == [1, 2, 3, 4, 5]
    assert detail["performance_trends"]["pace_consistency"] == 4.2
    assert detail["form_evaluations"]["overall_score"] == pytest.approx(4.1)


@pytest.mark.unit
def test_detail_includes_physiology(detail_db_path):
    with get_connection(detail_db_path) as conn:
        detail = get_activity_detail(conn, FULL_ACTIVITY_ID)

    assert detail is not None
    assert detail["vo2_max"] is not None
    assert detail["vo2_max"]["value"] == pytest.approx(49.6)
    assert detail["vo2_max"]["date"] == "2025-10-09"
    assert detail["lactate_threshold"] is not None
    assert detail["lactate_threshold"]["heart_rate"] == 168
    assert detail["lactate_threshold"]["speed_mps"] == pytest.approx(3.2)
    assert isinstance(detail["lactate_threshold"]["date_hr"], str)


@pytest.mark.unit
def test_detail_physiology_missing_is_none(detail_db_path):
    with get_connection(detail_db_path) as conn:
        detail = get_activity_detail(conn, PARTIAL_ACTIVITY_ID)

    assert detail is not None
    assert detail["vo2_max"] is None
    assert detail["lactate_threshold"] is None


@pytest.mark.unit
def test_detail_missing_activity_returns_none(detail_db_path):
    with get_connection(detail_db_path) as conn:
        detail = get_activity_detail(conn, 999999)

    assert detail is None


@pytest.mark.integration
def test_get_activity_detail_column_keys_stable(detail_db_path):
    """Each sub-table dict exposes its full expected key set (Issue #369).

    Guards the explicit-column SELECT lists in queries/detail.py against an
    accidentally dropped column that would silently remove a JSON response key.
    """
    with get_connection(detail_db_path) as conn:
        detail = get_activity_detail(conn, FULL_ACTIVITY_ID)

    assert detail is not None

    assert set(detail["activity"].keys()) == _EXPECTED_ACTIVITY_KEYS

    assert detail["splits"], "expected at least one split row"
    assert set(detail["splits"][0].keys()) == _EXPECTED_SPLIT_KEYS

    assert detail["form_efficiency"] is not None
    assert set(detail["form_efficiency"].keys()) == _EXPECTED_FORM_EFFICIENCY_KEYS

    assert detail["hr_zones"], "expected at least one HR zone row"
    assert set(detail["hr_zones"][0].keys()) == _EXPECTED_HR_ZONE_KEYS

    assert detail["performance_trends"] is not None
    assert set(detail["performance_trends"].keys()) == _EXPECTED_PERFORMANCE_TRENDS_KEYS

    assert detail["form_evaluations"] is not None
    assert set(detail["form_evaluations"].keys()) == _EXPECTED_FORM_EVALUATIONS_KEYS


@pytest.mark.unit
def test_detail_partial_data(detail_db_path):
    with get_connection(detail_db_path) as conn:
        detail = get_activity_detail(conn, PARTIAL_ACTIVITY_ID)

    assert detail is not None
    assert detail["form_efficiency"] is None
    assert detail["performance_trends"] is None
    assert detail["form_evaluations"] is None
    assert detail["hr_zones"] == []
    # Other data is still returned
    assert detail["activity"]["activity_name"] == "Partial Run"
    assert len(detail["splits"]) == 2
