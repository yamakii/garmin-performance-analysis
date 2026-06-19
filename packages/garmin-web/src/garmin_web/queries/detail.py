"""Read-only queries aggregating per-activity detail data."""

import datetime
from typing import Any

import duckdb

# Explicit column lists mirror the production schemas in
# garmin_mcp/database/db_writer.py (and applied migrations). They reproduce the
# exact key set the previous ``SELECT *`` returned, so the JSON response shape
# (consumed by the frontend, including the dynamic ``Record`` sub-tables) is
# unchanged. Keep these in sync with the table schemas — the
# ``test_get_activity_detail_column_keys_stable`` regression test guards against
# a silently dropped key.
_ACTIVITIES_COLUMNS = (
    "activity_id, activity_date, activity_name, start_time_local,"
    " start_time_gmt, location_name, total_distance_km, total_time_seconds,"
    " avg_speed_ms, avg_pace_seconds_per_km, avg_heart_rate, max_heart_rate,"
    " temp_celsius, relative_humidity_percent, wind_speed_kmh, wind_direction,"
    " gear_type, gear_model, base_weight_kg, body_mass_kg"
)

_SPLITS_COLUMNS = (
    "activity_id, split_index, distance, duration_seconds, start_time_gmt,"
    " start_time_s, end_time_s, intensity_type, role_phase, pace_str,"
    " pace_seconds_per_km, heart_rate, hr_zone, cadence, cadence_rating, power,"
    " power_efficiency, stride_length, ground_contact_time,"
    " vertical_oscillation, vertical_ratio, elevation_gain, elevation_loss,"
    " terrain_type, environmental_conditions, wind_impact, temp_impact,"
    " environmental_impact, max_heart_rate, max_cadence, max_power,"
    " normalized_power, average_speed, grade_adjusted_speed"
)

_FORM_EFFICIENCY_COLUMNS = (
    "activity_id, gct_average, gct_min, gct_max, gct_std, gct_variability,"
    " gct_rating, gct_evaluation, vo_average, vo_min, vo_max, vo_std, vo_trend,"
    " vo_rating, vo_evaluation, vr_average, vr_min, vr_max, vr_std, vr_rating,"
    " vr_evaluation"
)

_HR_ZONES_COLUMNS = (
    "activity_id, zone_number, zone_low_boundary, zone_high_boundary,"
    " time_in_zone_seconds, zone_percentage"
)

_PERFORMANCE_TRENDS_COLUMNS = (
    "activity_id, pace_consistency, hr_drift_percentage, cadence_consistency,"
    " fatigue_pattern, warmup_splits, warmup_avg_pace_seconds_per_km,"
    " warmup_avg_pace_str, warmup_avg_hr, warmup_avg_cadence, warmup_avg_power,"
    " warmup_evaluation, run_splits, run_avg_pace_seconds_per_km,"
    " run_avg_pace_str, run_avg_hr, run_avg_cadence, run_avg_power,"
    " run_evaluation, recovery_splits, recovery_avg_pace_seconds_per_km,"
    " recovery_avg_pace_str, recovery_avg_hr, recovery_avg_cadence,"
    " recovery_avg_power, recovery_evaluation, cooldown_splits,"
    " cooldown_avg_pace_seconds_per_km, cooldown_avg_pace_str, cooldown_avg_hr,"
    " cooldown_avg_cadence, cooldown_avg_power, cooldown_evaluation"
)

_FORM_EVALUATIONS_COLUMNS = (
    "eval_id, activity_id, gct_ms_expected, vo_cm_expected, vr_pct_expected,"
    " gct_ms_actual, vo_cm_actual, vr_pct_actual, gct_delta_pct, vo_delta_cm,"
    " vr_delta_pct, gct_penalty, gct_star_rating, gct_score,"
    " gct_needs_improvement, gct_evaluation_text, vo_penalty, vo_star_rating,"
    " vo_score, vo_needs_improvement, vo_evaluation_text, vr_penalty,"
    " vr_star_rating, vr_score, vr_needs_improvement, vr_evaluation_text,"
    " cadence_actual, cadence_minimum, cadence_achieved, overall_score,"
    " overall_star_rating, power_avg_w, power_wkg, speed_actual_mps,"
    " speed_expected_mps, power_efficiency_score, power_efficiency_rating,"
    " power_efficiency_needs_improvement, integrated_score, training_mode,"
    " evaluated_at, cadence_expected, cadence_delta_pct, cadence_star_rating,"
    " cadence_score, cadence_needs_improvement, cadence_evaluation_text"
)


def _to_jsonable(value: Any) -> Any:
    """Convert DuckDB date/datetime values to str for JSON serialization."""
    if isinstance(value, datetime.date | datetime.datetime):
        return str(value)
    return value


def _row_to_dict(columns: list[str], row: tuple) -> dict:
    return {col: _to_jsonable(val) for col, val in zip(columns, row, strict=True)}


def _fetch_one(conn: duckdb.DuckDBPyConnection, sql: str, params: list) -> dict | None:
    result = conn.execute(sql, params)
    columns = [desc[0] for desc in result.description]
    row = result.fetchone()
    return _row_to_dict(columns, row) if row is not None else None


def _fetch_all(conn: duckdb.DuckDBPyConnection, sql: str, params: list) -> list[dict]:
    result = conn.execute(sql, params)
    columns = [desc[0] for desc in result.description]
    return [_row_to_dict(columns, row) for row in result.fetchall()]


def get_activity_detail(
    conn: duckdb.DuckDBPyConnection, activity_id: int
) -> dict | None:
    """Aggregate activity detail data into a single dict.

    Combines activities, splits, form_efficiency, heart_rate_zones,
    performance_trends, form_evaluations, vo2_max and lactate_threshold.
    Splits are ordered by split_index ascending; HR zones by zone_number
    ascending.

    Args:
        conn: Open DuckDB connection (read-only is sufficient).
        activity_id: Target activity ID.

    Returns:
        Dict with keys: activity, splits, form_efficiency, hr_zones,
        performance_trends, form_evaluations, vo2_max, lactate_threshold.
        Single-row tables that have no row for the activity are None;
        list tables are empty lists.
        Returns None if the activity itself does not exist.
    """
    activity = _fetch_one(
        conn,
        f"SELECT {_ACTIVITIES_COLUMNS} FROM activities WHERE activity_id = ?",
        [activity_id],
    )
    if activity is None:
        return None
    return {
        "activity": activity,
        "splits": _fetch_all(
            conn,
            f"SELECT {_SPLITS_COLUMNS} FROM splits"
            " WHERE activity_id = ? ORDER BY split_index",
            [activity_id],
        ),
        "form_efficiency": _fetch_one(
            conn,
            f"SELECT {_FORM_EFFICIENCY_COLUMNS} FROM form_efficiency"
            " WHERE activity_id = ?",
            [activity_id],
        ),
        "hr_zones": _fetch_all(
            conn,
            f"SELECT {_HR_ZONES_COLUMNS} FROM heart_rate_zones"
            " WHERE activity_id = ? ORDER BY zone_number",
            [activity_id],
        ),
        "performance_trends": _fetch_one(
            conn,
            f"SELECT {_PERFORMANCE_TRENDS_COLUMNS} FROM performance_trends"
            " WHERE activity_id = ?",
            [activity_id],
        ),
        "form_evaluations": _fetch_one(
            conn,
            f"SELECT {_FORM_EVALUATIONS_COLUMNS} FROM form_evaluations"
            " WHERE activity_id = ?",
            [activity_id],
        ),
        "vo2_max": _fetch_one(
            conn,
            "SELECT COALESCE(precise_value, value) AS value, date"
            " FROM vo2_max WHERE activity_id = ?",
            [activity_id],
        ),
        "lactate_threshold": _fetch_one(
            conn,
            "SELECT heart_rate, speed_mps, date_hr"
            " FROM lactate_threshold WHERE activity_id = ?",
            [activity_id],
        ),
    }
