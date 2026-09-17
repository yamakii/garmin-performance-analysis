"""Post-event protection window: is the athlete still recovering from a race?

A race (or any comparably big stimulus) leaves the legs fragile for weeks even
when the recovery *feels* complete. The 2026 injury followed exactly that
pattern: a half marathon on 2025-12-14, then a long run 15 days later that was
35 % longer than anything run in the eight weeks before the race.

The lesson this module encodes is **where the event comes from**. That half
averaged only 141 bpm -- a cold-weather optical under-read -- so any
HR-intensity heuristic would have missed it entirely. The race calendar
(``athlete_goals`` and the ``kind == "race"`` steps of the long-run ladder) is
therefore the source of truth, and the HR reading is only a fallback proxy for
big efforts that were never written down. A proxy event never overrides a
calendar event on the same day.

The gate itself is arithmetic:

- The window is :data:`WINDOW_DAYS` days long and starts the day *after* the
  event (the event day itself is not "since the event").
- The ceiling is the longest run in the :data:`PRE_EVENT_LOOKBACK_DAYS` days
  before the event -- what the legs were demonstrably trained for. Exceeding it
  while still inside the window is the precursor being guarded against.
- ``green`` inside the ceiling (or outside the window), ``yellow`` above it,
  ``red`` above it by more than :data:`RED_OVERSHOOT_PCT`, and
  ``insufficient_data`` when the window applies but no ceiling can be computed.
"""

from __future__ import annotations

from datetime import date as date_cls
from datetime import timedelta
from typing import Any

#: Length of the protection window (days after the event).
WINDOW_DAYS = 21

#: Lookback used for the pre-event ceiling (longest run in the 8 weeks before).
PRE_EVENT_LOOKBACK_DAYS = 56

#: Overshoot above the ceiling (%) that turns a yellow into a red.
RED_OVERSHOOT_PCT = 10.0

#: Minimum distance (km) for a run to qualify as an HR-proxy big stimulus.
PROXY_MIN_KM = 18.0

#: Event-source precedence when several sources land on the same date: the
#: calendar always wins over the HR proxy (the 141 bpm half lesson).
_SOURCE_RANK: dict[str, int] = {"goal": 0, "ladder": 1, "hr_proxy": 2}


def _as_date(value: Any) -> date_cls | None:
    """Coerce a ``date`` / ``datetime`` / ``YYYY-MM-DD`` string to ``date``."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, date_cls):
        return value
    try:
        return date_cls.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _as_float(value: Any) -> float | None:
    """Coerce a metric to ``float``, or ``None`` when absent / non-numeric."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sunday_of_week(week_start: date_cls) -> date_cls:
    """Map a ladder week's start day to the race day (that week's Sunday).

    Races are run on the Sunday and the ladder only records the week. Taking
    the first Sunday on or after ``week_start`` respects any
    ``athlete_profile.week_start_day``: a Monday-based week start maps forward
    six days, while a Sunday-based one is already the race day.
    """
    return week_start + timedelta(days=(6 - week_start.weekday()) % 7)


def resolve_big_events(
    goals: list[dict[str, Any]],
    ladder_steps: list[dict[str, Any]],
    hard_long_runs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge the calendar and HR-proxy sources into one event list.

    Args:
        goals: ``athlete_goals`` rows (any status) with ``race_date`` /
            ``race_name``. Rows without a date are ignored.
        ladder_steps: Long-run ladder steps with ``kind == "race"``, carrying
            ``week_start`` (and optionally ``target_km`` / ``note``). Steps
            whose ``kind`` is present and not ``"race"`` are ignored.
        hard_long_runs: Candidate activities for the HR proxy, each with
            ``activity_id``, ``activity_date``, ``distance_km``,
            ``avg_heart_rate`` and ``zone3_lower`` (the Garmin-native zone-3
            lower boundary of that activity; no HR formulas).

    Returns:
        ``[{"date": "YYYY-MM-DD", "source": "goal"|"ladder"|"hr_proxy",
        "label": str, "activity_id": int|None}]`` deduped by date (goal beats
        ladder beats proxy) and sorted by date ascending.
    """
    candidates: list[dict[str, Any]] = []

    for goal in goals:
        event_date = _as_date(goal.get("race_date"))
        if event_date is None:
            continue
        candidates.append(
            {
                "date": event_date.isoformat(),
                "source": "goal",
                "label": str(goal.get("race_name") or "レース"),
                "activity_id": None,
            }
        )

    for step in ladder_steps:
        kind = step.get("kind")
        if kind is not None and str(kind).lower() != "race":
            continue
        week_start = _as_date(step.get("week_start"))
        if week_start is None:
            continue
        target_km = _as_float(step.get("target_km"))
        label = str(step.get("note") or "").strip()
        if not label:
            label = (
                f"ラダーのレース週 ({target_km:.1f}km)"
                if target_km is not None
                else "ラダーのレース週"
            )
        candidates.append(
            {
                "date": _sunday_of_week(week_start).isoformat(),
                "source": "ladder",
                "label": label,
                "activity_id": None,
            }
        )

    for run in hard_long_runs:
        run_date = _as_date(run.get("activity_date"))
        distance_km = _as_float(run.get("distance_km"))
        avg_hr = _as_float(run.get("avg_heart_rate"))
        zone3_lower = _as_float(run.get("zone3_lower"))
        if run_date is None or distance_km is None or distance_km < PROXY_MIN_KM:
            continue
        if avg_hr is None or zone3_lower is None or avg_hr < zone3_lower:
            continue
        activity_id = run.get("activity_id")
        candidates.append(
            {
                "date": run_date.isoformat(),
                "source": "hr_proxy",
                "label": f"高強度ロング {distance_km:.1f}km ({avg_hr:.0f}bpm)",
                "activity_id": int(activity_id) if activity_id is not None else None,
            }
        )

    by_date: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        existing = by_date.get(candidate["date"])
        if existing is None or (
            _SOURCE_RANK[candidate["source"]] < _SOURCE_RANK[existing["source"]]
        ):
            by_date[candidate["date"]] = candidate

    return [by_date[key] for key in sorted(by_date)]


def empty_post_event_window(
    date: str | None = None,
    reason_ja: str = "活動データがないため、レース後の保護期間を判定できません。",
) -> dict[str, Any]:
    """Return the payload shape used when there is nothing at all to judge.

    Args:
        date: Reference day (``YYYY-MM-DD``), or ``None`` when even that could
            not be resolved.
        reason_ja: One-line Japanese rationale.

    Returns:
        A :func:`compute_post_event_window`-shaped dict whose verdict is
        ``insufficient_data``.
    """
    return {
        "date": date,
        "last_event": None,
        "days_since_event": None,
        "in_window": False,
        "ceiling_km": None,
        "longest_since_km": None,
        "longest_since_activity_id": None,
        "overshoot_pct": None,
        "verdict": "insufficient_data",
        "reason_ja": reason_ja,
    }


def _reason_ja(
    verdict: str,
    last_event: dict[str, Any] | None,
    days_since_event: int | None,
    in_window: bool,
    ceiling_km: float | None,
    longest_since_km: float | None,
    overshoot_pct: float | None,
) -> str:
    """Compose the one-line Japanese rationale for the verdict."""
    if verdict == "no_event":
        return (
            "レースなどの大きな刺激が登録されていないため、"
            "保護期間の制限はかかっていません。"
        )

    label = (last_event or {}).get("label", "大きな刺激")

    if verdict == "insufficient_data":
        return (
            f"{label}から{days_since_event}日目で保護期間中ですが、"
            f"レース前{PRE_EVENT_LOOKBACK_DAYS}日間に比較できるロングがなく、"
            "上限距離を判定できません。"
        )

    if not in_window:
        return (
            f"{label}から{days_since_event}日が経過し、"
            f"{WINDOW_DAYS}日間の保護期間は終了しています。"
        )

    if verdict == "green":
        if longest_since_km is None or ceiling_km is None:
            return (
                f"{label}から{days_since_event}日目の保護期間中で、"
                "まだロングを走っていません。"
            )
        return (
            f"{label}から{days_since_event}日目の保護期間中ですが、"
            f"その後の最長走{longest_since_km:.1f}kmはレース前の上限"
            f"{ceiling_km:.1f}km以内に収まっています。"
        )

    ceiling = ceiling_km if ceiling_km is not None else 0.0
    longest = longest_since_km if longest_since_km is not None else 0.0
    overshoot = overshoot_pct if overshoot_pct is not None else 0.0
    if verdict == "yellow":
        return (
            f"{label}から{days_since_event}日目の保護期間中に"
            f"{longest:.1f}kmを走り、レース前の上限{ceiling:.1f}kmを"
            f"{overshoot:.1f}%超えています。次のロングは上限以内に戻してください。"
        )
    return (
        f"{label}から{days_since_event}日目の保護期間中に"
        f"{longest:.1f}kmを走り、レース前の上限{ceiling:.1f}kmを"
        f"{overshoot:.1f}%超過しています。故障につながりやすい形なので、"
        "次のロングは上限以下まで落としてください。"
    )


def compute_post_event_window(
    events: list[dict[str, Any]],
    runs_since: list[dict[str, Any]],
    pre_event_longest_km: float | None,
    date: str,
) -> dict[str, Any]:
    """Judge the protection window as of ``date``.

    Args:
        events: Events from :func:`resolve_big_events`. Events dated after
            ``date`` are ignored; the latest remaining one is the reference.
        runs_since: Activities with ``activity_id`` / ``activity_date`` /
            ``distance_km``. Runs on or before the event day and runs after
            ``date`` are filtered out, so an unfiltered list is safe to pass.
        pre_event_longest_km: Longest run in the
            :data:`PRE_EVENT_LOOKBACK_DAYS` days before the event, or ``None``
            when it cannot be computed.
        date: Reference day (``YYYY-MM-DD``).

    Returns:
        ``{"date", "last_event", "days_since_event", "in_window", "ceiling_km",
        "longest_since_km", "longest_since_activity_id", "overshoot_pct",
        "verdict", "reason_ja"}`` where ``verdict`` is one of ``green`` /
        ``yellow`` / ``red`` / ``no_event`` / ``insufficient_data``.
    """
    reference = _as_date(date)
    if reference is None:
        return empty_post_event_window(
            date, "基準日を解釈できず、保護期間を判定できません。"
        )

    past_events = []
    for event in events:
        event_day = _as_date(event.get("date"))
        if event_day is not None and event_day <= reference:
            past_events.append(event)

    if not past_events:
        return {
            "date": reference.isoformat(),
            "last_event": None,
            "days_since_event": None,
            "in_window": False,
            "ceiling_km": None,
            "longest_since_km": None,
            "longest_since_activity_id": None,
            "overshoot_pct": None,
            "verdict": "no_event",
            "reason_ja": _reason_ja("no_event", None, None, False, None, None, None),
        }

    last_event = max(past_events, key=lambda e: str(e["date"]))
    event_date = _as_date(last_event["date"])
    assert event_date is not None  # every past event parsed above
    days_since_event = (reference - event_date).days
    in_window = 0 < days_since_event <= WINDOW_DAYS

    ceiling_km = _as_float(pre_event_longest_km)

    longest_since_km: float | None = None
    longest_since_activity_id: int | None = None
    for run in runs_since:
        run_date = _as_date(run.get("activity_date"))
        distance_km = _as_float(run.get("distance_km"))
        if run_date is None or distance_km is None:
            continue
        if not (event_date < run_date <= reference):
            continue
        if longest_since_km is None or distance_km > longest_since_km:
            longest_since_km = distance_km
            raw_id = run.get("activity_id")
            longest_since_activity_id = int(raw_id) if raw_id is not None else None

    overshoot_pct: float | None = None
    if ceiling_km is not None and ceiling_km > 0 and longest_since_km is not None:
        overshoot_pct = round((longest_since_km / ceiling_km - 1.0) * 100.0, 1)

    if not in_window:
        verdict = "green"
    elif ceiling_km is None or ceiling_km <= 0:
        verdict = "insufficient_data"
    elif longest_since_km is None or longest_since_km <= ceiling_km:
        verdict = "green"
    elif longest_since_km > ceiling_km * (1.0 + RED_OVERSHOOT_PCT / 100.0):
        verdict = "red"
    else:
        verdict = "yellow"

    return {
        "date": reference.isoformat(),
        "last_event": last_event,
        "days_since_event": days_since_event,
        "in_window": in_window,
        "ceiling_km": round(ceiling_km, 2) if ceiling_km is not None else None,
        "longest_since_km": (
            round(longest_since_km, 2) if longest_since_km is not None else None
        ),
        "longest_since_activity_id": longest_since_activity_id,
        "overshoot_pct": overshoot_pct,
        "verdict": verdict,
        "reason_ja": _reason_ja(
            verdict,
            last_event,
            days_since_event,
            in_window,
            ceiling_km,
            longest_since_km,
            overshoot_pct,
        ),
    }
