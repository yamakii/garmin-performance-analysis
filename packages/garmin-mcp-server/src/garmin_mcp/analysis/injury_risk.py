"""Composite injury-risk score (pure functions, no I/O).

Fuses four already-available deterministic signals into a single 0-100 injury
risk score with a ``low`` / ``moderate`` / ``high`` band and a per-factor
breakdown:

- **ACWR** (acute:chronic workload ratio) -- the dominant driver (weight 0.40).
- **Durability trend** -- worsening long-run cardiac decoupling (weight 0.25).
- **Wellness deviation** -- HRV / readiness / RHR outside the personal band
  (weight 0.20).
- **Form anomalies** -- an acute:chronic ratio of *material* form-anomaly event
  rates: recent 14-day deduped-event rate over the personal 90-day baseline
  rate (weight 0.15). A raw z>3 spike count saturated the factor at all times
  (~0.22% of samples deviate by chance, so tens of "anomalies" appear even on
  healthy form); the ratio form only adds risk when recent form movement
  *exceeds* the athlete's own baseline (#807).

This is a *descriptive* live-computed indicator (same principle as the weekly
"today's caution" card): no LLM, no backfill. Missing inputs are dropped from
the weighting and the remaining factors are renormalized, so the score stays
meaningful when a signal is unavailable. When *every* input is missing the
function returns ``{"insufficient_data": True}`` rather than a misleading zero.

ACWR contribution is piecewise-linear: the 0.8-1.3 band is the safe zone (0
risk), 1.5 maps to 50%, and >=1.8 saturates at 100%.
"""

from __future__ import annotations

from typing import Any

# Relative weights of each factor before renormalization over available inputs.
WEIGHTS: dict[str, float] = {
    "acwr": 0.40,
    "durability": 0.25,
    "wellness": 0.20,
    "form_anomaly": 0.15,
}

# ACWR piecewise-linear anchors (ratio -> risk fraction). Below/at 1.3 is the
# safe zone (0); 1.5 is half risk; 1.8+ saturates at full risk.
_ACWR_SAFE_MAX = 1.3
_ACWR_MID = 1.5
_ACWR_HIGH = 1.8

# Form-anomaly signal selection + acute:chronic ratio anchors (#807).
# An anomaly counts toward the material-event rate only when it is *material*
# (``probable_cause`` other than ``"isolated"``) and severe (``|z| >
# _FORM_SEVERITY_MIN_Z``, matching the detector's medium/high strata). Adjacent
# material anomalies within ``_FORM_EVENT_DEDUP_WINDOW_S`` seconds collapse into
# a single event (one stop/transition, not 2-6 per-metric duplicates). The
# recent:baseline event-rate ratio is piecewise-linear: <=1.2 safe (0 risk),
# >=2.0 saturates (full risk). Baselines below ``_FORM_BASELINE_MIN_RATE``
# events/hour are too sparse to compare against, so the factor is dropped.
_FORM_SEVERITY_MIN_Z = 3.5
_FORM_EVENT_DEDUP_WINDOW_S = 2
_FORM_RATIO_SAFE = 1.2
_FORM_RATIO_HIGH = 2.0
_FORM_BASELINE_MIN_RATE = 0.2

# Band thresholds on the 0-100 score. ``score < 30`` low, ``30 <= score <= 60``
# moderate, ``score > 60`` high (boundaries: 30 and 60 are moderate).
_BAND_LOW_MAX = 30
_BAND_MODERATE_MAX = 60


def classify_band(score: float) -> str:
    """Map a 0-100 injury-risk ``score`` to its band.

    ``score < 30`` -> ``"low"``; ``30 <= score <= 60`` -> ``"moderate"``;
    ``score > 60`` -> ``"high"`` (30 and 60 are inclusive of ``moderate``).
    """
    if score < _BAND_LOW_MAX:
        return "low"
    if score <= _BAND_MODERATE_MAX:
        return "moderate"
    return "high"


def _acwr_ratio_to_risk(ratio: float) -> float:
    """Piecewise-linear ACWR ratio -> risk fraction in ``[0, 1]``."""
    if ratio <= _ACWR_SAFE_MAX:
        return 0.0
    if ratio >= _ACWR_HIGH:
        return 1.0
    if ratio <= _ACWR_MID:
        # 1.3 -> 0.0, 1.5 -> 0.5
        return (ratio - _ACWR_SAFE_MAX) / (_ACWR_MID - _ACWR_SAFE_MAX) * 0.5
    # 1.5 -> 0.5, 1.8 -> 1.0
    return 0.5 + (ratio - _ACWR_MID) / (_ACWR_HIGH - _ACWR_MID) * 0.5


def _acwr_factor(acwr: dict[str, Any] | None) -> tuple[float | None, str]:
    """Risk fraction + Japanese detail for the ACWR factor (None => unavailable)."""
    if acwr is None:
        return None, ""
    ratio = acwr.get("acwr")
    if ratio is None:
        return None, ""
    return _acwr_ratio_to_risk(ratio), f"ACWR {ratio:.2f}（安全域 0.8-1.3）"


def _durability_factor(
    durability_trend: dict[str, Any] | None,
) -> tuple[float | None, str]:
    """Risk fraction + detail for the durability trend (None => unavailable)."""
    if durability_trend is None:
        return None, ""
    trend = durability_trend.get("trend") or {}
    direction = trend.get("direction")
    if direction is None or direction == "insufficient_data":
        return None, ""
    risk = 1.0 if direction == "worsening" else 0.0
    return risk, f"耐久性トレンド: {direction}"


def _wellness_factor(
    wellness_deviation: dict[str, Any] | None,
) -> tuple[float | None, str]:
    """Risk fraction + detail for wellness deviation (None => unavailable).

    Uses the HRV / readiness / RHR baseline blocks: a metric counts toward risk
    when its band is usable (not ``insufficient``) and it sits in an
    ``adverse`` deviation. The fraction is adverse metrics over usable metrics;
    when no band is usable the factor is unavailable.
    """
    if wellness_deviation is None:
        return None, ""
    usable = [
        block
        for key in ("hrv", "readiness", "rhr")
        if isinstance(block := wellness_deviation.get(key), dict)
        and block.get("flag") != "insufficient"
    ]
    if not usable:
        return None, ""
    adverse = sum(1 for block in usable if block.get("adverse"))
    return (
        adverse / len(usable),
        f"起床時コンディション: {adverse}/{len(usable)} 指標逸脱",
    )


def is_material_severe(anomaly: dict[str, Any]) -> bool:
    """Whether a form anomaly is a *material, severe* signal (not noise).

    Material means an identifiable cause (``probable_cause`` other than
    ``"isolated"`` -- elevation / pace / fatigue). Severe means its z-score
    magnitude exceeds ``_FORM_SEVERITY_MIN_Z`` (the detector's medium/high
    strata). Isolated noise and low-severity (``|z| <= 3.5``) spikes -- which
    occur at the ~0.22% chance base rate even on healthy form -- are excluded.
    """
    if anomaly.get("probable_cause") == "isolated":
        return False
    z = anomaly.get("z_score")
    if z is None:
        return False
    return abs(float(z)) > _FORM_SEVERITY_MIN_Z


def count_material_events(anomalies: list[dict[str, Any]]) -> int:
    """Count deduped material-severe form-anomaly *events* in one activity.

    Filters to material-severe anomalies (``is_material_severe``), then collapses
    anomalies whose timestamps are within ``_FORM_EVENT_DEDUP_WINDOW_S`` seconds
    of the previous one into a single event. A single stop/transition that trips
    2-6 per-metric detections across GCT/VO/VR counts once, not many times.
    """
    timestamps = sorted(a["timestamp"] for a in anomalies if is_material_severe(a))
    if not timestamps:
        return 0
    events = 1
    prev = timestamps[0]
    for ts in timestamps[1:]:
        if ts - prev > _FORM_EVENT_DEDUP_WINDOW_S:
            events += 1
        prev = ts
    return events


def _form_ratio_to_risk(ratio: float) -> float:
    """Piecewise-linear form event-rate ratio -> risk fraction in ``[0, 1]``.

    ``ratio <= 1.2`` -> 0 (recent form is within the personal baseline band);
    ``ratio >= 2.0`` -> 1.0; linear in between (e.g. 1.6 -> 0.5).
    """
    if ratio <= _FORM_RATIO_SAFE:
        return 0.0
    if ratio >= _FORM_RATIO_HIGH:
        return 1.0
    return (ratio - _FORM_RATIO_SAFE) / (_FORM_RATIO_HIGH - _FORM_RATIO_SAFE)


def _form_factor(signal: dict[str, Any] | None) -> tuple[float | None, str]:
    """Risk fraction + detail for the form-anomaly factor (None => unavailable).

    ``signal`` is the ``_form_anomaly_signal`` output with ``recent_rate`` /
    ``baseline_rate`` (material-event rates, events/hour). The factor is dropped
    (``None``) when the signal is missing, its rates are absent, or the personal
    baseline rate is below ``_FORM_BASELINE_MIN_RATE`` (too little baseline
    running to compare against -- avoids both false alarms and false zeros).
    """
    if signal is None:
        return None, ""
    recent_rate = signal.get("recent_rate")
    baseline_rate = signal.get("baseline_rate")
    if recent_rate is None or baseline_rate is None:
        return None, ""
    if baseline_rate < _FORM_BASELINE_MIN_RATE:
        return None, ""
    ratio = recent_rate / baseline_rate
    risk = _form_ratio_to_risk(ratio)
    detail = (
        f"フォーム異常イベント 直近 {recent_rate:.2f}/h vs "
        f"基準 {baseline_rate:.2f}/h（比 {ratio:.2f}、安全域 ≤1.2）"
    )
    return risk, detail


def compute_injury_risk(
    acwr: dict[str, Any] | None,
    durability_trend: dict[str, Any] | None,
    wellness_deviation: dict[str, Any] | None,
    form_anomaly: dict[str, Any] | None,
) -> dict[str, Any]:
    """Fuse ACWR / durability / wellness / form signals into an injury-risk score.

    Args:
        acwr: ``TrainingLoadReader.get_acwr`` output (uses the ``acwr`` ratio).
            ``None`` (or a null ratio) drops the factor.
        durability_trend: ``DurabilityReader.get_durability_trend`` output (uses
            ``trend.direction``). ``None`` / ``insufficient_data`` drops it.
        wellness_deviation: ``get_wellness_baseline_deviation`` output (uses the
            per-metric ``adverse`` / ``flag`` blocks). ``None`` / all-insufficient
            drops it.
        form_anomaly: ``_form_anomaly_signal`` output with ``recent_rate`` /
            ``baseline_rate`` (material-event rates, events/hour). ``None`` or a
            baseline rate below ``_FORM_BASELINE_MIN_RATE`` drops the factor.

    Returns:
        ``{"score": int(0-100), "band": "low"|"moderate"|"high", "factors":
        [{"name", "contribution", "detail_ja"}], "available_inputs": [...]}``.
        ``factors`` is sorted by ``contribution`` (points added to the score)
        descending and ``contribution`` values sum to ~``score``. When every
        input is missing the result is ``{"insufficient_data": True}``.
    """
    raw_factors: list[tuple[str, float | None, str]] = [
        ("acwr", *_acwr_factor(acwr)),
        ("durability", *_durability_factor(durability_trend)),
        ("wellness", *_wellness_factor(wellness_deviation)),
        ("form_anomaly", *_form_factor(form_anomaly)),
    ]
    available = [
        (name, risk, detail) for name, risk, detail in raw_factors if risk is not None
    ]
    if not available:
        return {"insufficient_data": True}

    total_weight = sum(WEIGHTS[name] for name, _, _ in available)
    factors: list[dict[str, Any]] = []
    score_float = 0.0
    for name, risk, detail in available:
        contribution = (WEIGHTS[name] / total_weight) * risk * 100
        score_float += contribution
        factors.append(
            {
                "name": name,
                "contribution": round(contribution, 1),
                "detail_ja": detail,
            }
        )

    factors.sort(key=lambda f: f["contribution"], reverse=True)
    score = int(round(score_float))
    return {
        "score": score,
        "band": classify_band(score),
        "factors": factors,
        "available_inputs": [name for name, _, _ in available],
    }
