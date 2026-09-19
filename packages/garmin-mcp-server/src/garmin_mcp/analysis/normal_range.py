"""Run-level "is today inside this athlete's own normal range?" policy (no I/O).

Every band in this system used to carry its own threshold: the server's wellness
baseline judges at 1.0 SD, the Web app draws its band at 1.5, the power-model
read flags ``|z| > 1`` and the analysis contract asks for ``rhr_z >= 1.0``. This
module is the single place the *run-level* thresholds live, so the run page, the
run-note agent and any later caller cannot drift apart. It deliberately does not
migrate those other call sites (#1248); it only owns the run-level policy.

Two decisions are baked in:

**Robust centre and spread.** The band is the ``median`` of the athlete's own
prior runs and ``MAD_SCALE * MAD`` around it, not mean +/- SD. Measured over the
real history, a mean/SD band across mixed run families put the second-half drift
band at -13 %...+22 % -- wide enough that nothing is ever outside it. The same
runs, kept to one intensity family and judged robustly, give -1 %...+10 %. One
wild interval session can no longer widen the band that judges an easy run.

**Orientation, not absolute value.** Every metric is handed to
:func:`compute_band` with ``higher_is_worse`` so the returned ``z`` is oriented:
``z > 0`` always means the unfavourable side (long ground contact, *low*
cadence). Callers can therefore compare metrics without remembering which way
each one points, and ``adverse`` is simply "outside the band on the bad side".

The status vocabulary (``within`` / ``edge`` / ``outside`` / ``insufficient``)
follows :mod:`garmin_mcp.analysis.wellness_baseline` so the two layers read the
same way in a report.

This module replaces grading a run's mean against a *split-level* sigma
(``form_baseline/scorer.py``): over 63 runs that score was uncorrelated with HR
or rest and clustered low on short runs, because a run mean is naturally much
less variable than a single split.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

#: Trailing window (days) of the athlete's own prior runs used to build a band.
#: Consumers do the date filtering; the number lives here so they agree.
WINDOW_DAYS = 60

#: Minimum prior runs before a band is trustworthy. Below this the metric is
#: reported ``insufficient`` rather than judged against two or three runs.
MIN_BASELINE_RUNS = 10

#: Minimum running splits (see ``form_baseline/split_filter.py``) a run needs
#: before its form averages describe anything. A 2-split run is a warmup.
MIN_VALID_SPLITS = 3

#: |z| at or above which today sits at the edge of the normal range.
EDGE_Z = 1.5

#: |z| at or above which today sits outside the normal range.
OUTSIDE_Z = 2.0

#: Per-run |z| that counts towards a streak. Deliberately lower than ``EDGE_Z``:
#: a streak is about repetition of a mild lean, not a single dramatic run.
STREAK_Z = 1.0

#: Consecutive judged runs at ``STREAK_Z`` that make a streak worth reporting.
STREAK_RUNS = 3

#: Scale turning a median absolute deviation into a SD-comparable spread for
#: normally distributed data (``1 / Phi^-1(0.75)``).
MAD_SCALE = 1.4826

#: ``form_baseline.scorer.extrapolation_factor`` at or above which a form metric
#: is no longer judged at all (#1273). The factor is 1.0 inside the trained
#: speed range and 2.0 half a trained range beyond its edge, so 1.5 is a quarter
#: of the range past the edge: an easy run 0.02 m/s outside the band (factor
#: 1.09) is still judged, while a tempo run 0.3 m/s outside it (factor 2.33) is
#: an extrapolation and says nothing about the athlete's form.
EXTRAPOLATION_NOT_JUDGED = 1.5

#: Reasons a metric is not judged. These are stable *codes*, never prose: the
#: text a reader sees is looked up per code in ``run_signals.REASON_MESSAGES_JA``
#: (#1278), so this module can say why it withheld a judgement without deciding
#: how to word it. Values the wording needs (counts) travel alongside the code
#: in :attr:`Band.reason_params`.
REASON_TODAY_MISSING = "value_missing"
REASON_THIN_BASELINE = "thin_baseline"
REASON_NO_SPREAD = "no_spread"


@dataclass(frozen=True)
class Band:
    """The athlete's own normal range for one metric and today's place in it.

    ``centre`` and ``spread`` are in the *series'* own units (e.g. deviation %
    for the pace-corrected form metrics, bpm for an HR residual). Only ``z`` is
    oriented, so a caller that wants display bounds maps
    ``centre -/+ OUTSIDE_Z * spread`` through its own unit conversion.
    """

    centre: float | None
    spread: float | None
    z: float | None  # oriented: > 0 = unfavourable side
    status: str  # "within" | "edge" | "outside" | "insufficient"
    adverse: bool  # status == "outside" and z > 0
    n: int
    reason: str | None  # why insufficient: a ``REASON_*`` code, not prose
    reason_params: Mapping[str, Any] = field(default_factory=dict)

    @property
    def judged(self) -> bool:
        """Whether the band actually judged today (status != insufficient)."""
        return self.status != "insufficient"


def robust_spread(values: Sequence[float], centre: float) -> float:
    """Return ``MAD_SCALE * MAD`` around ``centre``, falling back to the SD.

    A degenerate series (more than half the values identical) has ``MAD == 0``,
    which would make every z infinite. In that case the population SD is used
    instead, and only a series with no spread at all returns ``0.0``.
    """
    mad = statistics.median(abs(v - centre) for v in values)
    spread = MAD_SCALE * mad
    if spread > 0:
        return spread
    return statistics.pstdev(values) if len(values) > 1 else 0.0


def compute_band(
    series: Sequence[float | None],
    today: float | None,
    *,
    higher_is_worse: bool,
    min_samples: int = MIN_BASELINE_RUNS,
) -> Band:
    """Place ``today`` inside the normal range built from ``series``.

    Args:
        series: The athlete's own prior values for this metric (today excluded),
            typically the trailing ``WINDOW_DAYS`` window already filtered to the
            comparable runs. ``None`` and non-finite entries are skipped.
        today: Today's value, or ``None`` when the metric was not measured.
        higher_is_worse: ``True`` when a high value is the unfavourable side
            (ground contact time, HR drift), ``False`` when a low value is
            (cadence, power efficiency). Governs the sign of ``z`` only -- the
            returned ``centre`` / ``spread`` stay in raw series units.
        min_samples: Prior runs required before the band is trusted.

    Returns:
        A :class:`Band`. ``z`` is rounded to 2 dp and the status is read off the
        rounded value, so a reported ``2.0`` is always ``"outside"``. Boundaries
        are inclusive: ``|z| >= EDGE_Z`` is ``"edge"``, ``|z| >= OUTSIDE_Z`` is
        ``"outside"``. When today is missing, the baseline is too thin or it has
        no spread at all, the band is ``"insufficient"`` with a ``reason`` and
        ``adverse=False`` (no signal is never a bad signal).
    """
    present = [f for f in (as_float(v) for v in series) if f is not None]
    n = len(present)

    today_value = as_float(today)
    if today_value is None:
        return _insufficient(n, REASON_TODAY_MISSING)
    if n < min_samples:
        return _insufficient(
            n, REASON_THIN_BASELINE, params={"n": n, "required": min_samples}
        )

    centre = statistics.median(present)
    spread = robust_spread(present, centre)
    if spread <= 0:
        return _insufficient(n, REASON_NO_SPREAD, centre=centre)

    raw_z = (today_value - centre) / spread
    z = round(raw_z if higher_is_worse else -raw_z, 2)

    magnitude = abs(z)
    if magnitude >= OUTSIDE_Z:
        status = "outside"
    elif magnitude >= EDGE_Z:
        status = "edge"
    else:
        status = "within"

    return Band(
        centre=round(centre, 4),
        spread=round(spread, 4),
        z=z,
        status=status,
        adverse=status == "outside" and z > 0,
        n=n,
        reason=None,
    )


def oriented_z(
    value: float | None,
    centre: float | None,
    spread: float | None,
    *,
    higher_is_worse: bool,
) -> float | None:
    """Return one value's oriented z against an existing band, or ``None``.

    Used to place *earlier* runs in today's band (the streak read) without
    rebuilding a band per run.
    """
    number = as_float(value)
    if number is None or centre is None or not spread:
        return None
    raw_z = (number - centre) / spread
    return round(raw_z if higher_is_worse else -raw_z, 2)


def _insufficient(
    n: int,
    reason: str,
    *,
    params: Mapping[str, Any] | None = None,
    centre: float | None = None,
) -> Band:
    """Build an unjudged band carrying the ``reason`` code and its parameters."""
    return Band(
        centre=None if centre is None else round(centre, 4),
        spread=None,
        z=None,
        status="insufficient",
        adverse=False,
        n=n,
        reason=reason,
        reason_params=dict(params or {}),
    )


def as_float(value: Any) -> float | None:
    """Coerce ``value`` to a finite float, or ``None`` when it is not one.

    Rows arrive from DuckDB / numpy, so a value may be ``None``, a ``Decimal``,
    a numpy scalar or a NaN; every caller wants the same "usable number?" test,
    and every caller wants a plain ``float`` back (JSON-serialisable).
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
