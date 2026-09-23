"""Pre-fetch the context a run report does not carry.

The run itself -- plan vs actual, signals against the athlete's own normal
range, scenes, conditions -- is computed deterministically by
``get_run_report``. What that report cannot say is why the day was prescribed,
how the athlete woke up, what the previous run of the same kind looked like and
which shoe was worn. This bundle carries exactly that, for the
``analyze-activity`` workflow (which forwards it to ``run-note-analyst``) and
for the MCP tool of the same name.

Usage:
    uv run python -m garmin_mcp.scripts.prefetch_activity_context 21884133706

Output (JSON to stdout):
    {
      "activity_id": 21884133706,
      "activity_date": "2026-02-16",
      "training_type": "aerobic_base",
      "gear": {...}|null,            # shoe worn + its cumulative mileage
      "similar_workouts": {"target_activity": {...}, "similar_activities": [...]},
      "long_run_gate": null,         # long runs only (>= 10 km); see below
      "prescription": [],            # that day's weekly_prescriptions rows
      "prescription_for_run": {...}|null,  # the row the run is judged against
      "week_position": {...}|null,   # where the day sits in the training week
      "previous_same_type": {...}|null,  # last same-type run within 21 days
      "vs_previous": {...}|null,     # deterministic deltas against it
      "morning_wellness": {...}|null     # readiness / RHR / HRV / sleep + z
    }

Every key has a reader (``buildRunNoteContext`` in
``.claude/workflows/analyze-activity.js``); a test keeps the two in step. The
numbers the five retired section analysts used to receive here -- weather,
terrain, zone percentages, form scores, phase structure, VO2max, LT -- live in
``get_run_report`` and in their own tools (``get_weather_data``,
``get_hr_efficiency_analysis``, ``get_form_evaluations``, ...) (#1287).

``long_run_gate`` carries the deterministic long-run progression verdict
(extend / repeat / shorten) for runs of at least
``_LONG_RUN_GATE_MIN_KM``; it is ``null`` for shorter runs and on any error, so
the coach review transcribes the same judgement the weekly review sees (#982).
Its ``recovery_cost`` block prices the two mornings after the run, and a fired
``cost_flag`` holds the distance even when the in-run fades are clean (#1221).

The prescription layer (Issue #984) gives the analysis the four things a coach
knows before reading the numbers: what was *prescribed* for that day, where the
day sits in the week (long-run day / days to the long run / cutback), how the
last same-type run went, and how the athlete woke up. ``vs_previous`` is
derived deterministically (``analysis.derivations``) so the agent transcribes a
judgement rather than inventing one. Every key is null-on-error (``[]`` for
``prescription``). The plan verdict itself is not here: it lives in
``get_run_report``'s ``plan`` only (#1353), which judges it on the steady HR
and the purpose outcome this bundle does not have.

Side effect: the form baseline of the activity's month (and the month before)
is trained here when it is missing (Issue #266). Nothing else in the system
does that, and ingest grades form against that baseline (#1088), so the call
stays even though its outcome is no longer part of the bundle.
"""

import argparse
import json
import logging
import sys
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from garmin_mcp.analysis.derivations import (
    compute_vs_previous,
    compute_week_position,
    select_prescription_for_run,
)
from garmin_mcp.database.connection import get_connection, get_db_path
from garmin_mcp.database.readers.metadata import collect_activity_gear

logger = logging.getLogger(__name__)

# Minimum distance for the long-run progression gate to apply. Matches the
# long-run definition used by the durability reader / get_durability_trend.
_LONG_RUN_GATE_MIN_KM = 10.0

# How far back to look for the previous run of the same training type (Issue
# #984). Three weeks keeps the comparison inside the same block / fitness level;
# older runs are a trend question, not a "how did the same session go" question.
_PREVIOUS_SAME_TYPE_LOOKBACK_DAYS = 21


def _safe[T](fn: Callable[[], T]) -> T | None:
    """Call ``fn`` and return its result, or ``None`` on any exception.

    Keeps one failing collector (missing table, empty ledger) from aborting the
    whole bundle -- every added key is null-on-error (Issue #235 convention).
    """
    try:
        return fn()
    except Exception:
        logger.debug("prefetch collector failed; leaving its key as None")
        return None


def _empty_prescription_layer() -> dict[str, Any]:
    """The prescription layer's keys with no data (shape is always present)."""
    return {
        "prescription": [],
        "prescription_for_run": None,
        "week_position": None,
        "previous_same_type": None,
        "vs_previous": None,
        "morning_wellness": None,
    }


def _fetch_previous_day_run(
    db_path_str: str, activity_date: str
) -> dict[str, Any] | None:
    """The previous calendar day's longest run, or ``None`` when there was none.

    ``week_position.is_day_after_long_run`` is read from this (#1333): whether
    yesterday was a long run is what the athlete ran yesterday, not which day
    of the week today is.

    Returns:
        ``{"distance_km", "duration_min"}`` of the longest (by time) run.
    """
    previous_day = (date.fromisoformat(activity_date) - timedelta(days=1)).isoformat()
    with get_connection(db_path_str) as conn:
        row = conn.execute(
            """
            SELECT total_distance_km, total_time_seconds
            FROM activities
            WHERE activity_date = ?
            ORDER BY total_time_seconds DESC NULLS LAST
            LIMIT 1
            """,
            [previous_day],
        ).fetchone()
    if row is None or row[1] is None:
        return None
    return {
        "distance_km": round(float(row[0]), 2) if row[0] is not None else None,
        "duration_min": round(float(row[1]) / 60.0, 1),
    }


def _fetch_previous_same_type(
    db_path_str: str,
    activity_id: int,
    activity_date: str,
    training_type: str | None,
    lookback_days: int = _PREVIOUS_SAME_TYPE_LOOKBACK_DAYS,
) -> dict[str, Any] | None:
    """Find the last run of the same training type before ``activity_date``.

    ``training_type`` lives on ``hr_efficiency``, so the join to it also filters
    out non-run activities (strength / hiking never get an hr_efficiency row) --
    a multi-activity day therefore still resolves to the run. The current
    activity and same-day runs are excluded (a comparison needs a prior day).

    Args:
        db_path_str: DuckDB path.
        activity_id: The activity being analysed (excluded from the search).
        activity_date: Its date (``YYYY-MM-DD``); only earlier days match.
        training_type: The type to match; ``None`` disables the lookup.
        lookback_days: How many days back to search.

    Returns:
        ``{"activity_id", "activity_date", "distance_km", "pace_s_per_km",
        "avg_hr", "gct_ms", "cadence_spm", "decoupling_pct"}`` (decoupling left
        ``None`` here -- it needs the time series), or ``None`` when no
        same-type run is in range.
    """
    if not training_type:
        return None

    from garmin_mcp.database.db_reader import GarminDBReader

    earliest = (
        date.fromisoformat(activity_date) - timedelta(days=lookback_days)
    ).isoformat()
    rows = GarminDBReader(db_path_str).execute_read_query(
        """
        SELECT
            a.activity_id,
            a.start_time_local::DATE AS activity_date,
            a.total_distance_km,
            a.avg_pace_seconds_per_km,
            a.avg_heart_rate,
            f.gct_ms_actual,
            f.cadence_actual
        FROM activities a
        JOIN hr_efficiency h ON h.activity_id = a.activity_id
        LEFT JOIN form_evaluations f ON f.activity_id = a.activity_id
        WHERE h.training_type = ?
          AND a.activity_id <> ?
          AND a.start_time_local::DATE < CAST(? AS DATE)
          AND a.start_time_local::DATE >= CAST(? AS DATE)
        ORDER BY a.start_time_local DESC
        LIMIT 1
        """,
        (training_type, activity_id, activity_date, earliest),
    )
    if not rows:
        return None

    row = rows[0]
    return {
        "activity_id": int(row[0]),
        "activity_date": str(row[1]),
        "distance_km": row[2],
        "pace_s_per_km": row[3],
        "avg_hr": row[4],
        "gct_ms": row[5],
        "cadence_spm": row[6],
        "decoupling_pct": None,
    }


def _fetch_decoupling_pct(db_path_str: str, activity_id: int) -> float | None:
    """Cardiac decoupling (%) for one activity, or ``None`` when uncomputable."""
    from garmin_mcp.database.readers.durability import DurabilityReader

    durability = DurabilityReader(db_path_str).get_activity_durability(activity_id)
    return (durability or {}).get("decoupling_pct")


def _fetch_morning_wellness(db_path_str: str, activity_date: str) -> dict | None:
    """Collect the day's wellness numbers with their personal-baseline z-scores.

    The raw row is read first: without a ``daily_wellness`` row for the exact
    day there is no morning to report (the baseline reader would otherwise label
    an earlier day's values as "today").

    Args:
        db_path_str: DuckDB path.
        activity_date: The activity's date (``YYYY-MM-DD``).

    Returns:
        ``{"date", "readiness", "resting_hr", "hrv_ms", "sleep_score",
        "readiness_z", "rhr_z", "hrv_z", "adverse"}``, or ``None`` when the day
        has no wellness row.
    """
    from garmin_mcp.database.db_reader import GarminDBReader

    reader = GarminDBReader(db_path_str)
    rows = reader.execute_read_query(
        """
        SELECT training_readiness, resting_hr, hrv_overnight_ms, sleep_score
        FROM daily_wellness
        WHERE date = CAST(? AS DATE)
        """,
        (activity_date,),
    )
    if not rows:
        return None

    readiness, resting_hr, hrv_ms, sleep_score = rows[0]
    deviation: dict[str, Any] = (
        _safe(lambda: reader.get_wellness_baseline_deviation(activity_date)) or {}
    )

    def _z(metric: str) -> float | None:
        block = deviation.get(metric)
        return block.get("z") if isinstance(block, dict) else None

    return {
        "date": activity_date,
        "readiness": readiness,
        "resting_hr": resting_hr,
        "hrv_ms": hrv_ms,
        "sleep_score": sleep_score,
        "readiness_z": _z("readiness"),
        "rhr_z": _z("rhr"),
        "hrv_z": _z("hrv"),
        "adverse": bool(deviation.get("overall_flag")),
    }


def _collect_prescription_layer(
    db_path_str: str,
    activity_id: int,
    activity_date: str,
    training_type: str | None,
    current_metrics: dict[str, Any],
    user_id: str = "default",
) -> dict[str, Any]:
    """Build the "prescription vs actual" layer of the bundle (Issue #984).

    Reads the day's prescription, the week's block / ladder step, the previous
    same-type run and the morning's wellness, then derives the delta chips
    deterministically. Each collector is individually ``_safe``, so
    a DB without the plan tables degrades to the empty layer instead of failing
    the whole prefetch.

    Args:
        db_path_str: DuckDB path.
        activity_id: The activity being analysed.
        activity_date: Its date (``YYYY-MM-DD``).
        training_type: Its training type (used for the same-type lookup).
        current_metrics: The run's comparison metrics for
            :func:`compute_vs_previous`.
        user_id: Ledger owner identifier.

    Returns:
        The six layer keys (see :func:`_empty_prescription_layer`).
    """
    from garmin_mcp.database.readers.plan import PlanReader

    layer = _empty_prescription_layer()

    plan_reader = _safe(lambda: PlanReader(db_path_str))
    if plan_reader is not None:
        rows = (
            _safe(
                lambda: plan_reader.get_prescriptions_for_date(
                    activity_date, user_id=user_id
                )
            )
            or []
        )
        layer["prescription"] = rows
        # The row a run answers: the first with a running intensity class, so a
        # 補強 row filed earlier the same day is not what the run is judged
        # against (Issue #1086).
        run_row = select_prescription_for_run(rows)
        layer["prescription_for_run"] = run_row

        week_start = _safe(
            lambda: plan_reader.resolve_week_start(activity_date, user_id=user_id)
        )
        if week_start is not None:
            block = _safe(
                lambda: plan_reader.get_block_for_date(week_start, user_id=user_id)
            )
            ladder_step = _safe(
                lambda: plan_reader.get_ladder_step_for_week(
                    week_start, user_id=user_id
                )
            )
            # The configured week start day is implied by the resolved week
            # start, so no second profile read is needed.
            week_start_day = date.fromisoformat(week_start).weekday()
            previous_day_run = _safe(
                lambda: _fetch_previous_day_run(db_path_str, activity_date)
            )
            layer["week_position"] = _safe(
                lambda: compute_week_position(
                    activity_date,
                    week_start_day,
                    ladder_step,
                    block,
                    previous_day_run,
                )
            )

    previous = _safe(
        lambda: _fetch_previous_same_type(
            db_path_str, activity_id, activity_date, training_type
        )
    )
    if previous is not None and current_metrics.get("decoupling_pct") is not None:
        # Only compare decoupling when the current run has it (long runs), so
        # the chip is never a lone number without its counterpart.
        previous["decoupling_pct"] = _safe(
            lambda: _fetch_decoupling_pct(db_path_str, previous["activity_id"])
        )
    layer["previous_same_type"] = previous
    layer["vs_previous"] = _safe(lambda: compute_vs_previous(current_metrics, previous))

    layer["morning_wellness"] = _safe(
        lambda: _fetch_morning_wellness(db_path_str, activity_date)
    )
    return layer


def prefetch_activity_context(activity_id: int) -> dict:
    """Context the run report does not carry.

    Why the day was prescribed, where it sits in the week, how the athlete woke
    up, what the previous same-type run looked like, similar past workouts, the
    long-run gate and the shoe. The run itself is ``get_run_report``'s.

    Args:
        activity_id: Garmin activity ID.

    Returns:
        The bundle described in the module docstring, or ``{"error": ...}`` when
        the activity does not exist.
    """
    db_path = get_db_path()

    with get_connection(db_path) as conn:
        activity_row = conn.execute(
            """
            SELECT
                start_time_local::DATE AS activity_date,
                avg_heart_rate,
                avg_pace_seconds_per_km,
                total_distance_km
            FROM activities
            WHERE activity_id = ?
            """,
            [activity_id],
        ).fetchone()

        if not activity_row:
            return {"error": f"Activity {activity_id} not found"}

        activity_date = str(activity_row[0])
        avg_heart_rate = activity_row[1]
        avg_pace_s_per_km = activity_row[2]
        total_distance_km = activity_row[3]

        # Which shoe, and how far into its life this run sits (Issue #1207).
        gear = collect_activity_gear(conn, activity_id)

        hr_row = conn.execute(
            "SELECT training_type FROM hr_efficiency WHERE activity_id = ?",
            [activity_id],
        ).fetchone()
        training_type = hr_row[0] if hr_row else None

    from garmin_mcp.database.readers.form import FormReader

    db_path_str = str(db_path)

    # Not emitted: only its GCT / cadence feed the vs_previous deltas below.
    form_evaluation = FormReader(db_path_str).get_form_evaluations(activity_id)

    # Self-healing (Issue #266): train the form baseline of the activity's
    # month (+ prior month) when it is missing. This is the only caller, and
    # ingest grades form against that baseline (#1088), so it runs here even
    # though nothing in the bundle reports it. Best-effort: never blocks.
    from garmin_mcp.form_baseline.trainer import ensure_form_baselines_for_date

    try:
        autogen = ensure_form_baselines_for_date(activity_date, db_path_str)
        if autogen.get("generated"):
            logger.info("form baselines generated: %s", autogen["generated"])
    except Exception:
        logger.debug("form baseline self-heal failed; continuing without it")

    # Long-run progression gate (Issue #982): may the next long run be
    # extended? Only meaningful for long runs, so shorter runs keep the key at
    # null rather than shipping a verdict with no basis. Null on error. The
    # unified reader (not DurabilityReader) because the gate also prices the
    # next two mornings via get_long_run_recovery_cost (#1221).
    long_run_gate: dict | None = None
    if (
        total_distance_km is not None
        and float(total_distance_km) >= _LONG_RUN_GATE_MIN_KM
    ):
        try:
            from garmin_mcp.analysis.progression_gate import (
                build_long_run_progression_gate,
            )
            from garmin_mcp.database.db_reader import GarminDBReader

            long_run_gate = build_long_run_progression_gate(
                GarminDBReader(db_path_str), activity_id
            )
        except Exception:
            logger.debug("long-run progression gate failed; leaving it as None")

    # Similar past workouts (own connection via WorkoutComparator). Called once,
    # outside the read transaction above. Key is always present (null on error).
    similar_workouts: dict | None
    try:
        from garmin_mcp.rag.queries.comparisons import WorkoutComparator

        comparator = WorkoutComparator(db_path_str)
        similar_workouts = comparator.find_similar_workouts(activity_id, limit=3)
    except Exception:
        similar_workouts = None

    # Prescription vs actual layer (Issue #984): what was prescribed for the
    # day, where the day sits in the week, how the same session went last time,
    # and how the athlete woke up -- plus the deterministic deltas.
    prescription_layer = _collect_prescription_layer(
        db_path_str,
        activity_id,
        activity_date,
        training_type,
        {
            "activity_id": activity_id,
            "activity_date": activity_date,
            "pace_s_per_km": avg_pace_s_per_km,
            "avg_hr": avg_heart_rate,
            "gct_ms": ((form_evaluation or {}).get("gct") or {}).get("actual"),
            "cadence_spm": ((form_evaluation or {}).get("cadence") or {}).get("actual"),
            "decoupling_pct": ((long_run_gate or {}).get("current") or {}).get(
                "decoupling_pct"
            ),
        },
    )

    return {
        "activity_id": activity_id,
        "activity_date": activity_date,
        "training_type": training_type,
        # Shoe worn on this run plus its cumulative mileage (Issue #1207); null
        # when no gear was registered in Garmin for the activity.
        "gear": gear,
        "similar_workouts": similar_workouts,
        # Deterministic long-run progression verdict (Issue #982); null for
        # runs below _LONG_RUN_GATE_MIN_KM.
        "long_run_gate": long_run_gate,
        # --- Prescription vs actual layer (Issue #984) ---
        **prescription_layer,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pre-fetch the context a run report does not carry"
    )
    parser.add_argument("activity_id", type=int, help="Garmin activity ID")
    args = parser.parse_args()

    result = prefetch_activity_context(args.activity_id)
    print(json.dumps(result, ensure_ascii=False))

    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()
