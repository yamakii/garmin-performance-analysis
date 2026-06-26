"""Personal wellness baseline analysis (pure functions, no I/O).

Derives a *personal* baseline band (rolling mean +/- SD) for HRV, Training
Readiness and resting HR from ``daily_wellness`` history, then judges today's
value against that band as a z-score ``z = (today - mean) / std`` rather than an
absolute threshold (#555). Low HRV / low readiness or *high* RHR relative to the
athlete's own band raises an ``adverse`` deviation flag that downstream layers
(readiness gate / weekly-review notes) consume.

This is a descriptive early-warning layer, not a predictive model: it only
flags how far today sits from the personal band. All functions are null-safe --
missing days / values are skipped rather than raising, so device-off days do not
break the band.

Standard deviation uses the *population* form (``statistics.pstdev``) so the
band reflects the full observed history rather than an inferential estimate.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

# Default trailing window (days) used to build the personal baseline band.
DEFAULT_WINDOW_DAYS = 30

# Minimum non-null samples required before a band is trustworthy; below this the
# metric is reported as ``insufficient`` (no signal) rather than a noisy z.
DEFAULT_MIN_SAMPLES = 7

# How many SDs from the mean count as a deviation (band half-width). Boundaries
# are strict: exactly +/- this many SDs is still "within".
DEFAULT_SD_THRESHOLD = 1.0


@dataclass(frozen=True)
class MetricBaseline:
    """One metric's personal baseline band and today's position within it."""

    metric: str  # "hrv" | "readiness" | "rhr"
    mean: float | None
    std: float | None
    today: float | None
    z: float | None  # (today - mean) / std
    flag: str  # "low" | "high" | "within" | "insufficient"
    adverse: bool  # unfavorable direction (hrv/readiness=low, rhr=high)
    n: int  # non-null sample count used for the band


def compute_metric_baseline(
    series: Sequence[float | None],
    today: float | None,
    *,
    metric: str | None = None,
    min_samples: int = DEFAULT_MIN_SAMPLES,
    direction: str = "low_is_bad",
    sd_threshold: float = DEFAULT_SD_THRESHOLD,
) -> MetricBaseline:
    """Position ``today`` within the personal band built from ``series``.

    Args:
        series: Past ``window_days`` values (today excluded), ascending. ``None``
            entries (device-off days) are skipped before computing mean / SD.
        today: Today's value, or ``None`` when unmeasured.
        metric: Explicit metric label for the returned block. When ``None`` the
            label falls back to ``_metric_label(direction)`` -- a best-effort
            guess for lone calls. ``compute_wellness_baseline_deviation`` always
            passes the correct label so HRV / readiness (both ``low_is_bad``) are
            not conflated (#583).
        min_samples: Minimum non-null samples required; below this the band is
            ``"insufficient"`` (mean/std/z = ``None``).
        direction: ``"low_is_bad"`` (HRV / readiness -- a low value is
            unfavorable) or ``"high_is_bad"`` (RHR -- a high value is
            unfavorable). Governs which band edge sets ``adverse``.
        sd_threshold: Band half-width in SDs. ``flag = "low"`` when
            ``z < -sd_threshold``, ``"high"`` when ``z > +sd_threshold``, else
            ``"within"`` (exactly +/- the threshold is ``"within"`` -- strict).

    Returns:
        A :class:`MetricBaseline`. ``mean`` / ``std`` are population statistics
        rounded to 1 dp; ``z`` is rounded to 2 dp. When samples are insufficient
        or ``today`` is ``None`` the metric is ``"insufficient"`` and
        ``adverse=False`` (no signal).
    """
    metric = metric if metric is not None else _metric_label(direction)
    present = [v for v in series if v is not None]
    n = len(present)

    if n < min_samples or today is None:
        return MetricBaseline(
            metric=metric,
            mean=None,
            std=None,
            today=today,
            z=None,
            flag="insufficient",
            adverse=False,
            n=n,
        )

    mean = statistics.mean(present)
    std = statistics.pstdev(present)

    if std == 0:
        # Degenerate band: no spread -> today cannot deviate in SD units.
        z = 0.0
        flag = "within"
    else:
        z = round((today - mean) / std, 2)
        if z < -sd_threshold:
            flag = "low"
        elif z > sd_threshold:
            flag = "high"
        else:
            flag = "within"

    adverse = flag == "high" if direction == "high_is_bad" else flag == "low"

    return MetricBaseline(
        metric=metric,
        mean=round(mean, 1),
        std=round(std, 1),
        today=today,
        z=z,
        flag=flag,
        adverse=adverse,
        n=n,
    )


# Per-metric wiring: daily_wellness column + unfavorable direction.
_METRICS: tuple[tuple[str, str, str], ...] = (
    ("hrv", "hrv_overnight_ms", "low_is_bad"),
    ("readiness", "training_readiness", "low_is_bad"),
    ("rhr", "resting_hr", "high_is_bad"),
)


def _metric_label(direction: str) -> str:
    """Best-effort metric label for a lone ``compute_metric_baseline`` call."""
    return "rhr" if direction == "high_is_bad" else "hrv"


def compute_wellness_baseline_deviation(
    rows: Sequence[dict[str, Any]],
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
    sd_threshold: float = DEFAULT_SD_THRESHOLD,
) -> dict[str, Any]:
    """Personal-baseline deviation for HRV / readiness / RHR on the latest day.

    Args:
        rows: ``daily_wellness`` rows ascending by date, today at the tail. Each
            row is a dict with ``date`` plus the metric columns
            (``hrv_overnight_ms``, ``training_readiness``, ``resting_hr``).
        window_days: Trailing window (days) used to build each band (today
            excluded). Default 30.
        sd_threshold: Band half-width in SDs (see ``compute_metric_baseline``).

    Returns:
        ``{date, hrv: {...}, readiness: {...}, rhr: {...}, overall_flag: bool}``
        where each metric block is a :class:`MetricBaseline` as a dict.
        ``overall_flag`` is ``True`` when *any* metric is in an unfavorable
        deviation (``adverse`` and ``flag`` in ``{"low", "high"}``). Empty
        ``rows`` yields all-``insufficient`` blocks and ``overall_flag=False``.
    """
    if not rows:
        empty = {
            label: asdict(
                compute_metric_baseline([], None, metric=label, direction=direction)
            )
            for label, _col, direction in _METRICS
        }
        return {"date": None, **empty, "overall_flag": False}

    today_row = rows[-1]
    history = rows[:-1][-window_days:]

    result: dict[str, Any] = {"date": _row_date(today_row)}
    overall_flag = False
    for label, col, direction in _METRICS:
        series = [r.get(col) for r in history]
        baseline = compute_metric_baseline(
            series,
            today_row.get(col),
            metric=label,
            direction=direction,
            sd_threshold=sd_threshold,
        )
        result[label] = asdict(baseline)
        if baseline.adverse and baseline.flag in {"low", "high"}:
            overall_flag = True

    result["overall_flag"] = overall_flag
    return result


def _row_date(row: dict[str, Any]) -> str | None:
    """Stringified ``date`` field of a row (null-safe)."""
    value = row.get("date")
    return None if value is None else str(value)
