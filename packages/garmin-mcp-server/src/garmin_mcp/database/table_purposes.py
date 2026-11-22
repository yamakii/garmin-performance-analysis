"""One line per DuckDB domain table: what it answers and its grain.

``get_db_catalog`` serves these lines so a session can find the table behind a
question without reading the 80 KB schema doc. A test pins the keys to the live
schema (``tests/database/test_table_purposes.py``), so a new table cannot ship
without a line here. Column-level detail stays in
``docs/spec/duckdb_schema_mapping.md``.
"""

from __future__ import annotations

TABLE_PURPOSES: dict[str, str] = {
    "activities": (
        "One row per run: date, start time, distance, time, average pace/HR, "
        "weather snapshot, shoes (gear_*), sensors (dynamics_source / hr_source). "
        "The hub every per-activity table joins on activity_id."
    ),
    "activity_context": (
        "Facts the athlete stated about a run (commute, carried load, walk "
        "reasons, apparel, sensor mounting). Per activity, append-only."
    ),
    "analysis_runs": "Bookkeeping: one row per analysis run (run_id, started_at).",
    "athlete_goals": (
        "Race goals: race name/date, priority (A/B/C), distance, target time, "
        "status, notes with the goal's own success criteria."
    ),
    "athlete_profile": (
        "The athlete's current focus and focus_notes (standing rules and "
        "hypotheses as of writing; numbers in it may be stale)."
    ),
    "athlete_profile_versions": "Every saved version of athlete_profile (JSON).",
    "athlete_symptoms": (
        "Symptom log: date, body region, side, severity, phase, optional "
        "activity. One row per report."
    ),
    "body_composition": "Weight / body fat / muscle mass per measurement date.",
    "coaching_rules": (
        "Athlete-specific coaching rules (scope, rule_text, rationale, active)."
    ),
    "daily_energy": (
        "Per day: intake (consumed_kcal) and expenditure (total/active/BMR kcal), "
        "steps, coverage of the day."
    ),
    "daily_wellness": (
        "Per day morning recovery: resting HR, overnight HRV and its baseline, "
        "sleep duration/score, training readiness, body battery, stress."
    ),
    "form_baseline_history": (
        "Trained form-baseline models (GCT/VO/VR/power vs speed) per period; "
        "what form_evaluations' expected values come from."
    ),
    "form_efficiency": (
        "Per run: GCT / vertical oscillation / vertical ratio summary stats."
    ),
    "form_evaluations": (
        "Per run: expected vs actual GCT/VO/VR/power efficiency against the "
        "athlete's own speed-adjusted baseline."
    ),
    "heart_rate_zones": (
        "Per run and zone (Garmin native zones): boundaries, seconds and % in zone."
    ),
    "hiking_sessions": "One row per hike: duration, distance, elevation, HR.",
    "hr_efficiency": (
        "Per run: zone distribution, primary zone, training_type classification."
    ),
    "intake_confirmations": "Days the athlete confirmed the food log complete.",
    "lactate_threshold": (
        "Garmin's lactate-threshold estimate (HR, speed, FTP) as fetched with "
        "each activity; date_hr says when Garmin last updated it."
    ),
    "performance_trends": (
        "Per run phase summary (warmup/run/recovery/cooldown pace, HR, cadence), "
        "pace consistency and HR drift."
    ),
    "season_retrospectives": (
        "Season narratives and key learnings per period (prose, written then)."
    ),
    "section_analyses": (
        "Stored LLM analyses per run (section_type, e.g. run_note; JSON)."
    ),
    "splits": (
        "Per lap (auto 1 km or workout/manual): pace, HR, cadence, power, GCT, "
        "VO, stride, elevation, intensity_type / role_phase."
    ),
    "strength_sessions": "One row per strength session: duration, sets, HR.",
    "sync_runs": "Bookkeeping: scheduled sync runs and their results.",
    "time_series_metrics": (
        "Per second-ish sample within a run: HR, speed, cadence, power, GCT, "
        "VO, elevation. Large; filter by activity_id."
    ),
    "training_block_versions": "Every saved version of the training block plan.",
    "training_blocks": (
        "The mesocycle plan: blocks with phase, dates, purpose, long-run ladder "
        "(JSON), quality sessions per week, cutback rule."
    ),
    "trend_analyses": "Stored LLM trend narrations per period (JSON).",
    "vo2_max": "Garmin VO2max as fetched with each activity (value, date).",
    "weekly_prescriptions": (
        "Per prescribed session: date, session_type, target km/minutes, HR "
        "band/ceiling, pace band, status, the activity that fulfilled it."
    ),
    "weekly_reviews": "Stored weekly reviews per week (review_data JSON).",
}
