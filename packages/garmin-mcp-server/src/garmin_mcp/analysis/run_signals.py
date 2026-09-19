"""Per-run signals: today's form and cardio against the athlete's own normal (no I/O).

The single-run page and the run-note agent ask the same question of every
metric -- *was today normal for this athlete?* -- so this module answers it once
and hands both a flat list of signal dicts. It is deliberately pure: rows in,
dicts out. Reading those rows out of DuckDB belongs to the reader issue above
this one.

Seven signals are produced, all oriented so that ``z > 0`` is the unfavourable
side (see :mod:`garmin_mcp.analysis.normal_range`):

===================  ========================================  =============
signal               judged value                              bad side
===================  ========================================  =============
``gct``              pace-corrected deviation % from expected  higher
``vo``               ditto (``vo_delta_cm / vo_cm_expected``)  higher
``vr``               ditto                                     higher
``cadence``          ditto                                     lower
``power``            ``power_efficiency_score * 100``          lower
``hr_vs_expected``   ``avg_hr - expected_hr(pace, temp, day)`` higher
``hr_drift``         ``hr_drift_percentage``                   higher
===================  ========================================  =============

The four form metrics are already pace-corrected, so their baseline is every
prior run. The two cardio signals are not comparable across sessions -- an
interval session's drift says nothing about an easy run's -- so their baseline
is restricted to the **same intensity family**, which is what turned a useless
-13 %...+22 % drift band into -1 %...+10 % on the real history.

What is *not* judged is as important as what is. A metric comes back
``insufficient`` with a ``reason`` when the run has fewer than
``MIN_VALID_SPLITS`` running splits (its averages describe a warmup), when the
form model was extrapolated far beyond its trained speed range (the caller sets
``{metric}_extrapolated``, see ``normal_range.EXTRAPOLATION_NOT_JUDGED``), when
the value is missing, when fewer than ``MIN_BASELINE_RUNS`` prior runs exist, or
-- for HR drift -- when the run was hot enough
(``DECOUPLING_CONTAMINATION_TEMP_C``) that the drift is thermal, not durability.
Silence beats a confident number built on three runs.

``normal_low`` / ``normal_high`` come back in the metric's **display** unit (ms,
cm, %, spm, bpm) rather than in z or deviation-%, so a page can print
"260 ms, usual 252-262" without knowing how the band was built.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from garmin_mcp.analysis.normal_range import (
    MIN_VALID_SPLITS,
    OUTSIDE_Z,
    STREAK_Z,
    WINDOW_DAYS,
    Band,
    as_float,
    compute_band,
    oriented_z,
)
from garmin_mcp.analysis.progression_gate import DECOUPLING_CONTAMINATION_TEMP_C
from garmin_mcp.rag.queries.heat_adjustment import (
    HeatAdjustmentModel,
    HeatModelCoefficients,
)

#: Row keys accepted for the few columns whose name differs between the
#: ``activities`` table and the prefetched context (kept tolerant so the reader
#: above this module can hand over either shape).
_HR_KEYS = ("avg_hr", "avg_heart_rate")
_PACE_KEYS = ("pace", "pace_s_per_km", "avg_pace_seconds_per_km")
_TEMP_KEYS = ("temp", "temp_c", "temp_celsius")

#: Reasons a signal is not judged.
REASON_SHORT_RUN = "only {n} running splits (need {required})"
REASON_NO_SPLIT_COUNT = "the run's valid-split count is unknown"
# Written in Japanese because the page prints ``reason`` verbatim under the
# metric, and this is the one reason an ordinary quality session triggers: a
# tempo run judged by an easy-run model is a reference value, not a finding
# (#1273).
REASON_EXTRAPOLATED = "学習した速度の範囲から大きく外れているため参考値"
REASON_NO_HR_MODEL = "no fitted heat-adjustment model"
REASON_NO_HR_INPUTS = "pace, temperature or HR missing for the expected-HR read"
REASON_HOT = (
    "temperature {temp} °C: the drift is thermal, not a durability read "
    "(>= {limit} °C)"
)


@dataclass(frozen=True)
class _FormSpec:
    """One pace-corrected form metric and where to read it on a row."""

    metric: str
    label_ja: str
    unit: str
    higher_is_worse: bool
    delta_key: str
    delta_is_pct: bool  # False -> the delta is absolute and divided by expected
    expected_key: str
    actual_key: str


_FORM_SPECS: tuple[_FormSpec, ...] = (
    _FormSpec(
        metric="gct",
        label_ja="接地時間",
        unit="ms",
        higher_is_worse=True,
        delta_key="gct_delta_pct",
        delta_is_pct=True,
        expected_key="gct_ms_expected",
        actual_key="gct_ms_actual",
    ),
    _FormSpec(
        metric="vo",
        label_ja="上下動",
        unit="cm",
        higher_is_worse=True,
        delta_key="vo_delta_cm",
        delta_is_pct=False,
        expected_key="vo_cm_expected",
        actual_key="vo_cm_actual",
    ),
    _FormSpec(
        metric="vr",
        label_ja="上下動比",
        unit="%",
        higher_is_worse=True,
        delta_key="vr_delta_pct",
        delta_is_pct=True,
        expected_key="vr_pct_expected",
        actual_key="vr_pct_actual",
    ),
    _FormSpec(
        metric="cadence",
        label_ja="ケイデンス",
        unit="spm",
        higher_is_worse=False,
        delta_key="cadence_delta_pct",
        delta_is_pct=True,
        expected_key="cadence_expected",
        actual_key="cadence_actual",
    ),
)


def build_signals(
    today: Mapping[str, Any],
    history: Sequence[Mapping[str, Any]],
    *,
    hr_model: HeatModelCoefficients | None = None,
) -> list[dict[str, Any]]:
    """Judge today's run against the athlete's own prior runs, metric by metric.

    Args:
        today: The run under analysis as a plain dict: ``activity_date``,
            ``n_valid_splits``, ``intensity_category``, the form delta /
            expected / actual columns, ``power_efficiency_score``,
            ``hr_drift_percentage``, ``avg_hr``, ``pace``, ``temp``. Missing
            keys are tolerated -- the affected signal reports why it could not
            be judged.
        history: Prior runs in the same shape, ascending by date (re-sorted
            defensively). Rows dated on or after ``today`` and rows older than
            ``WINDOW_DAYS`` are dropped, so a caller may pass a wider slice.
        hr_model: Coefficients from ``HeatAdjustmentModel.fit`` over that same
            window. Without them the ``hr_vs_expected`` signal is not judged;
            every other signal is unaffected.

    Returns:
        One dict per signal, in the order of the table in the module docstring::

            {family, metric, label_ja, unit, today, expected, normal_low,
             normal_high, z, status, adverse, direction, streak, n, reason}

        All values are JSON-serialisable plain types (no numpy scalars, no
        ``date`` objects). ``today`` / ``expected`` / ``normal_*`` are in the
        metric's display unit and rounded to 1 dp; ``status`` is one of
        ``within`` / ``edge`` / ``outside`` / ``insufficient``.
    """
    prior = _window(today, history)

    signals = [_form_signal(spec, today, prior) for spec in _FORM_SPECS]
    signals.append(_power_signal(today, prior))
    signals.append(_hr_vs_expected_signal(today, prior, hr_model))
    signals.append(_hr_drift_signal(today, prior))
    return signals


# --------------------------------------------------------------------------- #
# Form signals
# --------------------------------------------------------------------------- #


def _form_signal(
    spec: _FormSpec,
    today: Mapping[str, Any],
    prior: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Judge one pace-corrected form metric against every comparable prior run."""
    expected = as_float(_get(today, spec.expected_key))
    today_display = as_float(_get(today, spec.actual_key))
    deviation = _form_deviation_pct(today, spec)
    if today_display is None and expected is not None and deviation is not None:
        today_display = expected * (1.0 + deviation / 100.0)

    blocker = _eligibility_reason(today, spec.metric)
    if blocker is not None:
        return _unjudged(
            metric=spec.metric,
            family="form",
            label_ja=spec.label_ja,
            unit=spec.unit,
            today=today_display,
            expected=expected,
            reason=blocker,
        )

    eligible = [row for row in prior if _eligibility_reason(row, spec.metric) is None]
    series = [_form_deviation_pct(row, spec) for row in eligible]
    band = compute_band(series, deviation, higher_is_worse=spec.higher_is_worse)

    # Without the model expectation the band cannot be expressed in ms / cm, so
    # it falls back to the deviation-% it was built in.
    expected_display = expected if expected is not None else band.centre

    return _assemble(
        metric=spec.metric,
        family="form",
        label_ja=spec.label_ja,
        unit=spec.unit,
        today=today_display,
        expected=expected_display,
        band=band,
        display=_relative_display(expected),
        higher_is_worse=spec.higher_is_worse,
        streak=_streak(
            band,
            deviation,
            [_form_deviation_pct(row, spec) for row in reversed(eligible)],
            higher_is_worse=spec.higher_is_worse,
        ),
    )


def _power_signal(
    today: Mapping[str, Any], prior: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Judge the power efficiency score (%) against comparable prior runs.

    Unlike the four form metrics this one has no model expectation to hang a
    display unit on: the score *is* the percentage, so ``expected`` is the
    athlete's own baseline centre.
    """
    value = _power_pct(today)
    blocker = _eligibility_reason(today, "power")
    if blocker is not None:
        return _unjudged(
            metric="power",
            family="form",
            label_ja="パワー効率",
            unit="%",
            today=value,
            expected=None,
            reason=blocker,
        )

    eligible = [row for row in prior if _eligibility_reason(row, "power") is None]
    band = compute_band(
        [_power_pct(row) for row in eligible], value, higher_is_worse=False
    )
    return _assemble(
        metric="power",
        family="form",
        label_ja="パワー効率",
        unit="%",
        today=value,
        expected=band.centre,
        band=band,
        display=_identity,
        higher_is_worse=False,
        streak=_streak(
            band,
            value,
            [_power_pct(row) for row in reversed(eligible)],
            higher_is_worse=False,
        ),
    )


# --------------------------------------------------------------------------- #
# Cardio signals (same intensity family only)
# --------------------------------------------------------------------------- #


def _hr_vs_expected_signal(
    today: Mapping[str, Any],
    prior: Sequence[Mapping[str, Any]],
    hr_model: HeatModelCoefficients | None,
) -> dict[str, Any]:
    """Judge measured HR against what pace, temperature and date predict.

    The residual (``avg_hr - expected_hr``) already removes the heat and the
    fitness trend, so what is left is "harder or easier than this run should
    have felt" -- judged against the residuals of the same intensity family.
    """
    label_ja = "心拍（想定比）"
    measured = as_float(_get(today, *_HR_KEYS))

    if hr_model is None:
        return _unjudged(
            metric="hr_vs_expected",
            family="cardio",
            label_ja=label_ja,
            unit="bpm",
            today=measured,
            expected=None,
            reason=REASON_NO_HR_MODEL,
        )

    base_date = _base_date(today, prior)
    expected = _expected_hr(today, hr_model, base_date)
    if expected is None or measured is None:
        return _unjudged(
            metric="hr_vs_expected",
            family="cardio",
            label_ja=label_ja,
            unit="bpm",
            today=measured,
            expected=expected,
            reason=REASON_NO_HR_INPUTS,
        )

    family = [row for row in prior if _same_family(row, today)]
    series = [_hr_residual(row, hr_model, base_date) for row in family]
    band = compute_band(series, measured - expected, higher_is_worse=True)

    return _assemble(
        metric="hr_vs_expected",
        family="cardio",
        label_ja=label_ja,
        unit="bpm",
        today=measured,
        expected=expected,
        band=band,
        display=_offset_display(expected),
        higher_is_worse=True,
        streak=_streak(
            band,
            measured - expected,
            [_hr_residual(row, hr_model, base_date) for row in reversed(family)],
            higher_is_worse=True,
        ),
    )


def _hr_drift_signal(
    today: Mapping[str, Any], prior: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Judge Pa:HR decoupling against the same intensity family's own drift."""
    label_ja = "心拍ドリフト"
    value = as_float(_get(today, "hr_drift_percentage"))

    temp = as_float(_get(today, *_TEMP_KEYS))
    if temp is not None and temp >= DECOUPLING_CONTAMINATION_TEMP_C:
        return _unjudged(
            metric="hr_drift",
            family="cardio",
            label_ja=label_ja,
            unit="%",
            today=value,
            expected=None,
            reason=REASON_HOT.format(
                temp=round(temp, 1), limit=DECOUPLING_CONTAMINATION_TEMP_C
            ),
        )

    family = [
        row for row in prior if _same_family(row, today) and not _contaminated(row)
    ]
    band = compute_band(
        [as_float(_get(row, "hr_drift_percentage")) for row in family],
        value,
        higher_is_worse=True,
    )
    return _assemble(
        metric="hr_drift",
        family="cardio",
        label_ja=label_ja,
        unit="%",
        today=value,
        expected=band.centre,
        band=band,
        display=_identity,
        higher_is_worse=True,
        streak=_streak(
            band,
            value,
            [as_float(_get(row, "hr_drift_percentage")) for row in reversed(family)],
            higher_is_worse=True,
        ),
    )


# --------------------------------------------------------------------------- #
# Assembly helpers
# --------------------------------------------------------------------------- #


def _identity(value: float) -> float:
    """The band is already in the display unit (power %, drift %)."""
    return value


def _relative_display(base: float | None) -> Callable[[float], float]:
    """Map a deviation % onto the display unit around ``base`` (257 ms + 1.6 %)."""
    if base is None:
        return _identity
    return lambda value: base * (1.0 + value / 100.0)


def _offset_display(base: float) -> Callable[[float], float]:
    """Map a residual onto the display unit around ``base`` (expected HR + 4 bpm)."""
    return lambda value: base + value


def _assemble(
    *,
    metric: str,
    family: str,
    label_ja: str,
    unit: str,
    today: float | None,
    expected: float | None,
    band: Band,
    display: Callable[[float], float],
    higher_is_worse: bool,
    streak: int,
) -> dict[str, Any]:
    """Render a judged band as a signal dict in the metric's display unit."""
    normal_low: float | None = None
    normal_high: float | None = None
    if band.centre is not None and band.spread:
        low = display(band.centre - OUTSIDE_Z * band.spread)
        high = display(band.centre + OUTSIDE_Z * band.spread)
        normal_low, normal_high = min(low, high), max(low, high)

    return {
        "family": family,
        "metric": metric,
        "label_ja": label_ja,
        "unit": unit,
        "today": _round(today),
        "expected": _round(expected),
        "normal_low": _round(normal_low),
        "normal_high": _round(normal_high),
        "z": band.z,
        "status": band.status,
        "adverse": band.adverse,
        "direction": _direction(band.z, higher_is_worse=higher_is_worse),
        "streak": streak,
        "n": band.n,
        "reason": band.reason,
    }


def _unjudged(
    *,
    metric: str,
    family: str,
    label_ja: str,
    unit: str,
    today: float | None,
    expected: float | None,
    reason: str,
) -> dict[str, Any]:
    """A signal the run itself disqualifies, before any baseline is built."""
    return {
        "family": family,
        "metric": metric,
        "label_ja": label_ja,
        "unit": unit,
        "today": _round(today),
        "expected": _round(expected),
        "normal_low": None,
        "normal_high": None,
        "z": None,
        "status": "insufficient",
        "adverse": False,
        "direction": None,
        "streak": 0,
        "n": 0,
        "reason": reason,
    }


def _streak(
    band: Band,
    today_value: float | None,
    prior_values: Sequence[float | None],
    *,
    higher_is_worse: bool,
) -> int:
    """Consecutive most-recent runs (today first) leaning the unfavourable way.

    Every run is placed in *today's* band rather than in a band of its own, so
    the streak answers "how long has this lean been going on, measured the way
    we measure it now". A run whose value is missing ends the streak: we cannot
    claim continuity through a gap.
    """
    if not band.judged:
        return 0

    count = 0
    for value in (today_value, *prior_values):
        z = oriented_z(value, band.centre, band.spread, higher_is_worse=higher_is_worse)
        if z is None or z < STREAK_Z:
            break
        count += 1
    return count


def _direction(z: float | None, *, higher_is_worse: bool) -> str | None:
    """Which side of the band today sits on, in the metric's own terms."""
    if z is None or z == 0:
        return None
    raw = z if higher_is_worse else -z
    return "high" if raw > 0 else "low"


def _round(value: float | None) -> float | None:
    """1 dp is the display resolution of every unit here (ms / cm / % / spm / bpm)."""
    return None if value is None else round(float(value), 1)


# --------------------------------------------------------------------------- #
# Row helpers
# --------------------------------------------------------------------------- #


def _get(row: Mapping[str, Any], *keys: str) -> Any:
    """First non-``None`` value among ``keys`` (column-name tolerance)."""
    for key in keys:
        value = row.get(key)
        if value is not None:
            return value
    return None


def _form_deviation_pct(row: Mapping[str, Any], spec: _FormSpec) -> float | None:
    """The row's pace-corrected deviation (%) for one form metric."""
    delta = as_float(row.get(spec.delta_key))
    if delta is None:
        return None
    if spec.delta_is_pct:
        return delta
    expected = as_float(row.get(spec.expected_key))
    if not expected:
        return None
    return delta / expected * 100.0


def _power_pct(row: Mapping[str, Any]) -> float | None:
    """The row's power efficiency score as a percentage."""
    score = as_float(row.get("power_efficiency_score"))
    return None if score is None else score * 100.0


def _eligibility_reason(row: Mapping[str, Any], metric: str) -> str | None:
    """Why the row's form metrics cannot be trusted, or ``None`` when they can."""
    splits = as_float(row.get("n_valid_splits"))
    if splits is None:
        return REASON_NO_SPLIT_COUNT
    if splits < MIN_VALID_SPLITS:
        return REASON_SHORT_RUN.format(n=int(splits), required=MIN_VALID_SPLITS)
    if row.get(f"{metric}_extrapolated") or row.get("extrapolated"):
        return REASON_EXTRAPOLATED
    return None


def _same_family(row: Mapping[str, Any], today: Mapping[str, Any]) -> bool:
    """Whether the row was run at today's intensity (easy / tempo / ...)."""
    return row.get("intensity_category") == today.get("intensity_category")


def _contaminated(row: Mapping[str, Any]) -> bool:
    """Whether the row was hot enough for its drift to be thermal."""
    temp = as_float(_get(row, *_TEMP_KEYS))
    return temp is not None and temp >= DECOUPLING_CONTAMINATION_TEMP_C


def _expected_hr(
    row: Mapping[str, Any], coeffs: HeatModelCoefficients, base_date: date | None
) -> float | None:
    """Model-predicted HR for the row, or ``None`` when an input is missing."""
    pace = as_float(_get(row, *_PACE_KEYS))
    temp = as_float(_get(row, *_TEMP_KEYS))
    obs_date = _row_date(row)
    if pace is None or temp is None or obs_date is None or base_date is None:
        return None
    return HeatAdjustmentModel.expected_hr(pace, temp, obs_date, coeffs, base_date)


def _hr_residual(
    row: Mapping[str, Any], coeffs: HeatModelCoefficients, base_date: date | None
) -> float | None:
    """``avg_hr - expected_hr`` for the row, or ``None`` when an input is missing."""
    measured = as_float(_get(row, *_HR_KEYS))
    expected = _expected_hr(row, coeffs, base_date)
    if measured is None or expected is None:
        return None
    return measured - expected


def _row_date(row: Mapping[str, Any]) -> date | None:
    """The row's ``activity_date`` as a ``date`` (accepts ``date`` or string)."""
    value = row.get("activity_date")
    if isinstance(value, date):
        return value
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _base_date(
    today: Mapping[str, Any], prior: Sequence[Mapping[str, Any]]
) -> date | None:
    """Day 0 of the model's time axis: the earliest run in the window.

    Any consistent base works for the residual band (a different base shifts
    every residual by the same ``beta_days`` offset), so the earliest run in the
    window the caller passed is used.
    """
    dates = [d for d in (_row_date(row) for row in (*prior, today)) if d is not None]
    return min(dates) if dates else None


def _window(
    today: Mapping[str, Any], history: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Prior runs inside the trailing ``WINDOW_DAYS``, ascending by date.

    Rows dated on or after today are dropped (a later run cannot judge today).
    Rows without a parseable date are kept in the order given -- the caller
    knows something we do not -- and so is the whole history when today itself
    carries no date.
    """
    rows = [dict(row) for row in history]
    rows.sort(key=lambda row: _row_date(row) or date.min)

    today_date = _row_date(today)
    if today_date is None:
        return rows

    kept = []
    for row in rows:
        row_date = _row_date(row)
        if row_date is None:
            kept.append(row)
            continue
        if row_date >= today_date:
            continue
        if (today_date - row_date).days > WINDOW_DAYS:
            continue
        kept.append(row)
    return kept
