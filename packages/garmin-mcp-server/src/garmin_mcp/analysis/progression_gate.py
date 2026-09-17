"""Deterministic long-run progression gate (extend / repeat / shorten).

The athlete profile states the rule in prose: *the long run is only extended
when the previous long run did not break the legs down* — compare like-for-like
practice long runs and, if the second half shows GCT +10 ms or worse, cadence
down 5 spm or worse, or a clearly larger pace fade **than the reference run**,
repeat the same distance instead of extending. Applying that by hand every week
is error-prone, so this module turns it into arithmetic over two
``get_activity_durability`` results (the current long run and a comparable
earlier one, picked by ``DurabilityReader.find_reference_long_run``).

The in-run fades are not the whole story: neither 2026 injury trigger
(2025-12-14, 2025-12-29) showed a GCT / cadence / pace fade worth flagging, and
both cost the next two mornings. So a fourth trigger, ``recovery_cost``, folds
``get_long_run_recovery_cost`` (#1218) in: a long run the athlete paid for
beyond their own baseline is not extended even when every in-run metric is
clean (#1221).

Verdict rules:

- **red** -- an in-run trigger is exceeded *and* the run is worse than the
  reference by that metric's margin (or there is no reference to exonerate it,
  or the next-morning cost fired alongside it).
- **yellow** -- an in-run trigger is exceeded but the run is not clearly worse
  than the reference; or the next-morning cost fired *alone* (the legs held, so
  repeating the distance -- not shortening it -- is the answer); or nothing is
  triggered yet the read is unreliable (no reference **and** the heat
  contaminates decoupling).
- **green** -- no trigger exceeded.
- **insufficient_data** -- the current run has none of the three half-split
  metrics (older device / missing time series) and the morning cost did not
  fire either.

The recommendation follows the verdict: ``green -> extend``,
``yellow -> repeat``, ``red -> shorten`` (``insufficient_data -> repeat``: with
nothing to judge, holding the distance is the conservative move).

The ``recovery_cost`` trigger has no reference run to compare against -- its
baseline is the athlete's own trailing 14 days -- so it always reports
``worse_than_reference=True``. An unevaluated cost (``insufficient_data``: no
wellness row for d+1, or too short a baseline) never changes the verdict; it is
surfaced in ``reason_ja`` instead.

Decoupling in 30 °C+ heat is thermal drift rather than a durability verdict
(see the decoupling-contamination lesson), so ``decoupling_contaminated``
flags the current run's temperature for the consumer rather than silently
loosening the gate.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from garmin_mcp.analysis.recovery_cost import (
    MIN_CRITERIA_TO_FIRE,
    format_cost_markers,
)

logger = logging.getLogger(__name__)

#: Second-half ground-contact-time rise (ms) that counts as a broken-down leg.
GCT_TRIGGER_MS = 10.0

#: Second-half cadence change (spm) that counts as a broken-down leg (a drop).
CADENCE_TRIGGER_SPM = -5.0

#: Second-half pace fade (%) that counts as a broken-down leg.
PACE_FADE_TRIGGER_PCT = 8.0

#: How much worse than the reference run a metric must be to read as a real
#: regression rather than run-to-run noise (same sign convention as the
#: triggers: negative for cadence, which worsens downwards).
REFERENCE_MARGIN: dict[str, float] = {
    "gct_fade_ms": 5.0,
    "cadence_fade_spm": -2.0,
    "pace_fade_pct": 3.0,
}

#: At/above this temperature the decoupling read is thermal drift, not durability.
DECOUPLING_CONTAMINATION_TEMP_C = 30.0

#: Trigger threshold per metric, evaluated in this (reported) order.
_TRIGGERS: dict[str, float] = {
    "gct_fade_ms": GCT_TRIGGER_MS,
    "cadence_fade_spm": CADENCE_TRIGGER_SPM,
    "pace_fade_pct": PACE_FADE_TRIGGER_PCT,
}

#: Recommendation implied by each verdict.
_RECOMMENDATION: dict[str, str] = {
    "green": "extend",
    "yellow": "repeat",
    "red": "shorten",
    "insufficient_data": "repeat",
}

#: Japanese metric labels for ``reason_ja``.
_METRIC_LABEL_JA: dict[str, str] = {
    "gct_fade_ms": "接地時間",
    "cadence_fade_spm": "ケイデンス",
    "pace_fade_pct": "ペース低下",
}


class DurabilitySource(Protocol):
    """The reader surface :func:`build_long_run_progression_gate` needs."""

    def get_activity_durability(self, activity_id: int) -> dict[str, Any] | None:
        """Return one activity's half-split durability metrics (or None)."""
        ...

    def find_reference_long_run(self, activity_id: int) -> dict[str, Any] | None:
        """Return a comparable earlier long run's durability metrics (or None)."""
        ...

    def get_long_run_recovery_cost(self, activity_id: int) -> dict[str, Any] | None:
        """Return what the run cost over the next two mornings (or None)."""
        ...


def _as_float(value: Any) -> float | None:
    """Coerce a metric to ``float``, or ``None`` when absent / non-numeric."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _exceeds(value: float, threshold: float) -> bool:
    """Whether ``value`` reaches ``threshold`` in the metric's worsening direction.

    A negative threshold (cadence) worsens downwards, so the comparison flips.
    """
    return value <= threshold if threshold < 0 else value >= threshold


def _worse_than_reference(
    metric: str, value: float, reference_value: float | None
) -> bool:
    """Whether ``value`` is worse than the reference by the metric's margin.

    ``None`` reference (no comparable run, or the run lacks this metric) is not
    evidence of a regression, so it returns ``False``; the verdict logic handles
    a missing reference separately.
    """
    if reference_value is None:
        return False
    margin = REFERENCE_MARGIN[metric]
    delta = value - reference_value
    return delta <= margin if margin < 0 else delta >= margin


def _reason_ja(
    verdict: str,
    triggers: list[dict[str, Any]],
    reference_activity_id: int | None,
    decoupling_contaminated: bool,
    temperature_c: float | None,
    cost_markers: str | None = None,
    cost_unevaluated: bool = False,
) -> str:
    """Compose the one-line Japanese rationale for the verdict.

    ``cost_markers`` is the rendered RHR / Readiness / HRV line when the
    next-morning cost fired (``None`` otherwise), and ``cost_unevaluated``
    marks a cost that could not be judged -- it is reported but never drives
    the verdict.
    """
    in_run = [t for t in triggers if t["metric"] in _METRIC_LABEL_JA]
    labels = "・".join(_METRIC_LABEL_JA[t["metric"]] for t in in_run)
    tail = "なお翌朝コストは未評価です。" if cost_unevaluated else ""

    if verdict == "insufficient_data":
        return (
            "後半区間の接地時間・ケイデンス・ペースが取得できず、"
            f"脚の崩れを判定できません。{tail}"
        )

    if verdict == "red":
        if cost_markers is not None:
            return (
                f"{labels}が基準を超えたうえ、翌朝コスト（{cost_markers}）も"
                "出ています。次のロングは距離を落としてください。"
            )
        if reference_activity_id is None:
            return (
                f"{labels}が基準を超えて悪化しています。"
                "比較できる同条件の練習ロングがないため、"
                f"次のロングは距離を落とすのが安全です。{tail}"
            )
        return (
            f"{labels}が基準を超え、前回の同条件ロング（{reference_activity_id}）より"
            f"明確に悪化しています。次のロングは距離を落としてください。{tail}"
        )

    if verdict == "yellow":
        if cost_markers is not None:
            return (
                f"後半の脚の崩れは基準内ですが、翌朝コスト（{cost_markers}）が"
                "出ているため、次回は同距離を反復してください。"
            )
        if in_run:
            return (
                f"{labels}は基準を超えていますが、前回の同条件ロング"
                f"（{reference_activity_id}）より明確に悪化してはいません。"
                f"次は同距離で反復してください。{tail}"
            )
        heat = f"気温{temperature_c:.1f}℃" if temperature_c is not None else "高温"
        return (
            f"後半の崩れは基準内ですが、{heat}で心拍の乖離が当てにならず、"
            f"比較できる練習ロングもありません。次は同距離で反復してください。{tail}"
        )

    if decoupling_contaminated:
        return (
            "後半の脚の崩れは基準内です（高温のため心拍の乖離は参考値）。"
            f"次のロングは延長できます。{tail}"
        )
    return f"後半の脚の崩れは基準内です。次のロングは延長できます。{tail}"


def _recovery_cost_block(recovery_cost: Any) -> dict[str, Any] | None:
    """The compact next-morning-cost block carried in the gate payload.

    Args:
        recovery_cost: A ``get_long_run_recovery_cost`` result, or ``None``
            when the cost was not fetched (anything non-dict reads as absent).

    Returns:
        ``{"cost_flag", "criteria_fired", "insufficient_data", "reason_ja"}``,
        or ``None``. The full wellness detail stays in the tool that produced
        it; the gate only needs the verdict and its one-line rationale.
    """
    if not isinstance(recovery_cost, dict):
        return None
    return {
        "cost_flag": bool(recovery_cost.get("cost_flag")),
        "criteria_fired": recovery_cost.get("criteria_fired"),
        "insufficient_data": bool(recovery_cost.get("insufficient_data")),
        "reason_ja": recovery_cost.get("reason_ja"),
    }


def compute_long_run_progression_gate(
    current: dict[str, Any] | None,
    reference: dict[str, Any] | None = None,
    recovery_cost: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Judge whether the next long run may be extended.

    Args:
        current: The current long run's ``get_activity_durability`` result
            (reads ``gct_fade_ms`` / ``cadence_fade_spm`` / ``pace_fade_pct``
            and ``temperature_c``). ``None`` is treated as no data.
        reference: A comparable earlier long run's durability result, or
            ``None`` when no like-for-like run exists in the lookback window.
        recovery_cost: The ``get_long_run_recovery_cost`` result for
            ``current`` (#1218), or ``None`` when it was not fetched. A fired
            ``cost_flag`` adds the fourth trigger.

    Returns:
        ``{"verdict": "green"|"yellow"|"red"|"insufficient_data",
        "triggers": [{"metric", "current", "reference", "threshold",
        "worse_than_reference"}], "decoupling_contaminated": bool,
        "reference_activity_id": int|None,
        "recommendation": "extend"|"repeat"|"shorten",
        "recovery_cost": {"cost_flag", "criteria_fired", "insufficient_data",
        "reason_ja"}|None, "reason_ja": str}``.

        ``triggers`` holds only the metrics that exceeded their threshold (an
        empty list on ``green``), each carrying the reference value it was
        compared against. The ``recovery_cost`` trigger reports
        ``current=criteria_fired`` against ``threshold=MIN_CRITERIA_TO_FIRE``
        with ``reference=None``.
    """
    current = current or {}
    reference_metrics = reference or {}

    cost = _recovery_cost_block(recovery_cost)
    cost_fired = cost is not None and cost["cost_flag"]
    cost_markers = format_cost_markers(recovery_cost or {}) if cost_fired else None
    cost_unevaluated = cost is not None and cost["insufficient_data"]

    temperature_c = _as_float(current.get("temperature_c"))
    decoupling_contaminated = (
        temperature_c is not None and temperature_c >= DECOUPLING_CONTAMINATION_TEMP_C
    )

    raw_reference_id = reference_metrics.get("activity_id")
    reference_activity_id = (
        int(raw_reference_id) if raw_reference_id is not None else None
    )

    values = {metric: _as_float(current.get(metric)) for metric in _TRIGGERS}

    if all(value is None for value in values.values()) and not cost_fired:
        verdict = "insufficient_data"
        triggers: list[dict[str, Any]] = []
    else:
        in_run_triggers = []
        for metric, threshold in _TRIGGERS.items():
            value = values[metric]
            if value is None or not _exceeds(value, threshold):
                continue
            reference_value = _as_float(reference_metrics.get(metric))
            in_run_triggers.append(
                {
                    "metric": metric,
                    "current": value,
                    "reference": reference_value,
                    "threshold": threshold,
                    "worse_than_reference": _worse_than_reference(
                        metric, value, reference_value
                    ),
                }
            )

        triggers = list(in_run_triggers)
        if cost_fired and cost is not None:
            # The baseline is the athlete's own trailing 14 days, so no
            # reference run can exonerate a morning cost.
            triggers.append(
                {
                    "metric": "recovery_cost",
                    "current": cost["criteria_fired"],
                    "reference": None,
                    "threshold": MIN_CRITERIA_TO_FIRE,
                    "worse_than_reference": True,
                }
            )

        if not triggers:
            verdict = (
                "yellow" if reference is None and decoupling_contaminated else "green"
            )
        elif not in_run_triggers:
            # The legs held; only the next mornings were expensive -> repeat
            # the distance rather than shorten it.
            verdict = "yellow"
        elif (
            cost_fired
            or reference is None
            or any(t["worse_than_reference"] for t in in_run_triggers)
        ):
            verdict = "red"
        else:
            verdict = "yellow"

    return {
        "verdict": verdict,
        "triggers": triggers,
        "decoupling_contaminated": decoupling_contaminated,
        "reference_activity_id": reference_activity_id,
        "recommendation": _RECOMMENDATION[verdict],
        "recovery_cost": cost,
        "reason_ja": _reason_ja(
            verdict,
            triggers,
            reference_activity_id,
            decoupling_contaminated,
            temperature_c,
            cost_markers,
            cost_unevaluated,
        ),
    }


def build_long_run_progression_gate(
    source: DurabilitySource, activity_id: int
) -> dict[str, Any]:
    """Fetch both runs and compute the gate payload for ``activity_id``.

    Shared by the ``get_long_run_progression_gate`` tool and both prefetch
    bundles so the activity summary and the weekly review transcribe the same
    verdict rather than re-deriving it.

    Args:
        source: A reader exposing ``get_activity_durability``,
            ``find_reference_long_run`` and ``get_long_run_recovery_cost``.
        activity_id: The long run being judged.

    Returns:
        ``{"activity_id", "current": dict|None, "reference": dict|None,
        **compute_long_run_progression_gate(...)}``. The morning cost is
        best-effort: a reader that fails (or lacks wellness rows) leaves
        ``recovery_cost`` null and the in-run verdict stands.
    """
    current = source.get_activity_durability(activity_id)
    reference = source.find_reference_long_run(activity_id)
    try:
        recovery_cost = source.get_long_run_recovery_cost(activity_id)
    except Exception:
        logger.debug("recovery cost failed for %s; leaving it as None", activity_id)
        recovery_cost = None
    return {
        "activity_id": activity_id,
        "current": current,
        "reference": reference,
        **compute_long_run_progression_gate(current, reference, recovery_cost),
    }
