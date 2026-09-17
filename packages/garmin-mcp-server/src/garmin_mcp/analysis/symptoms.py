"""Deterministic symptom rule: when does a logged niggle change the plan?

The symptom log (#1220) only records what the athlete felt; on its own it never
changes a decision. This module is the rule that turns those rows into a flag,
so the same arithmetic backs the daily check-in question, the Thursday
conditional-6th-day gate, the weekly review and the ``injury_risk`` factor --
no LLM judgement, no per-conversation re-interpretation.

Two patterns flag a region:

- **consecutive** -- the two most recent reports for one ``(body_region,
  side)`` within :data:`CONSECUTIVE_WINDOW_DAYS` days are both at or above
  :data:`CONSECUTIVE_SEVERITY`. Pain that *comes and goes* is the precursor
  worth catching, so a later severity-0 report does not clear the flag by
  itself: it clears once the two most recent reports are both below the
  threshold.
- **acute** -- any report within :data:`ACUTE_WINDOW_DAYS` days at or above
  :data:`ACUTE_SEVERITY`. One report of pain that alters the run is enough.

Reports are per *date*: two rows for the same region on the same day count once
(at their maximum severity), so logging a niggle twice in a day never
manufactures a "consecutive" pattern.

A severity-0 row is not noise -- it is the record that the question was asked
and the answer was clear, which is what lets a gate tell "no pain" from "never
asked" (``asked_today`` / ``clear_today``).
"""

from __future__ import annotations

from datetime import date as date_cls
from typing import Any

#: Severity (0-10) at which two consecutive reports flag a region.
CONSECUTIVE_SEVERITY = 3

#: Lookback for the consecutive rule (and for the whole evaluation window).
CONSECUTIVE_WINDOW_DAYS = 14

#: Severity at which a single report flags a region on its own.
ACUTE_SEVERITY = 5

#: Lookback for the acute rule (days).
ACUTE_WINDOW_DAYS = 7

#: Lookback for a "recently cleared" read: a severity-0 report this recent
#: still counts as an explicit all-clear when today's question was not asked.
CLEAR_WINDOW_DAYS = 3

#: Japanese labels for the ``body_region`` enum of ``save_symptom``.
_REGION_LABELS_JA: dict[str, str] = {
    "foot": "足部",
    "ankle": "足首",
    "achilles": "アキレス腱",
    "calf": "ふくらはぎ",
    "shin": "すね",
    "knee": "膝",
    "hamstring": "ハムストリング",
    "quad": "大腿前面",
    "hip": "股関節",
    "glute": "臀部",
    "groin": "鼠径部",
    "lower_back": "腰",
    "other": "その他",
}

#: Japanese labels for the ``side`` enum.
_SIDE_LABELS_JA: dict[str, str] = {"left": "左", "right": "右", "both": "両"}


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


def _as_severity(value: Any) -> int | None:
    """Coerce a severity to ``int``, or ``None`` when absent / non-numeric."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _region_label(body_region: str, side: str | None) -> str:
    """Japanese label for a region key, e.g. ``("calf", "right")`` -> 右ふくらはぎ."""
    region = _REGION_LABELS_JA.get(body_region, body_region)
    return f"{_SIDE_LABELS_JA.get(side or '', '')}{region}"


def _format_report(report: dict[str, Any]) -> str:
    """Render one report as ``9/15 4/10`` (month/day + severity out of 10)."""
    day = _as_date(report["date"])
    stamp = f"{day.month}/{day.day}" if day is not None else str(report["date"])
    return f"{stamp} {report['severity']}/10"


def _collect_reports(
    rows: list[dict[str, Any]], ref: date_cls
) -> dict[tuple[str, str | None], list[dict[str, Any]]]:
    """Group rows into per-region, per-date reports inside the 14-day window.

    Rows outside ``[ref - CONSECUTIVE_WINDOW_DAYS, ref]`` (or with an unusable
    date / severity) are dropped, and same-day rows for one region collapse to
    their maximum severity so a double log cannot fake a consecutive pattern.
    """
    window_start = ref.toordinal() - CONSECUTIVE_WINDOW_DAYS
    by_region: dict[tuple[str, str | None], dict[date_cls, int]] = {}
    for row in rows:
        day = _as_date(row.get("date"))
        severity = _as_severity(row.get("severity"))
        if day is None or severity is None:
            continue
        if not (window_start <= day.toordinal() <= ref.toordinal()):
            continue
        side = row.get("side")
        key = (str(row.get("body_region") or "other"), str(side) if side else None)
        per_date = by_region.setdefault(key, {})
        per_date[day] = max(per_date.get(day, severity), severity)

    return {
        key: [
            {"date": day.isoformat(), "severity": severity}
            for day, severity in sorted(per_date.items())
        ]
        for key, per_date in by_region.items()
    }


def _evaluate_region(
    key: tuple[str, str | None], reports: list[dict[str, Any]], ref: date_cls
) -> tuple[dict[str, Any], str] | None:
    """Apply both rules to one region; return ``(flag_entry, reason)`` or None."""
    body_region, side = key
    label = _region_label(body_region, side)
    latest = reports[-1]

    acute_cutoff = ref.toordinal() - ACUTE_WINDOW_DAYS
    acute = [
        report
        for report in reports
        if report["severity"] >= ACUTE_SEVERITY
        and (day := _as_date(report["date"])) is not None
        and day.toordinal() >= acute_cutoff
    ]
    if acute:
        rule = "acute"
        reason = (
            f"{label}: {_format_report(acute[-1])}"
            f"（{ACUTE_WINDOW_DAYS}日以内に{ACUTE_SEVERITY}以上）"
        )
    elif (
        len(reports) >= 2
        and reports[-1]["severity"] >= CONSECUTIVE_SEVERITY
        and reports[-2]["severity"] >= CONSECUTIVE_SEVERITY
    ):
        rule = "consecutive"
        reason = (
            f"{label}: {_format_report(reports[-2])} → {_format_report(reports[-1])}"
            f"（2回連続で{CONSECUTIVE_SEVERITY}以上）"
        )
    else:
        return None

    return (
        {
            "body_region": body_region,
            "side": side,
            "rule": rule,
            "latest_severity": latest["severity"],
            "latest_date": latest["date"],
            "reports": reports,
        },
        reason,
    )


def evaluate_symptom_rule(rows: list[dict[str, Any]], date: str) -> dict[str, Any]:
    """Decide whether the logged symptoms should change the plan as of ``date``.

    Args:
        rows: ``athlete_symptoms`` rows covering ``[date - 14, date]`` (the
            reader's window), each with ``date``, ``body_region``, ``side`` and
            ``severity``. Order does not matter; rows outside the window or
            missing a usable date/severity are ignored.
        date: Reference day (``YYYY-MM-DD``) the rule is evaluated for.

    Returns:
        ``{"date", "flag", "flagged_regions", "asked_today", "clear_today",
        "recently_cleared", "days_since_last_report", "reason_ja"}`` where

        - ``flag`` is True when any region matched a rule;
        - ``flagged_regions`` lists ``{body_region, side, rule, latest_severity,
          latest_date, reports}`` (``rule`` is ``"acute"`` or ``"consecutive"``;
          acute wins when a region matches both), ordered by region key;
        - ``asked_today`` is True when any row is dated ``date`` (the question
          was asked), ``clear_today`` when such a row has severity 0 and
          nothing is flagged, and ``recently_cleared`` when that all-clear is
          within :data:`CLEAR_WINDOW_DAYS` days instead of today;
        - ``days_since_last_report`` is the age of the most recent report in
          the window (0 = today, ``None`` when the window is empty);
        - ``reason_ja`` always explains the verdict, including "no reports".
    """
    ref = _as_date(date)
    if ref is None:
        raise ValueError(f"invalid date: {date!r}")

    by_region = _collect_reports(rows, ref)

    flagged_regions: list[dict[str, Any]] = []
    reasons: list[str] = []
    for key in sorted(by_region, key=lambda k: (k[0], k[1] or "")):
        evaluated = _evaluate_region(key, by_region[key], ref)
        if evaluated is not None:
            entry, reason = evaluated
            flagged_regions.append(entry)
            reasons.append(reason)

    all_reports = [report for reports in by_region.values() for report in reports]
    latest_day = max(
        (
            day
            for report in all_reports
            if (day := _as_date(report["date"])) is not None
        ),
        default=None,
    )
    days_since_last_report = (
        None if latest_day is None else (ref.toordinal() - latest_day.toordinal())
    )

    asked_today = any(report["date"] == ref.isoformat() for report in all_reports)
    flag = bool(flagged_regions)
    clear_today = (
        not flag
        and asked_today
        and any(
            report["date"] == ref.isoformat() and report["severity"] == 0
            for report in all_reports
        )
    )
    clear_cutoff = ref.toordinal() - CLEAR_WINDOW_DAYS
    recently_cleared = not flag and any(
        report["severity"] == 0
        and (day := _as_date(report["date"])) is not None
        and day.toordinal() >= clear_cutoff
        for report in all_reports
    )

    if flag:
        reason_ja = "、".join(reasons) + "→ 処方の見直しを推奨"
    elif days_since_last_report is None:
        reason_ja = f"直近{CONSECUTIVE_WINDOW_DAYS}日の症状記録なし（未確認）"
    elif clear_today:
        reason_ja = "今日の申告は痛みなし（フラグなし）"
    else:
        reason_ja = (
            f"直近{CONSECUTIVE_WINDOW_DAYS}日の報告は基準未満"
            f"（最終報告は{days_since_last_report}日前）"
        )

    return {
        "date": ref.isoformat(),
        "flag": flag,
        "flagged_regions": flagged_regions,
        "asked_today": asked_today,
        "clear_today": clear_today,
        "recently_cleared": recently_cleared,
        "days_since_last_report": days_since_last_report,
        "reason_ja": reason_ja,
    }
