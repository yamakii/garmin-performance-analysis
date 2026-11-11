"""Phase-aware build baseline reported beside the raw ACWR (Issue #1567).

The raw ACWR chronic term (the last-28-day distance / 4) cannot tell an
intentional cutback, taper, race or recovery week from normal training, so
after every deload it reports a "spike". This module computes a second
reference instead of changing the ACWR: the **build baseline**, the mean
weekly volume of the most recent registered build weeks, plus a label for each
week inside the ACWR chronic window. The ACWR itself, its thresholds and its
status are left alone because the 1.3 threshold assumes the raw rolling chronic.

A week's kind comes from the training block ledger only (no symptom reading):
an illness week is excluded through the ``cutback`` ladder kind registered for
it.

Pure functions only -- the reader supplies the weekly loads and the blocks.
"""

from __future__ import annotations

from typing import Any

#: Ladder kinds that count as a build week inside a ``build``-phase block.
BUILD_WEEK_KINDS = frozenset({"build", "hold"})

#: At most this many of the most recent build weeks feed the baseline.
MAX_BASELINE_WEEKS = 8

#: Calendar weeks reported as the composition of the ACWR chronic window.
WINDOW_WEEKS = 4

_BUILD = "build"
_UNREGISTERED = "unregistered"


def _covering_block(
    week_start: str, blocks: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Return the first block whose date range covers ``week_start``."""
    for block in blocks:
        start = str(block.get("start_date") or "")
        end = str(block.get("end_date") or "")
        if start and end and start <= week_start <= end:
            return block
    return None


def _ladder_kind(block: dict[str, Any], week_start: str) -> str | None:
    """Return the lower-cased ladder kind registered for ``week_start``."""
    for step in block.get("long_run_ladder") or []:
        if not isinstance(step, dict):
            continue
        if str(step.get("week_start") or "") != week_start:
            continue
        kind = str(step.get("kind") or "").strip().lower()
        return kind or None
    return None


def classify_week(week_start: str, blocks: list[dict[str, Any]]) -> str:
    """Label one calendar week from the training block ledger.

    ``"build"`` when the covering block's phase is ``build`` and that week's
    ladder kind is build/hold (or the block has no step for the week).
    Otherwise the ladder kind (``cutback``, ``taper``, ``race``, ...), the
    block phase when the week's step is build/hold or absent, or
    ``"unregistered"`` when no block covers the week.

    Args:
        week_start: The week's start day (``YYYY-MM-DD``).
        blocks: ``PlanReader.get_training_blocks()`` rows.

    Returns:
        The week kind.
    """
    block = _covering_block(week_start, blocks)
    if block is None:
        return _UNREGISTERED
    phase = str(block.get("phase") or "").strip().lower() or _UNREGISTERED
    kind = _ladder_kind(block, week_start)
    if kind is None or kind in BUILD_WEEK_KINDS:
        return _BUILD if phase == _BUILD else phase
    return kind


def compute_build_baseline(
    weekly_loads: list[dict[str, Any]],
    blocks: list[dict[str, Any]],
    acute_7d_km: float,
    *,
    lookback_weeks: int = 26,
    min_weeks: int = 2,
) -> dict[str, Any]:
    """Mean weekly volume of the most recent registered build weeks.

    Args:
        weekly_loads: ``[{"week_start": "YYYY-MM-DD", "load_km": float}]``
            ordered oldest -> newest (completed weeks).
        blocks: ``PlanReader.get_training_blocks()`` rows.
        acute_7d_km: The ACWR acute load (last-7-day km).
        lookback_weeks: Only the newest this-many weeks are considered.
        min_weeks: Fewer build weeks than this -> ``insufficient``.

    Returns:
        ``{"status": "ok" | "insufficient" | "no_blocks", "weekly_km",
        "weeks_used", "ratio", "note_ja"}``. ``weekly_km`` is the mean of at
        most :data:`MAX_BASELINE_WEEKS` build weeks, ``ratio`` is
        ``acute_7d_km / weekly_km``; ``note_ja`` is set when status != ok.
    """
    if not blocks:
        return {
            "status": "no_blocks",
            "weekly_km": None,
            "weeks_used": [],
            "ratio": None,
            "note_ja": (
                "トレーニングブロックが登録されていないため、ビルド週の"
                "基準量は出せません。ACWR の値だけで判断してください。"
            ),
        }

    recent = weekly_loads[-lookback_weeks:] if lookback_weeks > 0 else []
    build_weeks = [
        week
        for week in recent
        if classify_week(str(week["week_start"]), blocks) == _BUILD
    ]
    used = build_weeks[-MAX_BASELINE_WEEKS:]
    weeks_used = [str(week["week_start"]) for week in used]
    total = sum(float(week.get("load_km") or 0.0) for week in used)

    if len(used) < max(min_weeks, 1) or total <= 0:
        return {
            "status": "insufficient",
            "weekly_km": None,
            "weeks_used": weeks_used,
            "ratio": None,
            "note_ja": (
                f"直近 {lookback_weeks} 週で登録済みのビルド週が "
                f"{len(used)} 週しかなく（{min_weeks} 週以上が必要）、"
                "ビルド週の基準量は出せません。"
            ),
        }

    weekly_km = total / len(used)
    return {
        "status": "ok",
        "weekly_km": round(weekly_km, 2),
        "weeks_used": weeks_used,
        "ratio": round(acute_7d_km / weekly_km, 2),
        "note_ja": None,
    }


def window_composition(
    weekly_loads: list[dict[str, Any]], blocks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Label the calendar weeks inside the ACWR chronic window.

    Args:
        weekly_loads: ``[{"week_start", "load_km"}]`` ordered oldest -> newest;
            the newest entry is the (possibly partial) current week.
        blocks: ``PlanReader.get_training_blocks()`` rows.

    Returns:
        ``[{"week_start", "load_km", "kind"}]`` for the newest
        :data:`WINDOW_WEEKS` weeks, oldest -> newest.
    """
    return [
        {
            "week_start": str(week["week_start"]),
            "load_km": week.get("load_km"),
            "kind": classify_week(str(week["week_start"]), blocks),
        }
        for week in weekly_loads[-WINDOW_WEEKS:]
    ]
