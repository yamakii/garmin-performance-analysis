"""Deterministic long-run progression gate (extend / repeat / shorten).

The athlete profile states the rule in prose: *the long run is only extended
when the previous long run did not break the legs down* — compare like-for-like
practice long runs and, if the second half shows GCT +10 ms or worse, cadence
down 5 spm or worse, or a clearly larger pace fade **than the reference run**,
repeat the same distance instead of extending. Applying that by hand every week
is error-prone, so this module turns it into arithmetic over two
``get_activity_durability`` results (the current long run and a comparable
earlier one, picked by ``DurabilityReader.find_reference_long_run``).

Verdict rules:

- **red** -- a trigger is exceeded *and* the run is worse than the reference by
  that metric's margin (or there is no reference to exonerate it).
- **yellow** -- a trigger is exceeded but the run is not clearly worse than the
  reference; or nothing is triggered yet the read is unreliable (no reference
  **and** the heat contaminates decoupling).
- **green** -- no trigger exceeded.
- **insufficient_data** -- the current run has none of the three half-split
  metrics (older device / missing time series).

The recommendation follows the verdict: ``green -> extend``,
``yellow -> repeat``, ``red -> shorten`` (``insufficient_data -> repeat``: with
nothing to judge, holding the distance is the conservative move).

Decoupling in 30 °C+ heat is thermal drift rather than a durability verdict
(see the decoupling-contamination lesson), so ``decoupling_contaminated``
flags the current run's temperature for the consumer rather than silently
loosening the gate.
"""

from __future__ import annotations

from typing import Any, Protocol

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
) -> str:
    """Compose the one-line Japanese rationale for the verdict."""
    labels = "・".join(_METRIC_LABEL_JA[t["metric"]] for t in triggers)

    if verdict == "insufficient_data":
        return "後半区間の接地時間・ケイデンス・ペースが取得できず、脚の崩れを判定できません。"

    if verdict == "red":
        if reference_activity_id is None:
            return (
                f"{labels}が基準を超えて悪化しています。"
                "比較できる同条件の練習ロングがないため、次のロングは距離を落とすのが安全です。"
            )
        return (
            f"{labels}が基準を超え、前回の同条件ロング（{reference_activity_id}）より"
            "明確に悪化しています。次のロングは距離を落としてください。"
        )

    if verdict == "yellow":
        if triggers:
            return (
                f"{labels}は基準を超えていますが、前回の同条件ロング"
                f"（{reference_activity_id}）より明確に悪化してはいません。"
                "次は同距離で反復してください。"
            )
        heat = f"気温{temperature_c:.1f}℃" if temperature_c is not None else "高温"
        return (
            f"後半の崩れは基準内ですが、{heat}で心拍の乖離が当てにならず、"
            "比較できる練習ロングもありません。次は同距離で反復してください。"
        )

    if decoupling_contaminated:
        return (
            "後半の脚の崩れは基準内です（高温のため心拍の乖離は参考値）。"
            "次のロングは延長できます。"
        )
    return "後半の脚の崩れは基準内です。次のロングは延長できます。"


def compute_long_run_progression_gate(
    current: dict[str, Any] | None,
    reference: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Judge whether the next long run may be extended.

    Args:
        current: The current long run's ``get_activity_durability`` result
            (reads ``gct_fade_ms`` / ``cadence_fade_spm`` / ``pace_fade_pct``
            and ``temperature_c``). ``None`` is treated as no data.
        reference: A comparable earlier long run's durability result, or
            ``None`` when no like-for-like run exists in the lookback window.

    Returns:
        ``{"verdict": "green"|"yellow"|"red"|"insufficient_data",
        "triggers": [{"metric", "current", "reference", "threshold",
        "worse_than_reference"}], "decoupling_contaminated": bool,
        "reference_activity_id": int|None,
        "recommendation": "extend"|"repeat"|"shorten", "reason_ja": str}``.

        ``triggers`` holds only the metrics that exceeded their threshold (an
        empty list on ``green``), each carrying the reference value it was
        compared against.
    """
    current = current or {}
    reference_metrics = reference or {}

    temperature_c = _as_float(current.get("temperature_c"))
    decoupling_contaminated = (
        temperature_c is not None and temperature_c >= DECOUPLING_CONTAMINATION_TEMP_C
    )

    raw_reference_id = reference_metrics.get("activity_id")
    reference_activity_id = (
        int(raw_reference_id) if raw_reference_id is not None else None
    )

    values = {metric: _as_float(current.get(metric)) for metric in _TRIGGERS}

    if all(value is None for value in values.values()):
        verdict = "insufficient_data"
        triggers: list[dict[str, Any]] = []
    else:
        triggers = []
        for metric, threshold in _TRIGGERS.items():
            value = values[metric]
            if value is None or not _exceeds(value, threshold):
                continue
            reference_value = _as_float(reference_metrics.get(metric))
            triggers.append(
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

        if not triggers:
            verdict = (
                "yellow" if reference is None and decoupling_contaminated else "green"
            )
        elif reference is None or any(t["worse_than_reference"] for t in triggers):
            verdict = "red"
        else:
            verdict = "yellow"

    return {
        "verdict": verdict,
        "triggers": triggers,
        "decoupling_contaminated": decoupling_contaminated,
        "reference_activity_id": reference_activity_id,
        "recommendation": _RECOMMENDATION[verdict],
        "reason_ja": _reason_ja(
            verdict,
            triggers,
            reference_activity_id,
            decoupling_contaminated,
            temperature_c,
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
        source: A reader exposing ``get_activity_durability`` and
            ``find_reference_long_run``.
        activity_id: The long run being judged.

    Returns:
        ``{"activity_id", "current": dict|None, "reference": dict|None,
        **compute_long_run_progression_gate(...)}``.
    """
    current = source.get_activity_durability(activity_id)
    reference = source.find_reference_long_run(activity_id)
    return {
        "activity_id": activity_id,
        "current": current,
        "reference": reference,
        **compute_long_run_progression_gate(current, reference),
    }
