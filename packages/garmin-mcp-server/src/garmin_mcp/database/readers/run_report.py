"""The deterministic single-run report, assembled on read (#1250).

One activity, one payload: the plan verdict, the athlete's own normal range per
metric, the turning points of the run and the conditions it was run in. The
single-run page, the run-note agent, ``/run-debrief`` and ``/daily-checkin``
all read *this* dict, so they cannot disagree about what happened -- and every
past run gets the new page without being re-analysed by an LLM.

Nothing is computed here that some other module already knows how to compute.
This reader only loads rows and hands them on:

=========================  =================================================
what                       who decides it
=========================  =================================================
normal range per metric    ``analysis.run_signals`` / ``analysis.normal_range``
turning points, recurrence ``analysis.run_moments``
steps, flow series, axis   ``analysis.run_moments`` (``build_flow``)
plan verdict               ``analysis.derivations.compute_prescription_verdict``
steady seconds, ceiling    ``analysis.hr_windows``
time, judged share
run purpose                ``analysis.run_purpose`` (``resolve_purpose``)
scene verdict per purpose  ``analysis.run_policy`` (``apply_policy``)
delta chips, next target   ``analysis.derivations`` (``compute_vs_previous`` …)
intensity family           ``database.inserters.hr_efficiency``
expected HR                ``rag.queries.heat_adjustment.HeatAdjustmentModel``
which splits count          ``form_baseline.split_filter``
how far outside the        ``form_baseline.scorer.extrapolation_factor``
form model's speed range
=========================  =================================================

Loading rules that are easy to break when editing:

* **One query per table.** The 90-day history is read with a single query per
  table and merged in Python by ``activity_id``; a per-run loop over the
  readers would turn one page view into hundreds of queries.
* **Every table is optional.** A DuckDB without ``weekly_prescriptions`` (or
  ``form_evaluations``, or ``hr_efficiency``) must still return a report --
  the affected block degrades to ``None`` / ``insufficient`` instead of
  raising, because the Web fixture DBs and older databases are real callers.
* **Plain JSON types only.** Dates are ``str``, numbers are built-in
  ``float`` / ``int``, so ``json.dumps(report)`` needs no ``default=``.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from typing import Any

from garmin_mcp.analysis.derivations import (
    REST_INTENSITY_CLASS,
    compute_next_run_target,
    compute_prescription_verdict,
    compute_vs_previous,
    detect_progression_session,
    intensity_class,
    select_prescription_for_run,
)
from garmin_mcp.analysis.hr_windows import (
    event_mask,
    judged_share,
    masked_mean_hr,
    masked_split_hr,
    seconds_over,
    steady_mask,
)
from garmin_mcp.analysis.normal_range import EXTRAPOLATION_NOT_JUDGED
from garmin_mcp.analysis.run_moments import (
    RECURRENCE_LOOKBACK,
    build_flow,
    detect_moments,
    detect_recurrence,
)
from garmin_mcp.analysis.run_policy import apply_policy
from garmin_mcp.analysis.run_purpose import resolve_purpose
from garmin_mcp.database.inserters.hr_efficiency import resolve_intensity_category
from garmin_mcp.database.readers.base import BaseDBReader
from garmin_mcp.form_baseline.scorer import extrapolation_factor
from garmin_mcp.form_baseline.split_filter import (
    MIN_SPLIT_KM,
    running_split_params,
    running_split_sql,
)

logger = logging.getLogger(__name__)

# Trailing window loaded for the baselines. ``normal_range.WINDOW_DAYS`` (60)
# trims the signal baselines further inside ``build_signals``; the wider window
# is what the heat-adjustment model is fitted on, and what the same-family
# recurrence lookback picks its previous runs from.
HISTORY_DAYS = 90

# Verdict symbol -> the label the page puts in the headline.
_VERDICT_LABELS: dict[str, str] = {
    "✅": "処方どおり",
    "🟡": "一部ずれ",
    "🔴": "ずれあり",
}

# Headline label when the day carried no prescription at all.
NO_PLAN_LABEL = "処方なし"

# What an *adverse* signal is called in the headline. Only the unfavourable
# side gets a flag: a run whose ground contact is unusually short is not a
# thing to warn about, so favourable outliers never appear here.
_ADVERSE_FLAG_LABELS: dict[str, str] = {
    "gct": "接地時間が長め",
    "vo": "上下動が大きめ",
    "vr": "上下動比が高め",
    "cadence": "ケイデンスが低め",
    "power": "パワー効率が低め",
    "hr_vs_expected": "心拍が想定より高め",
    "hr_drift": "心拍ドリフトが大きめ",
}

# The phases ``performance_trends`` carries, in the order a run executes them.
_PHASES: tuple[str, ...] = ("warmup", "run", "recovery", "cooldown")

# One vocabulary for the plan card's intensity axis (#1268). Raw labels that
# name a distinction the intensity family drops (a recovery run is "easy" too)
# are matched first; everything else goes through the family.
_RAW_INTENSITY_LABELS: dict[str, str] = {
    "recovery": "リカバリー",
    "recovery_run": "リカバリー",
    "rest": "休養",
    "rest_day": "休養",
    "off": "休養",
    "moderate": "ミドル",
    "unknown": "-",
}
_FAMILY_INTENSITY_LABELS: dict[str, str] = {
    "easy": "イージー",
    "moderate": "ミドル",
    "tempo": "テンポ",
    "threshold": "閾値",
    "vo2max": "インターバル",
}

# Plan words the activity vocabulary cannot resolve: a prescription names the
# *session*, ``resolve_intensity_category`` only knows Garmin training types.
# Mapped to the same family labels so both sides of the intensity row speak one
# language (#1273).
_PLAN_INTENSITY_LABELS: dict[str, str] = {
    "easy": "イージー",
    "easy_run": "イージー",
    "jog": "イージー",
    "base": "イージー",
    "endurance": "イージー",
    "long": "イージー",
    "long_run": "イージー",
    "progression": "テンポ",
    "tempo_run": "テンポ",
    "marathon_pace": "テンポ",
    "lactate_threshold": "閾値",
    "threshold_work": "閾値",
    "interval": "インターバル",
    "intervals": "インターバル",
    "repetition": "インターバル",
    "speed": "インターバル",
    "race": "レース",
}

# What a session type says *beyond* its intensity family. The row compares
# intensity, so the extra word is appended to the target only -- a long run is
# prescribed as easy running and answered by an easy run (#1273).
_SESSION_TYPE_SUFFIX_JA: dict[str, str] = {
    "long": "ロング走",
    "long_run": "ロング走",
    "progression": "ビルドアップ",
}

# The form metrics the run report judges. ``power`` is deliberately absent: its
# model carries no speed range, so no speed can extrapolate it.
_FORM_METRICS: tuple[str, ...] = ("gct", "vo", "vr", "cadence")

# The baseline family the form models are trained and read per (#1088).
_BASELINE_USER_ID = "default"
_BASELINE_CONDITION_GROUP = "flat_road"

# Whose ``athlete_goals`` decide whether the run was on a goal race day.
_GOAL_USER_ID = "default"

# How far ahead a scheduled session is still "what is next" (#1273). Two weeks
# covers the current week plus the next one the plan has been written for.
_NEXT_SESSION_HORIZON_DAYS = 14

# Terrain bands in metres of gain per km, matching the table the analysis
# contract states to the agents (flat <10 / undulating 10-30 / hilly 30-50 /
# mountainous >50). A single big up-and-down promotes an otherwise "flat"
# average to "undulating" so local bumps are not averaged away (#473).
_TERRAIN_BANDS: tuple[tuple[float, str], ...] = (
    (10.0, "flat"),
    (30.0, "undulating"),
    (50.0, "hilly"),
)
_SPLIT_UNDULATION_M = 15.0


class RunReportReader(BaseDBReader):
    """Assembles :meth:`get_run_report` out of DuckDB rows and the pure modules."""

    def get_run_report(self, activity_id: int) -> dict[str, Any] | None:
        """Build the deterministic run report for one activity.

        Args:
            activity_id: The run to report on.

        Returns:
            ``None`` when the activity does not exist. Otherwise a dict with
            ``activity_id``, ``activity_date``, ``intensity_category``,
            ``purpose`` (``{"id", "label_ja", "source"}``, #1314),
            ``headline``, ``plan``, ``judged_share`` (``{"hr", "form"}``: the
            share of the run's time the HR ceiling / the form signals were
            judged on, ``None`` without a time series), ``signals``, ``zones``,
            ``moments`` (each with ``policy = {"verdict", "reason"}`` judged
            against the purpose),
            ``flow``, ``recurrence``, ``phases``, ``conditions``,
            ``vs_previous``, ``next_run_target`` and ``next_session`` (see the
            module docstring for who computes what). Every value is
            JSON-serialisable without a custom encoder.
        """
        with self._get_connection() as conn:
            tables = _existing_tables(conn)
            if "activities" not in tables:
                return None

            today_core = _fetch_activity(conn, activity_id)
            if today_core is None:
                return None

            activity_date = str(today_core["activity_date"])
            window_start = _shift_days(activity_date, -HISTORY_DAYS)

            runs = _fetch_window(conn, tables, window_start, activity_date)
            _mark_extrapolated(conn, tables, runs, window_start, activity_date)
            today = runs.get(activity_id) or today_core
            history = _history_before(runs, activity_id, activity_date)

            zone_rows = (
                _fetch_zone_rows(conn, activity_id)
                if "heart_rate_zones" in tables
                else []
            )
            elevation = (
                _fetch_elevation(conn, activity_id) if "splits" in tables else {}
            )

            family_previous = [
                run
                for run in history
                if run.get("intensity_category") == today.get("intensity_category")
            ][-RECURRENCE_LOOKBACK:]
            split_ids = [
                activity_id,
                *(int(run["activity_id"]) for run in family_previous),
            ]
            splits_by_id = _fetch_splits(conn, split_ids) if "splits" in tables else {}
            today_splits = splits_by_id.get(activity_id, [])
            has_series = "time_series_metrics" in tables
            hr_samples = _fetch_hr_samples(conn, activity_id) if has_series else []
            # The recurrence look-back reads each run through its own steady
            # mask, so today and the runs it is compared with are judged alike.
            previous_samples = {
                int(run["activity_id"]): (
                    _fetch_hr_samples(conn, int(run["activity_id"]))
                    if has_series
                    else []
                )
                for run in family_previous
            }
            identity = _fetch_run_identity(conn, tables, activity_id, activity_date)

        prescription = self._load_prescription(activity_date)
        hr_ceiling_bpm = _as_int(prescription.get("hr_high")) if prescription else None

        # Which seconds are steady running (#1313): the ceiling is judged on
        # them, and the form signals are not judged when too few are left.
        steady = steady_mask(hr_samples, today_splits) if hr_samples else []
        shares = {
            "hr": judged_share(hr_samples, steady) if hr_samples else None,
            "form": (
                judged_share(hr_samples, event_mask(hr_samples, today_splits))
                if hr_samples
                else None
            ),
        }
        today = {**today, "form_judged_share": shares["form"]}

        jog_avg_hr = _ceiling_avg_hr(today_splits, hr_samples, steady)
        verdict = compute_prescription_verdict(
            prescription, _actual(today), jog_avg_hr=jog_avg_hr
        )
        signals = self._signals(today, history)
        # Scenes read each kilometre's HR over its steady seconds only (#1320):
        # a stride and its recovery inside a kilometre are not a ceiling touch.
        moments = detect_moments(
            _steady_splits(today_splits, hr_samples, steady),
            hr_ceiling=hr_ceiling_bpm,
            prescription=prescription,
        )
        purpose = resolve_purpose(
            prescription, _purpose_facts(today, today_splits, moments, identity)
        )
        # The verdicts are added on top of detection; recurrence (below) still
        # reads the purpose-blind scenes, so a habit is found whatever it means.
        judged_moments = apply_policy(moments, purpose.id, _allowances(prescription))
        recurrence = detect_recurrence(
            moments,
            [
                {
                    "activity_date": str(run["activity_date"]),
                    # Previous runs are judged against *today's* ceiling: the
                    # family's prescribed ceiling is stable, and loading each
                    # run's own prescription would reintroduce a per-run loop.
                    "moments": detect_moments(
                        _steady_splits(
                            splits_by_id.get(int(run["activity_id"]), []),
                            previous_samples.get(int(run["activity_id"]), []),
                        ),
                        hr_ceiling=hr_ceiling_bpm,
                    ),
                }
                for run in reversed(family_previous)
            ],
        )

        next_run_target = self._next_run_target(
            activity_id, today, zone_rows, prescription
        )

        return {
            "activity_id": int(activity_id),
            "activity_date": activity_date,
            "intensity_category": str(today.get("intensity_category") or "unknown"),
            "purpose": {
                "id": purpose.id,
                "label_ja": purpose.label_ja,
                "source": purpose.source,
            },
            "headline": _headline(verdict, signals, judged_moments),
            "plan": _plan_block(
                prescription,
                verdict,
                today,
                zone_rows,
                splits=today_splits,
                hr_samples=hr_samples,
                steady=steady,
                ceiling_avg_hr=jog_avg_hr,
            ),
            "judged_share": shares,
            "signals": signals,
            "zones": _zones(zone_rows),
            "moments": judged_moments,
            "flow": build_flow(today_splits),
            "recurrence": recurrence,
            "phases": _phases(today),
            "conditions": _conditions(today, elevation),
            "vs_previous": _vs_previous(today, history),
            "next_run_target": next_run_target,
            "next_session": self._next_session(activity_date, next_run_target),
        }

    # ------------------------------------------------------------------ #
    # Collaborating readers / models
    # ------------------------------------------------------------------ #

    def _load_prescription(self, activity_date: str) -> dict[str, Any] | None:
        """The prescription row this run answers, or ``None`` when unprescribed.

        Delegated to ``PlanReader`` so the "latest batch of the containing
        week" semantics stay in one place, and to
        ``select_prescription_for_run`` so a 補強 row filed the same day is not
        what the run is judged against. A database without the plan tables
        degrades to ``None``.

        The import is function-local because this module is imported *while*
        the ``readers`` package is still initialising.
        """
        from garmin_mcp.database.readers.plan import PlanReader

        try:
            rows = PlanReader(str(self.db_path)).get_prescriptions_for_date(
                activity_date
            )
        except Exception as exc:  # pragma: no cover - degraded DB only
            logger.debug("no prescription available for %s: %s", activity_date, exc)
            return None
        return select_prescription_for_run(rows)

    def _signals(
        self, today: dict[str, Any], history: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Judge today's metrics against the athlete's own normal range.

        The import is function-local for the same reason as in
        :meth:`_fit_hr_model`: ``analysis.run_signals`` pulls in the
        heat-adjustment model, which imports ``GarminDBReader``, which imports
        this package.
        """
        from garmin_mcp.analysis.run_signals import build_signals

        return build_signals(
            today, history, hr_model=self._fit_hr_model(today, history)
        )

    def _fit_hr_model(
        self, today: dict[str, Any], history: list[dict[str, Any]]
    ) -> Any:
        """Fit the heat-adjustment model on the trailing same-family runs.

        The residual ``avg_hr - expected_hr`` is only comparable inside one
        intensity family, so the fit uses the same-family prior runs of the
        loaded window and never today itself (a model that has seen today
        cannot be surprised by it). ``None`` below ``MIN_FIT_ACTIVITIES``
        complete rows, which leaves the ``hr_vs_expected`` signal unjudged.

        The import is function-local on purpose: ``rag.queries.heat_adjustment``
        imports ``GarminDBReader``, which imports this package.
        """
        from garmin_mcp.rag.queries.heat_adjustment import HeatAdjustmentModel

        family = today.get("intensity_category")
        ids = [
            int(run["activity_id"])
            for run in history
            if run.get("intensity_category") == family
        ]
        if not ids:
            return None
        try:
            return HeatAdjustmentModel(str(self.db_path)).fit(ids)
        except Exception as exc:
            logger.debug("no heat-adjustment model for activity family: %s", exc)
            return None

    def _next_run_target(
        self,
        activity_id: int,
        today: dict[str, Any],
        zone_rows: list[tuple[Any, ...]],
        prescription: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """The deterministic numeric core of the next run's target, or ``None``.

        Reuses ``compute_next_run_target`` with the physiology the target's
        family needs (vVO2max for intervals, LT speed for tempo, the Garmin
        native zones for easy runs).
        """
        from garmin_mcp.database.readers.physiology import PhysiologyReader

        try:
            physiology = PhysiologyReader(str(self.db_path))
            vo2_max = physiology.get_vo2_max_data(activity_id)
            lactate_threshold = physiology.get_lactate_threshold_data(activity_id)
        except Exception as exc:  # pragma: no cover - degraded DB only
            logger.debug("no physiology for next_run_target: %s", exc)
            vo2_max = lactate_threshold = None

        try:
            return compute_next_run_target(
                today.get("training_type"),
                None,
                vo2_max,
                lactate_threshold,
                _as_int(today.get("avg_hr")),
                _as_float(today.get("avg_pace_seconds_per_km")),
                _zones_detail(zone_rows),
                prescription,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("next_run_target unavailable: %s", exc)
            return None

    def _next_session(
        self, activity_date: str, next_run_target: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """What the athlete actually does next, or ``None`` when unknown.

        ``next_run_target`` answers "what should the *next run of this kind*
        look like", which is not the same question: on 2026-09-18 it described
        the next easy run while the next scheduled session was a 16 km long run
        two days later (#1267). The answer is looked up in order of how much is
        known about the session:

        1. the next prescribed **run** after the activity date (strength rows
           and rows already marked ``skipped`` cannot be the next run),
        2. the block's next long-run ladder step, whose day is the week's last
           one by the same convention ``compute_week_position`` uses,
        3. failing both, today's family projected forward -- a dateless target
           that at least carries the right HR band.

        The import is function-local because this module is imported *while*
        the ``readers`` package is still initialising.
        """
        from garmin_mcp.database.readers.plan import PlanReader

        try:
            plan = PlanReader(str(self.db_path))
        except Exception as exc:  # pragma: no cover - degraded DB only
            logger.debug("no plan reader for next_session: %s", exc)
            return _projected_session(next_run_target)

        scheduled = _scheduled_session(plan, activity_date)
        if scheduled is not None:
            return scheduled
        ladder = _ladder_session(plan, activity_date)
        if ladder is not None:
            return ladder
        return _projected_session(next_run_target)


# --------------------------------------------------------------------------- #
# Row loading (one query per table)
# --------------------------------------------------------------------------- #


def _existing_tables(conn: Any) -> set[str]:
    """Names of the tables present in the attached database."""
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'main'"
    ).fetchall()
    return {str(row[0]) for row in rows}


def _fetch_activity(conn: Any, activity_id: int) -> dict[str, Any] | None:
    """The run's own ``activities`` row, or ``None`` when it does not exist."""
    row = conn.execute(
        """
        SELECT activity_id, CAST(activity_date AS VARCHAR), total_distance_km,
               total_time_seconds, avg_pace_seconds_per_km, avg_heart_rate,
               temp_celsius, relative_humidity_percent, wind_speed_kmh
        FROM activities WHERE activity_id = ?
        """,
        [activity_id],
    ).fetchone()
    return None if row is None else _activity_row(row)


def _fetch_run_identity(
    conn: Any, tables: set[str], activity_id: int, activity_date: str
) -> dict[str, Any]:
    """The two facts the purpose inference needs beyond the window rows.

    ``activity_name`` (a race is often only named as one) and whether the day
    is a goal race day in ``athlete_goals``. Either degrades to "unknown" on a
    database without the column / table.
    """
    identity: dict[str, Any] = {"activity_name": None, "is_goal_race_day": False}
    if _has_column(conn, "activities", "activity_name"):
        row = conn.execute(
            "SELECT activity_name FROM activities WHERE activity_id = ?",
            [activity_id],
        ).fetchone()
        identity["activity_name"] = None if row is None else row[0]
    if "athlete_goals" in tables:
        row = conn.execute(
            "SELECT COUNT(*) FROM athlete_goals "
            "WHERE user_id = ? AND race_date = CAST(? AS DATE)",
            [_GOAL_USER_ID, activity_date],
        ).fetchone()
        identity["is_goal_race_day"] = bool(row and row[0])
    return identity


def _fetch_window(
    conn: Any, tables: set[str], window_start: str, activity_date: str
) -> dict[int, dict[str, Any]]:
    """Every run of the trailing window, merged from one query per table.

    Returns ``{activity_id: row}`` where each row carries what
    :func:`~garmin_mcp.analysis.run_signals.build_signals` reads (the form
    deltas, the power score, HR drift, pace / temperature / HR, the valid-split
    count and the intensity family) plus the phase columns used for today.
    """
    runs: dict[int, dict[str, Any]] = {}
    for row in conn.execute(
        """
        SELECT activity_id, CAST(activity_date AS VARCHAR), total_distance_km,
               total_time_seconds, avg_pace_seconds_per_km, avg_heart_rate,
               temp_celsius, relative_humidity_percent, wind_speed_kmh
        FROM activities
        WHERE activity_date BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
        ORDER BY activity_date, activity_id
        """,
        [window_start, activity_date],
    ).fetchall():
        run = _activity_row(row)
        runs[int(run["activity_id"])] = run

    if not runs:
        return runs

    in_window = (
        "activity_id IN (SELECT activity_id FROM activities "
        "WHERE activity_date BETWEEN CAST(? AS DATE) AND CAST(? AS DATE))"
    )
    window_params = [window_start, activity_date]

    if "form_evaluations" in tables:
        for row in conn.execute(
            f"""
            SELECT activity_id, gct_ms_expected, gct_ms_actual, gct_delta_pct,
                   vo_cm_expected, vo_cm_actual, vo_delta_cm,
                   vr_pct_expected, vr_pct_actual, vr_delta_pct,
                   cadence_expected, cadence_actual, cadence_delta_pct,
                   power_efficiency_score
            FROM form_evaluations WHERE {in_window}
            """,
            window_params,
        ).fetchall():
            target = runs.get(int(row[0]))
            if target is None:
                continue
            target.update(
                {
                    "gct_ms_expected": _as_float(row[1]),
                    "gct_ms_actual": _as_float(row[2]),
                    "gct_delta_pct": _as_float(row[3]),
                    "vo_cm_expected": _as_float(row[4]),
                    "vo_cm_actual": _as_float(row[5]),
                    "vo_delta_cm": _as_float(row[6]),
                    "vr_pct_expected": _as_float(row[7]),
                    "vr_pct_actual": _as_float(row[8]),
                    "vr_delta_pct": _as_float(row[9]),
                    "cadence_expected": _as_float(row[10]),
                    "cadence_actual": _as_float(row[11]),
                    "cadence_delta_pct": _as_float(row[12]),
                    "power_efficiency_score": _as_float(row[13]),
                }
            )

    if "performance_trends" in tables:
        phase_columns = ", ".join(
            f"{phase}_avg_pace_seconds_per_km, {phase}_avg_hr" for phase in _PHASES
        )
        for row in conn.execute(
            f"""
            SELECT activity_id, hr_drift_percentage, {phase_columns}
            FROM performance_trends WHERE {in_window}
            """,
            window_params,
        ).fetchall():
            target = runs.get(int(row[0]))
            if target is None:
                continue
            target["hr_drift_percentage"] = _as_float(row[1])
            for index, phase in enumerate(_PHASES):
                target[f"{phase}_pace_s_per_km"] = _as_float(row[2 + index * 2])
                target[f"{phase}_avg_hr"] = _as_float(row[3 + index * 2])

    if "hr_efficiency" in tables:
        for row in conn.execute(
            f"""
            SELECT activity_id, training_type, primary_zone,
                   zone1_percentage, zone2_percentage, zone3_percentage,
                   zone4_percentage, zone5_percentage
            FROM hr_efficiency WHERE {in_window}
            """,
            window_params,
        ).fetchall():
            target = runs.get(int(row[0]))
            if target is None:
                continue
            target["training_type"] = row[1]
            target["intensity_category"] = resolve_intensity_category(
                row[1],
                _as_float(row[3]) or 0.0,
                _as_float(row[4]) or 0.0,
                _as_float(row[5]) or 0.0,
                _as_float(row[6]) or 0.0,
                _as_float(row[7]) or 0.0,
                row[2],
            )

    if "splits" in tables:
        for row in conn.execute(
            f"""
            SELECT activity_id, COUNT(*)
            FROM splits
            WHERE {in_window} AND {running_split_sql()}
            GROUP BY activity_id
            """,
            [*window_params, *running_split_params()],
        ).fetchall():
            target = runs.get(int(row[0]))
            if target is not None:
                target["n_valid_splits"] = int(row[1])

    return runs


def _mark_extrapolated(
    conn: Any,
    tables: set[str],
    runs: dict[int, dict[str, Any]],
    window_start: str,
    activity_date: str,
) -> None:
    """Flag the runs whose form expectations are extrapolations, in place.

    A form baseline only knows the speeds it was trained on. The model covering
    2026-09-09 was fitted on 1.97-2.38 m/s easy running, so the 2.70 m/s tempo
    run of that day was handed an expectation the curve had never been asked
    for -- and its "high vertical ratio" was reported as a form problem
    (#1273). ``form_evaluations`` does not persist the flag, so it is recomputed
    here from the run's evaluation speed and the covering baseline's range.

    Every run of the window is judged, not just today: an extrapolated history
    row is dropped from that metric's baseline by
    ``run_signals._eligibility_reason``, so a tempo run can neither widen nor
    shift the band an easy run is judged against.
    """
    speeds = _fetch_evaluation_speeds(conn, tables, window_start, activity_date)
    if not speeds:
        return
    ranges = _fetch_baseline_ranges(conn, tables, activity_date)
    if not ranges:
        return

    periods = sorted({period for period, _metric in ranges})
    for activity_id, run in runs.items():
        speed = speeds.get(activity_id)
        if not speed:
            continue
        period = _select_baseline_period(periods, str(run["activity_date"]))
        if period is None:
            continue
        for metric in _FORM_METRICS:
            speed_range = ranges.get((period, metric))
            if speed_range is None:
                continue
            if extrapolation_factor(speed_range, speed) >= EXTRAPOLATION_NOT_JUDGED:
                run[f"{metric}_extrapolated"] = True


def _fetch_evaluation_speeds(
    conn: Any, tables: set[str], window_start: str, activity_date: str
) -> dict[int, float]:
    """``{activity_id: m/s}`` each run's form metrics were evaluated at.

    The same population ``form_baseline.data_fetcher.get_splits_data`` averages:
    the run-phase splits of ``performance_trends.run_splits`` carrying form
    metrics, with walk breaks and GPS fragments filtered out, falling back to
    the unfiltered average when the filter matches nothing (a walk-dominated
    session). One query for the whole window -- a per-run loop here would turn
    one page view into hundreds of queries.
    """
    if "splits" not in tables:
        return {}

    join = phase_clause = ""
    if "performance_trends" in tables:
        join = "LEFT JOIN performance_trends p ON p.activity_id = s.activity_id"
        # ``run_splits`` is the persisted "3,4,6,7" list of split indices.
        phase_clause = (
            "AND (p.run_splits IS NULL OR TRIM(p.run_splits) = '' "
            "OR list_contains("
            "list_transform(str_split(p.run_splits, ','), "
            "x -> TRY_CAST(TRIM(x) AS INTEGER)), s.split_index))"
        )

    rows = conn.execute(
        f"""
        SELECT s.activity_id,
               AVG(CASE WHEN {running_split_sql("s")}
                        THEN s.pace_seconds_per_km END),
               AVG(s.pace_seconds_per_km)
        FROM splits s {join}
        WHERE s.activity_id IN (
                  SELECT activity_id FROM activities
                  WHERE activity_date
                        BETWEEN CAST(? AS DATE) AND CAST(? AS DATE))
          AND s.ground_contact_time IS NOT NULL
          AND s.vertical_oscillation IS NOT NULL
          AND s.vertical_ratio IS NOT NULL
          {phase_clause}
        GROUP BY s.activity_id
        """,
        [*running_split_params(), window_start, activity_date],
    ).fetchall()

    speeds: dict[int, float] = {}
    for row in rows:
        pace = _as_float(row[1]) or _as_float(row[2])
        if pace and pace > 0:
            speeds[int(row[0])] = 1000.0 / pace
    return speeds


def _fetch_baseline_ranges(
    conn: Any, tables: set[str], activity_date: str
) -> dict[tuple[tuple[str, str], str], tuple[float | None, float | None]]:
    """``{((period_start, period_end), metric): (min, max)}`` speed ranges."""
    if "form_baseline_history" not in tables:
        return {}

    placeholders = ", ".join("?" for _ in _FORM_METRICS)
    rows = conn.execute(
        f"""
        SELECT metric, CAST(period_start AS VARCHAR), CAST(period_end AS VARCHAR),
               speed_range_min, speed_range_max
        FROM form_baseline_history
        WHERE user_id = ? AND condition_group = ?
          AND metric IN ({placeholders})
          AND period_start <= CAST(? AS DATE)
        """,
        [
            _BASELINE_USER_ID,
            _BASELINE_CONDITION_GROUP,
            *_FORM_METRICS,
            activity_date,
        ],
    ).fetchall()

    return {
        ((str(row[1]), str(row[2])), str(row[0])): (
            _as_float(row[3]),
            _as_float(row[4]),
        )
        for row in rows
    }


def _select_baseline_period(
    periods: list[tuple[str, str]], run_date: str
) -> tuple[str, str] | None:
    """The baseline window a run's date is read against, or ``None``.

    The same rule as ``form_baseline.model_loader.load_models_from_db``: a
    period that *covers* the date wins over one that has already ended (a
    baseline's ``period_end`` is the nominal end of its training window, not the
    cut-off of the data behind it), and ties break on the most recent window.
    """
    candidates = [period for period in periods if period[0] <= run_date]
    if not candidates:
        return None
    ordered = sorted(
        candidates,
        key=lambda period: (
            period[0] if period[1] >= run_date else period[1],
            period[1],
            period[0],
        ),
        reverse=True,
    )
    return min(ordered, key=lambda period: 0 if period[1] >= run_date else 1)


def _fetch_zone_rows(conn: Any, activity_id: int) -> list[tuple[Any, ...]]:
    """``heart_rate_zones`` rows for one activity, ordered by zone number."""
    return list(
        conn.execute(
            """
            SELECT zone_number, zone_low_boundary, zone_high_boundary,
                   time_in_zone_seconds, zone_percentage
            FROM heart_rate_zones WHERE activity_id = ? ORDER BY zone_number
            """,
            [activity_id],
        ).fetchall()
    )


def _fetch_elevation(conn: Any, activity_id: int) -> dict[str, float | None]:
    """Total gain, distance and the largest single-split change of one run."""
    row = conn.execute(
        """
        SELECT SUM(elevation_gain), SUM(distance),
               MAX(COALESCE(elevation_gain, 0) + COALESCE(elevation_loss, 0))
        FROM splits WHERE activity_id = ?
        """,
        [activity_id],
    ).fetchone()
    if row is None:
        return {}
    return {
        "gain_m": _as_float(row[0]),
        "distance_km": _as_float(row[1]),
        "max_split_change_m": _as_float(row[2]),
    }


def _fetch_splits(
    conn: Any, activity_ids: list[int]
) -> dict[int, list[dict[str, Any]]]:
    """Split rows for today plus the recurrence lookback, in one query.

    Column names are translated to the ones
    :func:`~garmin_mcp.analysis.run_moments.detect_moments` reads. Every split
    is loaded -- fragments included -- because the scene positions are
    cumulative over the whole run; which splits are *drawn* or *measured* is
    the detector's decision, not this query's (#1268).
    """
    if not activity_ids:
        return {}
    placeholders = ", ".join("?" for _ in activity_ids)
    # ``workout_step_index`` arrived with #1296; an older database without the
    # column still gets a report, just without the step-index break.
    step_index = (
        "workout_step_index"
        if _has_column(conn, "splits", "workout_step_index")
        else "NULL"
    )
    rows = conn.execute(
        f"""
        SELECT activity_id, split_index, distance, pace_seconds_per_km,
               heart_rate, max_heart_rate, cadence, elevation_gain,
               role_phase, intensity_type, start_time_s, end_time_s,
               duration_seconds, {step_index}
        FROM splits WHERE activity_id IN ({placeholders})
        ORDER BY activity_id, split_index
        """,
        list(activity_ids),
    ).fetchall()

    splits: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        splits.setdefault(int(row[0]), []).append(
            {
                "split_index": _as_int(row[1]),
                "distance_km": _as_float(row[2]),
                "pace_s_per_km": _as_float(row[3]),
                "avg_hr": _as_float(row[4]),
                "max_hr": _as_float(row[5]),
                "cadence": _as_float(row[6]),
                "elevation_gain_m": _as_float(row[7]),
                "role_phase": row[8],
                "intensity_type": row[9],
                "start_s": _as_float(row[10]),
                "end_s": _as_float(row[11]),
                "duration_s": _as_float(row[12]),
                "workout_step_index": _as_int(row[13]),
            }
        )
    return splits


def _steady_splits(
    splits: Sequence[Mapping[str, Any]],
    samples: Sequence[Mapping[str, Any]],
    steady: Sequence[bool] | None = None,
) -> list[dict[str, Any]]:
    """``splits`` with each kilometre's HR read over its steady seconds (#1320).

    Without a time series the lap averages are all there is, and they are
    returned as they are. ``steady`` is today's mask when the caller already
    built it; a look-back run builds its own.
    """
    if not samples:
        return [dict(split) for split in splits]
    mask = steady if steady is not None else steady_mask(samples, splits)
    return masked_split_hr(samples, mask, splits)


def _has_column(conn: Any, table: str, column: str) -> bool:
    """Whether ``table`` in the attached database carries ``column``."""
    row = conn.execute(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema = 'main' AND table_name = ? AND column_name = ?",
        [table, column],
    ).fetchone()
    return bool(row and row[0])


def _fetch_hr_samples(conn: Any, activity_id: int) -> list[dict[str, Any]]:
    """One run's time series in the shape ``analysis.hr_windows`` reads.

    Heart rate for the ceiling, speed / cadence / the three duration clocks
    for the stops, pauses and bursts whose HR recovery is kept out of it
    (#1313). The zone totals cannot tell a steady second from one spent
    recovering from a surge, so every run with a time series is read here.

    A column an older database (or a Web fixture) does not carry is read as
    ``NULL``: the affected event kind is then simply not detected.
    """
    present = _table_columns(conn, "time_series_metrics")
    if "timestamp_s" not in present:
        return []
    selected = ", ".join(
        column if column in present else f"NULL AS {column}"
        for column in _SAMPLE_COLUMNS
    )
    rows = conn.execute(
        f"""
        SELECT timestamp_s, {selected}
        FROM time_series_metrics
        WHERE activity_id = ?
        ORDER BY timestamp_s
        """,
        [activity_id],
    ).fetchall()
    return [
        {
            "timestamp_s": float(row[0]),
            **{
                column: _as_float(value)
                for column, value in zip(_SAMPLE_COLUMNS, row[1:], strict=True)
            },
        }
        for row in rows
        if row[0] is not None
    ]


# The ``time_series_metrics`` columns ``analysis.hr_windows`` reads besides
# ``timestamp_s``.
_SAMPLE_COLUMNS: tuple[str, ...] = (
    "heart_rate",
    "speed",
    "cadence",
    "sum_moving_duration",
    "sum_elapsed_duration",
    "sum_duration",
)


def _table_columns(conn: Any, table: str) -> set[str]:
    """Column names of ``table`` in the attached database."""
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'main' AND table_name = ?",
        [table],
    ).fetchall()
    return {str(row[0]) for row in rows}


def _activity_row(row: tuple[Any, ...]) -> dict[str, Any]:
    """One ``activities`` row as the plain dict the pure modules consume."""
    return {
        "activity_id": int(row[0]),
        "activity_date": str(row[1]),
        "distance_km": _as_float(row[2]),
        "duration_min": (None if row[3] is None else round(float(row[3]) / 60.0, 1)),
        "avg_pace_seconds_per_km": _as_float(row[4]),
        "avg_hr": _as_float(row[5]),
        "temp_celsius": _as_float(row[6]),
        "humidity_pct": _as_float(row[7]),
        "wind_speed_kmh": _as_float(row[8]),
        "training_type": None,
        "intensity_category": "unknown",
        "n_valid_splits": 0,
    }


def _history_before(
    runs: dict[int, dict[str, Any]], activity_id: int, activity_date: str
) -> list[dict[str, Any]]:
    """The window's prior runs, ascending by date (today itself excluded)."""
    history = [
        run
        for run in runs.values()
        if int(run["activity_id"]) != activity_id
        and str(run["activity_date"]) < activity_date
    ]
    history.sort(key=lambda run: (str(run["activity_date"]), int(run["activity_id"])))
    return history


# --------------------------------------------------------------------------- #
# Payload blocks
# --------------------------------------------------------------------------- #


def _headline(
    verdict: dict[str, Any] | None,
    signals: list[dict[str, Any]],
    moments: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """The one line above the fold: plan label, adverse signals, concern scenes.

    A scene is flagged only when the purpose policy (#1314) calls it a
    ``concern``: a walk break on an aerobic long run is not news, the same
    break on a goal-pace rehearsal is.
    """
    label = NO_PLAN_LABEL
    if verdict is not None:
        label = _VERDICT_LABELS.get(str(verdict.get("verdict")), NO_PLAN_LABEL)

    flags = [
        _ADVERSE_FLAG_LABELS[signal["metric"]]
        for signal in signals
        if signal.get("adverse") and signal["metric"] in _ADVERSE_FLAG_LABELS
    ]
    flags.extend(
        str(moment["label_ja"])
        for moment in moments
        if (moment.get("policy") or {}).get("verdict") == "concern"
        and moment.get("label_ja")
    )
    return {"plan_label": label, "flag_count": len(flags), "flag_labels": flags}


def _allowances(prescription: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The prescription's ``allowances`` object, decoded when stored as JSON."""
    if prescription is None:
        return None
    allowances = prescription.get("allowances")
    if isinstance(allowances, str):
        try:
            allowances = json.loads(allowances)
        except ValueError:
            return None
    return dict(allowances) if isinstance(allowances, Mapping) else None


# Scene kinds that only a rep session produces.
_REP_SCENE_KINDS: frozenset[str] = frozenset({"rep", "work_set"})


def _purpose_facts(
    today: Mapping[str, Any],
    splits: Sequence[Mapping[str, Any]],
    moments: Sequence[Mapping[str, Any]],
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    """The facts ``resolve_purpose`` infers an unprescribed run's purpose from.

    Every value comes from rows already loaded for the report; nothing here
    queries the database.
    """
    category = today.get("intensity_category")
    run_splits = [
        {
            "avg_heart_rate": split.get("avg_hr"),
            "avg_pace_seconds_per_km": split.get("pace_s_per_km"),
        }
        for split in splits
        if str(split.get("role_phase") or "run").strip().lower() == "run"
        # Fragments are lap-button / GPS slivers, not a kilometre of a build-up.
        and (_as_float(split.get("distance_km")) or 0.0) >= MIN_SPLIT_KM
    ]
    return {
        "activity_name": identity.get("activity_name"),
        "moving_minutes": _as_float(today.get("duration_min")),
        "intensity_class": intensity_class(today.get("training_type"))
        or intensity_class(category if category != "unknown" else None),
        "intensity_category": category if category != "unknown" else None,
        "has_rep_structure": any(
            moment.get("kind") in _REP_SCENE_KINDS for moment in moments
        ),
        "is_progression": detect_progression_session(None, run_splits),
        "is_goal_race_day": bool(identity.get("is_goal_race_day")),
    }


def _plan_block(
    prescription: dict[str, Any] | None,
    verdict: dict[str, Any] | None,
    today: dict[str, Any],
    zone_rows: list[tuple[Any, ...]],
    *,
    splits: list[dict[str, Any]] | None = None,
    hr_samples: Sequence[Mapping[str, Any]] = (),
    steady: Sequence[bool] = (),
    ceiling_avg_hr: float | None = None,
) -> dict[str, Any] | None:
    """The plan card: the verdict, its per-axis checks and the HR ceiling.

    The checks do not re-judge anything -- each axis reports on / off plan
    exactly as ``compute_prescription_verdict`` decided it, so a tolerance band
    can never drift between the verdict and the card that explains it. The one
    axis that verdict does not know is ``strides`` (#1297): a count of the
    stride laps against the prescribed reps, added when the prescription
    carries strides.

    The ceiling row reads ``ceiling_avg_hr`` -- the steady-running average HR
    (#1313), the same number the verdict judged the ceiling on -- and the
    activity's own average HR when there is none.
    """
    if prescription is None or verdict is None:
        return None
    splits = splits or []

    on_plan = set(verdict.get("on_plan") or [])
    checks: list[dict[str, Any]] = []

    if "rest" in on_plan or _is_rest(prescription):
        checks.append(
            _check(
                "rest",
                "休養",
                "休養" if not _ran(today) else _volume_text(today),
                "rest" in on_plan,
            )
        )
    else:
        checks.append(
            _check(
                "intensity",
                _target_intensity_label(prescription.get("session_type")),
                _intensity_label(
                    today.get("training_type") or today.get("intensity_category")
                ),
                "intensity_class" in on_plan,
            )
        )
        target, actual = _volume_texts(prescription, today)
        if target is not None:
            checks.append(_check("volume", target, actual, "volume" in on_plan))
        hr_high = _as_float(prescription.get("hr_high"))
        avg_hr = (
            ceiling_avg_hr
            if ceiling_avg_hr is not None
            else _as_float(today.get("avg_hr"))
        )
        if hr_high is not None:
            checks.append(
                _check(
                    "hr_ceiling",
                    f"{hr_high:.0f} bpm 以下",
                    "-" if avg_hr is None else f"{avg_hr:.0f} bpm",
                    "hr_ceiling" in on_plan,
                )
            )
        if _prescribed_strides(prescription) is not None:
            checks.append(_strides_check(prescription, splits))

    return {
        "verdict": str(verdict.get("verdict")),
        "title": str(verdict.get("prescription_title") or ""),
        "checks": checks,
        "hr_ceiling": _hr_ceiling(prescription, zone_rows, hr_samples, steady),
    }


# The strides row's status -> the verdict symbol the card draws for it.
_STRIDES_VERDICTS: dict[str, str] = {
    "on_plan": "✅",
    "short": "🟡",
    "missing": "🔴",
}


def _prescribed_strides(prescription: dict[str, Any]) -> dict[str, Any] | None:
    """The prescription's ``strides`` add-on, or ``None`` when it has none."""
    strides = prescription.get("strides")
    if isinstance(strides, str):
        try:
            strides = json.loads(strides)
        except ValueError:
            return None
    if not isinstance(strides, dict) or not _as_int(strides.get("reps")):
        return None
    return strides


def _strides_check(
    prescription: Mapping[str, Any], splits: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """The ``strides`` row of the plan card: stride laps run against the reps.

    ``target`` / ``actual`` read ``"4本"``; ``on_plan`` is ``done >= reps``.
    The status is ``short`` (🟡) when some but not all strides were run and
    ``missing`` (🔴) when none were -- an easy run that skipped its strides
    answered only half of the prescription.
    """
    strides = _prescribed_strides(dict(prescription)) or {}
    reps = _as_int(strides.get("reps")) or 0
    done = _count_strides(splits)
    status = "on_plan" if done >= reps else "short" if done > 0 else "missing"
    return {
        "axis": "strides",
        "target": f"{reps}本",
        "actual": f"{done}本",
        "status": status,
        "on_plan": status == "on_plan",
        "verdict": _STRIDES_VERDICTS[status],
    }


def _count_strides(splits: Sequence[Mapping[str, Any]]) -> int:
    """How many strides were run: each maximal run of stride laps is one."""
    count = 0
    previous_stride = False
    for split in splits:
        is_stride = _is_stride_lap(split)
        if is_stride and not previous_stride:
            count += 1
        previous_stride = is_stride
    return count


def _is_stride_lap(split: Mapping[str, Any]) -> bool:
    """Whether a split was classified as a stride at ingest (#1296)."""
    return str(split.get("role_phase") or "").strip().lower() == "stride"


def _has_stride_laps(splits: Sequence[Mapping[str, Any]]) -> bool:
    """Whether a run carries any stride lap."""
    return any(_is_stride_lap(split) for split in splits)


def _is_jog_lap(split: Mapping[str, Any]) -> bool:
    """A lap that is neither a stride nor the jog-recovery of one."""
    role = str(split.get("role_phase") or "").strip().lower()
    return role not in {"stride", "recovery"}


def _ceiling_avg_hr(
    splits: Sequence[Mapping[str, Any]],
    hr_samples: Sequence[Mapping[str, Any]],
    steady: Sequence[bool],
) -> float | None:
    """The average HR the ceiling is judged on, or ``None`` for the activity's.

    With a time series it is the steady-running average (#1313): stops,
    pauses, bursts and effort laps are left out together with the heart
    rate's recovery from each. Without one, a run with strides falls back to
    its jog laps (#1297) and any other run to the activity's own average.
    """
    if hr_samples:
        steady_hr = masked_mean_hr(hr_samples, steady)
        if steady_hr is not None:
            return steady_hr
    return _jog_avg_hr(splits)


def _jog_avg_hr(splits: Sequence[Mapping[str, Any]]) -> float | None:
    """Time-weighted average HR of the jog laps of a run with strides.

    The fallback when the run has no time series. ``None`` when the run has
    no stride lap -- then the whole run *is* the jog and the activity's own
    average HR stands.
    """
    if not _has_stride_laps(splits):
        return None
    pairs = [
        (hr, _lap_seconds(split))
        for split in splits
        if _is_jog_lap(split) and (hr := _as_float(split.get("avg_hr"))) is not None
    ]
    weight = sum(duration for _, duration in pairs)
    if not pairs or weight <= 0:
        return None
    return round(sum(hr * duration for hr, duration in pairs) / weight, 1)


def _lap_seconds(split: Mapping[str, Any]) -> float:
    """How long a lap took: its recorded duration, else ``end - start``."""
    duration = _as_float(split.get("duration_s"))
    if duration and duration > 0:
        return duration
    start = _as_float(split.get("start_s"))
    end = _as_float(split.get("end_s"))
    if start is not None and end is not None and end > start:
        return end - start
    return 0.0


def _intensity_label(raw: Any) -> str:
    """One Japanese name for an intensity, whichever vocabulary named it.

    The plan card used to print the prescription's ``session_type`` against the
    activity's ``training_type`` -- ``easy`` vs ``aerobic_base`` -- so a run
    that answered its plan exactly still read as a mismatch. Both sides are
    resolved through the same intensity family (``resolve_intensity_category``,
    with the plan's own session words mapped onto it) and printed in one label
    set; the one distinction kept is recovery, which the athlete runs as its own
    session rather than as an easy run.
    """
    label = str(raw or "").strip().lower()
    if not label:
        return "-"
    if label in _RAW_INTENSITY_LABELS:
        return _RAW_INTENSITY_LABELS[label]
    if label in _PLAN_INTENSITY_LABELS:
        return _PLAN_INTENSITY_LABELS[label]
    family = resolve_intensity_category(label, 0.0, 0.0, 0.0, 0.0, 0.0, None)
    return _FAMILY_INTENSITY_LABELS.get(family, label)


def _target_intensity_label(session_type: Any) -> str:
    """The prescribed intensity, plus what the session type says beyond it.

    The row compares intensity, so both sides must be the intensity family:
    printing the session type (``ロング``) against the run's family
    (``イージー``) made an on-plan long run read as a mismatch (#1273). The
    session word is kept as a parenthesis on the target -- ``イージー（ロング走）``
    -- where it explains the target without pretending to be a second axis.
    """
    label = _intensity_label(session_type)
    suffix = _SESSION_TYPE_SUFFIX_JA.get(str(session_type or "").strip().lower())
    return f"{label}（{suffix}）" if suffix and label != "-" else label


def _check(axis: str, target: str, actual: str, on_plan: bool) -> dict[str, Any]:
    """One row of the plan card."""
    return {
        "axis": axis,
        "target": target,
        "actual": actual,
        "status": "on_plan" if on_plan else "off_plan",
        "on_plan": bool(on_plan),
    }


def _hr_ceiling(
    prescription: dict[str, Any],
    zone_rows: list[tuple[Any, ...]],
    hr_samples: Sequence[Mapping[str, Any]] = (),
    steady: Sequence[bool] = (),
) -> dict[str, Any] | None:
    """Time spent above the prescribed ceiling, steady running only.

    The heart-rate time series is read through the steady mask
    (``analysis.hr_windows.steady_mask``, #1313): a stride is *meant* to clear
    an easy ceiling (#1297), and after a surge, a stop or an auto-pause the
    heart rate needs a while to settle -- none of those seconds are the steady
    running the ceiling guards, and the zones cannot tell them apart.

    Without a time series the zones are the fallback: "how long was the
    athlete above 150?" is the sum of every zone whose *low* boundary is at or
    above the ceiling.
    """
    bpm = _as_int(prescription.get("hr_high"))
    if bpm is None:
        return None
    if hr_samples:
        steady_over = seconds_over(hr_samples, steady, bpm)
        if steady_over is not None:
            return {"bpm": bpm, **steady_over}
    if not zone_rows:
        return None

    total = sum(_as_float(row[3]) or 0.0 for row in zone_rows)
    over = sum(
        _as_float(row[3]) or 0.0
        for row in zone_rows
        if (_as_float(row[1]) or 0.0) >= bpm
    )
    return {
        "bpm": bpm,
        "seconds_over": round(over, 1),
        "pct_over": round(over / total * 100.0, 1) if total else 0.0,
    }


def _zones(zone_rows: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    """``[{"zone": 1, "pct": 12.3}, …]`` for the run's HR zone distribution."""
    return [
        {"zone": int(row[0]), "pct": round(_as_float(row[4]) or 0.0, 1)}
        for row in zone_rows
        if row[0] is not None
    ]


def _zones_detail(zone_rows: list[tuple[Any, ...]]) -> dict[str, Any] | None:
    """The zone boundaries in the shape ``compute_next_run_target`` expects."""
    if not zone_rows:
        return None
    return {
        "zones": [
            {
                "zone_number": int(row[0]),
                "low_boundary": _as_int(row[1]),
                "high_boundary": _as_int(row[2]),
                "time_in_zone_seconds": _as_float(row[3]),
                "zone_percentage": _as_float(row[4]),
            }
            for row in zone_rows
            if row[0] is not None
        ]
    }


def _phases(today: dict[str, Any]) -> list[dict[str, Any]]:
    """The run's phase structure, skipping phases the run did not have."""
    phases = []
    for phase in _PHASES:
        pace = _as_float(today.get(f"{phase}_pace_s_per_km"))
        avg_hr = _as_float(today.get(f"{phase}_avg_hr"))
        if pace is None and avg_hr is None:
            continue
        phases.append(
            {
                "phase": phase,
                "pace_s_per_km": _round(pace),
                "avg_hr": _round(avg_hr),
            }
        )
    return phases


def _conditions(
    today: dict[str, Any], elevation: dict[str, float | None]
) -> dict[str, Any]:
    """Weather and terrain the run was actually run in.

    Temperature / humidity / wind come from the weather station row on
    ``activities`` (never the device temperature, which carries body heat).
    """
    wind_kmh = _as_float(today.get("wind_speed_kmh"))
    gain = elevation.get("gain_m")
    distance = elevation.get("distance_km") or _as_float(today.get("distance_km"))
    gain_per_km = (
        gain / distance if gain is not None and distance and distance > 0 else None
    )
    return {
        "temp_c": _round(_as_float(today.get("temp_celsius"))),
        "humidity_pct": _round(_as_float(today.get("humidity_pct"))),
        "wind_mps": None if wind_kmh is None else round(wind_kmh / 3.6, 1),
        "terrain": _classify_terrain(gain_per_km, elevation.get("max_split_change_m")),
        "elevation_gain_m": None if gain is None else round(gain, 1),
    }


def _classify_terrain(
    gain_per_km: float | None, max_split_change: float | None
) -> str | None:
    """Terrain band for an average gain per km (``None`` when unknown)."""
    if gain_per_km is None:
        return None
    for limit, label in _TERRAIN_BANDS:
        if gain_per_km < limit:
            if (
                label == "flat"
                and max_split_change is not None
                and max_split_change >= _SPLIT_UNDULATION_M
            ):
                return "undulating"
            return label
    return "mountainous"


def _vs_previous(
    today: dict[str, Any], history: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Delta chips against the previous run of the same intensity family."""
    family = today.get("intensity_category")
    previous = next(
        (run for run in reversed(history) if run.get("intensity_category") == family),
        None,
    )
    if previous is None:
        return None
    return compute_vs_previous(_comparable(today), _comparable(previous))


def _comparable(run: dict[str, Any]) -> dict[str, Any]:
    """The metrics ``compute_vs_previous`` compares, in its own key names."""
    return {
        "activity_id": int(run["activity_id"]),
        "activity_date": str(run["activity_date"]),
        "pace_s_per_km": _as_float(run.get("avg_pace_seconds_per_km")),
        "avg_hr": _as_float(run.get("avg_hr")),
        "gct_ms": _as_float(run.get("gct_ms_actual")),
        "cadence_spm": _as_float(run.get("cadence_actual")),
        "decoupling_pct": None,
    }


def _scheduled_session(plan: Any, activity_date: str) -> dict[str, Any] | None:
    """The next prescribed run after ``activity_date``, or ``None``.

    Rows the athlete cannot answer with a run (strength, cross-training, a rest
    day) and rows already marked ``skipped`` are passed over, so "what is next"
    is the next time they actually go running.
    """
    try:
        rows = plan.list_prescriptions(
            _shift_days(activity_date, 1),
            _shift_days(activity_date, _NEXT_SESSION_HORIZON_DAYS),
        )
    except Exception as exc:  # pragma: no cover - degraded DB only
        logger.debug("no prescriptions after %s: %s", activity_date, exc)
        return None

    for row in rows:
        if str(row.get("status") or "").strip().lower() == "skipped":
            continue
        session_type = row.get("session_type")
        if not _is_run_session(session_type):
            continue
        on_date = str(row.get("date") or "")[:10]
        if not on_date:
            continue
        return {
            "date": on_date,
            "days_ahead": _days_between(activity_date, on_date),
            "session_type": str(session_type),
            "session_label_ja": _target_intensity_label(session_type),
            "title": row.get("title"),
            "target_km": _as_float(row.get("target_km")),
            "target_minutes": _as_int(row.get("target_minutes")),
            "hr_low": _as_int(row.get("hr_low")),
            "hr_high": _as_int(row.get("hr_high")),
            "source": "prescription",
        }
    return None


def _ladder_session(plan: Any, activity_date: str) -> dict[str, Any] | None:
    """The block's next long-run ladder step, or ``None`` when there is none.

    The long run is the week's last day by the same convention
    ``compute_week_position`` uses, so the step's ``week_start`` fixes its date
    without the plan having been written out day by day yet.
    """
    try:
        week_start = plan.resolve_week_start(activity_date)
        ladder_step = plan.get_ladder_step_for_week(week_start)
    except Exception as exc:  # pragma: no cover - degraded DB only
        logger.debug("no ladder step for %s: %s", activity_date, exc)
        return None

    step = (ladder_step or {}).get("next")
    if not isinstance(step, dict) or not step.get("week_start"):
        return None

    on_date = _shift_days(str(step["week_start"]), 6)
    days_ahead = _days_between(activity_date, on_date)
    if days_ahead is None or days_ahead <= 0:
        return None
    return {
        "date": on_date,
        "days_ahead": days_ahead,
        "session_type": "long",
        "session_label_ja": _target_intensity_label("long"),
        "title": step.get("title"),
        "target_km": _as_float(step.get("target_km")),
        "target_minutes": _as_int(step.get("target_minutes")),
        "hr_low": None,
        "hr_high": None,
        "source": "ladder",
    }


def _projected_session(next_run_target: dict[str, Any] | None) -> dict[str, Any] | None:
    """Today's family projected forward when the plan says nothing.

    Dateless on purpose: nothing here knows *when* the next run happens, only
    what kind of run it would be and the HR band it should be run at.
    """
    if not next_run_target or next_run_target.get("insufficient_data"):
        return None
    session_type = next_run_target.get("recommended_type")
    if not session_type:
        return None
    return {
        "date": None,
        "days_ahead": None,
        "session_type": str(session_type),
        "session_label_ja": _target_intensity_label(session_type),
        "title": None,
        "target_km": None,
        "target_minutes": None,
        "hr_low": _as_int(next_run_target.get("target_hr_low")),
        "hr_high": _as_int(next_run_target.get("target_hr_high")),
        "source": "same_type",
    }


def _is_run_session(session_type: Any) -> bool:
    """Whether a prescribed session is one the athlete answers by running."""
    session_class = intensity_class(session_type)
    return session_class is not None and session_class != REST_INTENSITY_CLASS


def _days_between(from_date: str, to_date: str) -> int | None:
    """Whole days from ``from_date`` to ``to_date`` (``None`` when unparseable)."""
    try:
        start = date.fromisoformat(from_date[:10])
        end = date.fromisoformat(to_date[:10])
    except ValueError:  # pragma: no cover - defensive
        return None
    return (end - start).days


def _actual(today: dict[str, Any]) -> dict[str, Any]:
    """The run as ``compute_prescription_verdict`` wants to see it."""
    return {
        "distance_km": _as_float(today.get("distance_km")),
        "duration_min": _as_float(today.get("duration_min")),
        "avg_hr": _as_float(today.get("avg_hr")),
        "training_type": today.get("training_type"),
    }


def _is_rest(prescription: dict[str, Any]) -> bool:
    """Whether the day prescribed rest (running at all is then the deviation)."""
    return str(prescription.get("session_type") or "").strip().lower() == "rest"


def _ran(today: dict[str, Any]) -> bool:
    """Whether the athlete ran at all on the day."""
    return (_as_float(today.get("distance_km")) or 0.0) > 0 or (
        _as_float(today.get("duration_min")) or 0.0
    ) > 0


def _volume_texts(
    prescription: dict[str, Any], today: dict[str, Any]
) -> tuple[str | None, str]:
    """``("8.0km", "8.1km（101%）")`` for the prescribed volume, or no target.

    Distance is preferred when the prescription names ``target_km``, matching
    the order ``compute_prescription_verdict`` compares them in.
    """
    target_km = _as_float(prescription.get("target_km"))
    distance_km = _as_float(today.get("distance_km"))
    if target_km and target_km > 0:
        return f"{target_km:.1f}km", _with_pct(distance_km, target_km, "km")

    target_min = _as_float(prescription.get("target_minutes"))
    duration_min = _as_float(today.get("duration_min"))
    if target_min and target_min > 0:
        return f"{target_min:.0f}分", _with_pct(duration_min, target_min, "分")
    return None, "-"


def _with_pct(value: float | None, target: float, unit: str) -> str:
    """``"8.1km（101%）"`` -- the achieved volume and its share of the target."""
    if value is None:
        return "-"
    done = f"{value:.1f}{unit}" if unit == "km" else f"{value:.0f}{unit}"
    return f"{done}（{round(value / target * 100)}%）"


def _volume_text(today: dict[str, Any]) -> str:
    """What the athlete did, for a rest day that was not taken."""
    distance_km = _as_float(today.get("distance_km"))
    if distance_km:
        return f"{distance_km:.1f}km"
    duration_min = _as_float(today.get("duration_min"))
    return f"{duration_min:.0f}分" if duration_min else "ラン"


# --------------------------------------------------------------------------- #
# Scalar helpers
# --------------------------------------------------------------------------- #


def _as_float(value: Any) -> float | None:
    """Coerce a DuckDB / numpy scalar to a plain ``float`` (``None`` if absent)."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round(value: float | None) -> float | None:
    """1 dp is the display resolution of every unit in the payload."""
    return None if value is None else round(value, 1)


def _as_int(value: Any) -> int | None:
    """Coerce a DuckDB / numpy scalar to a plain ``int`` (``None`` if absent)."""
    number = _as_float(value)
    return None if number is None else int(round(number))


def _shift_days(activity_date: str, days: int) -> str:
    """``activity_date`` shifted by ``days``, as ``YYYY-MM-DD``."""
    return (date.fromisoformat(activity_date[:10]) + timedelta(days=days)).isoformat()
