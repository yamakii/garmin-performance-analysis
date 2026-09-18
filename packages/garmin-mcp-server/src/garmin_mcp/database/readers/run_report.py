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
plan verdict               ``analysis.derivations.compute_prescription_verdict``
delta chips, next target   ``analysis.derivations`` (``compute_vs_previous`` …)
intensity family           ``database.inserters.hr_efficiency``
expected HR                ``rag.queries.heat_adjustment.HeatAdjustmentModel``
which splits count          ``form_baseline.split_filter``
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

import logging
from datetime import date, timedelta
from typing import Any

from garmin_mcp.analysis.derivations import (
    compute_next_run_target,
    compute_prescription_verdict,
    compute_vs_previous,
    select_prescription_for_run,
)
from garmin_mcp.analysis.run_moments import (
    RECURRENCE_LOOKBACK,
    detect_moments,
    detect_recurrence,
)
from garmin_mcp.database.inserters.hr_efficiency import resolve_intensity_category
from garmin_mcp.database.readers.base import BaseDBReader
from garmin_mcp.form_baseline.split_filter import (
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
            ``headline``, ``plan``, ``signals``, ``zones``, ``moments``,
            ``recurrence``, ``phases``, ``conditions``, ``vs_previous`` and
            ``next_run_target`` (see the module docstring for who computes
            what). Every value is JSON-serialisable without a custom encoder.
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

        prescription = self._load_prescription(activity_date)
        hr_ceiling_bpm = _as_int(prescription.get("hr_high")) if prescription else None

        verdict = compute_prescription_verdict(prescription, _actual(today))
        signals = self._signals(today, history)
        moments = detect_moments(
            splits_by_id.get(activity_id, []), hr_ceiling=hr_ceiling_bpm
        )
        recurrence = detect_recurrence(
            moments,
            [
                {
                    "activity_date": str(run["activity_date"]),
                    # Previous runs are judged against *today's* ceiling: the
                    # family's prescribed ceiling is stable, and loading each
                    # run's own prescription would reintroduce a per-run loop.
                    "moments": detect_moments(
                        splits_by_id.get(int(run["activity_id"]), []),
                        hr_ceiling=hr_ceiling_bpm,
                    ),
                }
                for run in reversed(family_previous)
            ],
        )

        return {
            "activity_id": int(activity_id),
            "activity_date": activity_date,
            "intensity_category": str(today.get("intensity_category") or "unknown"),
            "headline": _headline(verdict, signals),
            "plan": _plan_block(prescription, verdict, today, zone_rows),
            "signals": signals,
            "zones": _zones(zone_rows),
            "moments": moments,
            "recurrence": recurrence,
            "phases": _phases(today),
            "conditions": _conditions(today, elevation),
            "vs_previous": _vs_previous(today, history),
            "next_run_target": self._next_run_target(
                activity_id, today, zone_rows, prescription
            ),
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
    :func:`~garmin_mcp.analysis.run_moments.detect_moments` reads.
    """
    if not activity_ids:
        return {}
    placeholders = ", ".join("?" for _ in activity_ids)
    rows = conn.execute(
        f"""
        SELECT activity_id, split_index, distance, pace_seconds_per_km,
               heart_rate, max_heart_rate, cadence, elevation_gain
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
            }
        )
    return splits


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
    verdict: dict[str, Any] | None, signals: list[dict[str, Any]]
) -> dict[str, Any]:
    """The one line above the fold: plan label plus the adverse signals."""
    label = NO_PLAN_LABEL
    if verdict is not None:
        label = _VERDICT_LABELS.get(str(verdict.get("verdict")), NO_PLAN_LABEL)

    flags = [
        _ADVERSE_FLAG_LABELS[signal["metric"]]
        for signal in signals
        if signal.get("adverse") and signal["metric"] in _ADVERSE_FLAG_LABELS
    ]
    return {"plan_label": label, "flag_count": len(flags), "flag_labels": flags}


def _plan_block(
    prescription: dict[str, Any] | None,
    verdict: dict[str, Any] | None,
    today: dict[str, Any],
    zone_rows: list[tuple[Any, ...]],
) -> dict[str, Any] | None:
    """The plan card: the verdict, its per-axis checks and the HR ceiling.

    The checks do not re-judge anything -- each axis reports on / off plan
    exactly as ``compute_prescription_verdict`` decided it, so a tolerance band
    can never drift between the verdict and the card that explains it.
    """
    if prescription is None or verdict is None:
        return None

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
                str(prescription.get("session_type") or "-"),
                str(today.get("training_type") or "-"),
                "intensity_class" in on_plan,
            )
        )
        target, actual = _volume_texts(prescription, today)
        if target is not None:
            checks.append(_check("volume", target, actual, "volume" in on_plan))
        hr_high = _as_float(prescription.get("hr_high"))
        avg_hr = _as_float(today.get("avg_hr"))
        if hr_high is not None:
            checks.append(
                _check(
                    "hr_ceiling",
                    f"≦{hr_high:.0f}bpm",
                    "-" if avg_hr is None else f"{avg_hr:.0f}bpm",
                    "hr_ceiling" in on_plan,
                )
            )

    return {
        "verdict": str(verdict.get("verdict")),
        "title": str(verdict.get("prescription_title") or ""),
        "checks": checks,
        "hr_ceiling": _hr_ceiling(prescription, zone_rows),
    }


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
    prescription: dict[str, Any], zone_rows: list[tuple[Any, ...]]
) -> dict[str, Any] | None:
    """Time spent above the prescribed ceiling, read off the HR zones.

    The zones already carry the seconds per band, so "how long was the athlete
    above 150?" is the sum of every zone whose *low* boundary is at or above
    the ceiling -- no time-series scan and no per-second work.
    """
    bpm = _as_int(prescription.get("hr_high"))
    if bpm is None or not zone_rows:
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
