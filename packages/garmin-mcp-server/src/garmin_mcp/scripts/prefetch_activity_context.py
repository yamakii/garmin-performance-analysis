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
      "planned_workout": {
        "workout_type": "easy_run",
        "description_ja": "イージーラン 6km",
        "target_hr_low": 121,
        "target_hr_high": 148,
        "target_pace_low": null,
        "target_pace_high": null,
        "target_distance_km": 6.0,
        "target_duration_minutes": null,
        "plan_id": "5k_improvement_2026"
      }
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


def prefetch_activity_context(activity_id: int) -> dict:
    """Fetch shared context for all analysis agents in a single DB read.

    Args:
        activity_id: Garmin activity ID.

    Returns:
        Dict with training_type, weather, terrain, and planned_workout data.
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

        # 2. Training type (from hr_efficiency table)
        hr_row = conn.execute(
            """
            SELECT training_type
            FROM hr_efficiency
            WHERE activity_id = ?
            """,
            [activity_id],
        ).fetchone()

        training_type = hr_row[0] if hr_row else None

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
