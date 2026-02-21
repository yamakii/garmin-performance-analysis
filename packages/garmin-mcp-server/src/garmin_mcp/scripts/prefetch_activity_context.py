"""Pre-fetch shared activity context for analysis agents.

Queries DuckDB once for data that multiple agents would otherwise fetch independently,
reducing ~9 redundant MCP calls per activity to 0.

Usage:
    uv run python -m garmin_mcp.scripts.prefetch_activity_context 21884133706

Output (JSON to stdout):
    {
      "activity_id": 21884133706,
      "activity_date": "2026-02-16",
      "training_type": "aerobic_base",
      "temperature_c": 7.8,
      "humidity_pct": 84,
      "wind_mps": 1.1,
      "wind_direction": "NW",
      "terrain_category": "flat",
      "avg_elevation_gain_per_km": 1.6,
      "total_elevation_gain": 12.8,
      "total_elevation_loss": 11.2,
      "zone_percentages": {"zone1": 5.2, "zone2": 36.8, "zone3": 60.5, ...},
      "primary_zone": "Zone 3",
      "zone_distribution_rating": "appropriate",
      "hr_stability": "stable",
      "aerobic_efficiency": "good",
      "training_quality": "effective",
      "zone2_focus": false,
      "zone4_threshold_work": false,
      "form_scores": {
        "gct": {"star_rating": "★★★★★", "score": 4.8},
        "vo": {"star_rating": "★★★★☆", "score": 4.0},
        "vr": {"star_rating": "★★★★☆", "score": 4.0},
        "integrated_score": 92.5,
        "overall_score": 4.3,
        "overall_star_rating": "★★★★☆"
      },
      "phase_structure": {
        "pace_consistency": 0.017,
        "hr_drift_percentage": 2.5,
        "cadence_consistency": "stable",
        "fatigue_pattern": "none",
        "warmup": {"avg_pace": "6:33/km", "avg_hr": 134.0},
        "run": {"avg_pace": "5:45/km", "avg_hr": 155.0},
        "cooldown": {"avg_pace": "7:12/km", "avg_hr": 140.0}
      },
      "planned_workout": null
    }
"""

import argparse
import json
import sys

from garmin_mcp.database.connection import get_connection, get_db_path


def _classify_terrain(avg_gain_per_km: float | None) -> str:
    """Classify terrain based on average elevation gain per km."""
    if avg_gain_per_km is None:
        return "unknown"
    if avg_gain_per_km < 10:
        return "flat"
    if avg_gain_per_km < 30:
        return "undulating"
    if avg_gain_per_km < 50:
        return "hilly"
    return "mountainous"


def _build_phase_dict(row: tuple, has_recovery: bool) -> dict:
    """Build phase_structure dict from performance_trends query row.

    Column order matches Query 6 SELECT:
    0: pace_consistency, 1: hr_drift_percentage, 2: cadence_consistency,
    3: fatigue_pattern, 4-6: warmup (pace_str, hr, splits),
    7-9: run (pace_str, hr, splits), 10-12: recovery (pace_str, hr, splits),
    13-15: cooldown (pace_str, hr, splits)
    """
    result: dict = {
        "pace_consistency": row[0],
        "hr_drift_percentage": row[1],
        "cadence_consistency": row[2],
        "fatigue_pattern": row[3],
    }

    # Warmup phase
    if row[5]:  # warmup_splits not null
        result["warmup"] = {"avg_pace": row[4], "avg_hr": row[5] and round(row[5], 1)}

    # Run phase
    if row[8]:  # run_splits not null
        result["run"] = {"avg_pace": row[7], "avg_hr": row[8] and round(row[8], 1)}

    # Recovery phase (only for interval training)
    if has_recovery and row[11]:  # recovery_splits not null
        result["recovery"] = {
            "avg_pace": row[10],
            "avg_hr": row[11] and round(row[11], 1),
        }

    # Cooldown phase
    if row[14]:  # cooldown_splits not null
        result["cooldown"] = {
            "avg_pace": row[13],
            "avg_hr": row[14] and round(row[14], 1),
        }

    return result


def prefetch_activity_context(activity_id: int) -> dict:
    """Fetch shared context for all analysis agents in a single DB read.

    Args:
        activity_id: Garmin activity ID.

    Returns:
        Dict with training_type, weather, terrain, HR efficiency,
        form scores, phase structure, and planned_workout data.
    """
    db_path = get_db_path()

    with get_connection(db_path) as conn:
        # 1. Activity metadata + weather (from activities table)
        activity_row = conn.execute(
            """
            SELECT
                start_time_local::DATE AS activity_date,
                temp_celsius,
                relative_humidity_percent,
                wind_speed_kmh,
                wind_direction
            FROM activities
            WHERE activity_id = ?
            """,
            [activity_id],
        ).fetchone()

        if not activity_row:
            return {"error": f"Activity {activity_id} not found"}

        activity_date = str(activity_row[0])
        temp_c = activity_row[1]
        humidity = activity_row[2]
        wind_kmh = activity_row[3]
        wind_direction = activity_row[4]
        wind_mps = round(wind_kmh / 3.6, 1) if wind_kmh else None

        # 2. HR efficiency (C1: expanded from training_type only)
        hr_row = conn.execute(
            """
            SELECT
                training_type,
                primary_zone,
                zone_distribution_rating,
                hr_stability,
                aerobic_efficiency,
                training_quality,
                zone2_focus,
                zone4_threshold_work,
                zone1_percentage,
                zone2_percentage,
                zone3_percentage,
                zone4_percentage,
                zone5_percentage
            FROM hr_efficiency
            WHERE activity_id = ?
            """,
            [activity_id],
        ).fetchone()

        training_type = hr_row[0] if hr_row else None
        zone_percentages = None
        primary_zone = None
        zone_distribution_rating = None
        hr_stability = None
        aerobic_efficiency = None
        training_quality = None
        zone2_focus = None
        zone4_threshold_work = None

        if hr_row:
            zone_percentages = {
                "zone1": hr_row[8],
                "zone2": hr_row[9],
                "zone3": hr_row[10],
                "zone4": hr_row[11],
                "zone5": hr_row[12],
            }
            primary_zone = hr_row[1]
            zone_distribution_rating = hr_row[2]
            hr_stability = hr_row[3]
            aerobic_efficiency = hr_row[4]
            training_quality = hr_row[5]
            zone2_focus = hr_row[6]
            zone4_threshold_work = hr_row[7]

        # 3. Planned workout target (if training plan exists)
        planned_workout = None
        try:
            planned_row = conn.execute(
                """
                SELECT
                    pw.workout_type,
                    pw.description_ja,
                    pw.target_hr_low,
                    pw.target_hr_high,
                    pw.target_pace_low,
                    pw.target_pace_high,
                    pw.target_distance_km,
                    pw.target_duration_minutes,
                    pw.plan_id
                FROM planned_workouts pw
                JOIN training_plans tp
                    ON pw.plan_id = tp.plan_id AND pw.version = tp.version
                WHERE pw.workout_date = ?::DATE
                  AND pw.workout_type != 'rest'
                  AND tp.status = 'active'
                ORDER BY tp.version DESC
                LIMIT 1
                """,
                [activity_date],
            ).fetchone()

            if planned_row:
                planned_workout = {
                    "workout_type": planned_row[0],
                    "description_ja": planned_row[1],
                    "target_hr_low": planned_row[2],
                    "target_hr_high": planned_row[3],
                    "target_pace_low": planned_row[4],
                    "target_pace_high": planned_row[5],
                    "target_distance_km": planned_row[6],
                    "target_duration_minutes": planned_row[7],
                    "plan_id": planned_row[8],
                }
        except Exception:
            pass  # Table may not exist if no plan was ever saved

        # 4. Elevation statistics (from splits table)
        elev_row = conn.execute(
            """
            SELECT
                SUM(elevation_gain) AS total_gain,
                SUM(elevation_loss) AS total_loss,
                COUNT(*) AS split_count
            FROM splits
            WHERE activity_id = ?
            """,
            [activity_id],
        ).fetchone()

        total_gain = elev_row[0] if elev_row and elev_row[0] else 0.0
        total_loss = elev_row[1] if elev_row and elev_row[1] else 0.0
        split_count = elev_row[2] if elev_row else 0
        avg_gain_per_km = round(total_gain / split_count, 1) if split_count > 0 else 0.0

        # 5. Form evaluation scores (C2)
        form_scores = None
        try:
            form_row = conn.execute(
                """
                SELECT
                    gct_star_rating,
                    gct_score,
                    vo_star_rating,
                    vo_score,
                    vr_star_rating,
                    vr_score,
                    integrated_score,
                    overall_score,
                    overall_star_rating
                FROM form_evaluations
                WHERE activity_id = ?
                """,
                [activity_id],
            ).fetchone()

            if form_row:
                form_scores = {
                    "gct": {
                        "star_rating": form_row[0],
                        "score": form_row[1],
                    },
                    "vo": {
                        "star_rating": form_row[2],
                        "score": form_row[3],
                    },
                    "vr": {
                        "star_rating": form_row[4],
                        "score": form_row[5],
                    },
                    "integrated_score": form_row[6],
                    "overall_score": form_row[7],
                    "overall_star_rating": form_row[8],
                }
        except Exception:
            pass  # Table may not exist

        # 6. Phase structure (C3)
        phase_structure = None
        try:
            phase_row = conn.execute(
                """
                SELECT
                    pace_consistency,
                    hr_drift_percentage,
                    cadence_consistency,
                    fatigue_pattern,
                    warmup_avg_pace_str,
                    warmup_avg_hr,
                    warmup_splits,
                    run_avg_pace_str,
                    run_avg_hr,
                    run_splits,
                    recovery_avg_pace_str,
                    recovery_avg_hr,
                    recovery_splits,
                    cooldown_avg_pace_str,
                    cooldown_avg_hr,
                    cooldown_splits
                FROM performance_trends
                WHERE activity_id = ?
                """,
                [activity_id],
            ).fetchone()

            if phase_row:
                has_recovery = phase_row[12] is not None  # recovery_splits
                phase_structure = _build_phase_dict(phase_row, has_recovery)
        except Exception:
            pass  # Table may not exist

    return {
        "activity_id": activity_id,
        "activity_date": activity_date,
        "training_type": training_type,
        "temperature_c": round(temp_c, 1) if temp_c is not None else None,
        "humidity_pct": humidity,
        "wind_mps": wind_mps,
        "wind_direction": wind_direction,
        "terrain_category": _classify_terrain(avg_gain_per_km),
        "avg_elevation_gain_per_km": avg_gain_per_km,
        "total_elevation_gain": round(total_gain, 1),
        "total_elevation_loss": round(total_loss, 1),
        "zone_percentages": zone_percentages,
        "primary_zone": primary_zone,
        "zone_distribution_rating": zone_distribution_rating,
        "hr_stability": hr_stability,
        "aerobic_efficiency": aerobic_efficiency,
        "training_quality": training_quality,
        "zone2_focus": zone2_focus,
        "zone4_threshold_work": zone4_threshold_work,
        "form_scores": form_scores,
        "phase_structure": phase_structure,
        "planned_workout": planned_workout,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pre-fetch shared activity context for analysis agents"
    )
    parser.add_argument("activity_id", type=int, help="Garmin activity ID")
    args = parser.parse_args()

    result = prefetch_activity_context(args.activity_id)
    print(json.dumps(result, ensure_ascii=False))

    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()
