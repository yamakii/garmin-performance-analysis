"""Tests for the run-level normal-range policy (#1248).

The series fixtures are built so the robust band is *exactly* known: the shape
below has median 0 and median-absolute-deviation 1 in shape units, so scaling it
by ``spread / MAD_SCALE`` gives a band whose centre is 0.0 and whose robust
spread is ``spread``. Every expected z is therefore an exact number rather than
an eyeballed approximation.
"""

import pytest

from garmin_mcp.analysis.normal_range import (
    EDGE_Z,
    MAD_SCALE,
    MIN_BASELINE_RUNS,
    OUTSIDE_Z,
    Band,
    compute_band,
    oriented_z,
    robust_spread,
)

# Symmetric shape: median 0, median(|value|) 1, mass on both tails.
_SHAPE = (-2.0, -1.5, -1.0, -0.5, 0.0, 0.0, 0.5, 1.0, 1.5, 2.0)


def _series(
    blocks: int = 3, *, centre: float = 0.0, spread: float = 1.0
) -> list[float]:
    """A baseline with exactly ``centre`` as median and ``spread`` as MAD*scale."""
    return [centre + spread * value / MAD_SCALE for value in _SHAPE] * blocks


# --------------------------------------------------------------------------- #
# compute_band()
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_band_within_at_one_spread():
    band = compute_band(_series(), 1.0, higher_is_worse=True)

    assert band.n == 30
    assert band.centre == pytest.approx(0.0)
    assert band.spread == pytest.approx(1.0)
    assert band.z == pytest.approx(1.0)
    assert band.status == "within"
    assert band.adverse is False


@pytest.mark.unit
def test_band_edge_between_1_5_and_2():
    band = compute_band(_series(), 1.7, higher_is_worse=True)

    assert band.z is not None
    assert EDGE_Z <= band.z < OUTSIDE_Z
    assert band.status == "edge"
    assert band.adverse is False


@pytest.mark.unit
def test_band_outside_at_two_spreads():
    band = compute_band(_series(), 2.1, higher_is_worse=True)

    assert band.z == pytest.approx(2.1)
    assert band.status == "outside"
    assert band.adverse is True


@pytest.mark.unit
def test_band_favourable_outlier_is_not_adverse():
    """A run far *better* than normal is still outside the band, never adverse."""
    band = compute_band(_series(), -2.3, higher_is_worse=True)

    assert band.status == "outside"
    assert band.z is not None and band.z < 0
    assert band.adverse is False


@pytest.mark.unit
def test_band_orients_lower_is_worse():
    """Cadence style: the low side is the bad side, so z comes back positive."""
    band = compute_band(_series(), -2.2, higher_is_worse=False)

    assert band.z == pytest.approx(2.2)
    assert band.status == "outside"
    assert band.adverse is True


@pytest.mark.unit
def test_band_thin_baseline_is_insufficient():
    band = compute_band(_series()[:9], 3.0, higher_is_worse=True)

    assert band.status == "insufficient"
    assert band.z is None
    assert band.adverse is False
    assert band.n == 9
    assert band.reason is not None
    assert "baseline size 9" in band.reason
    assert str(MIN_BASELINE_RUNS) in band.reason


@pytest.mark.unit
def test_band_missing_today_is_insufficient():
    band = compute_band(_series(), None, higher_is_worse=True)

    assert band.status == "insufficient"
    assert band.reason == "today's value is missing"


@pytest.mark.unit
def test_band_is_robust_to_one_wild_value():
    """One interval session must not widen the band that judges an easy run."""
    series = [*_series(blocks=2), 40.0]

    band = compute_band(series, 2.5, higher_is_worse=True)

    assert band.spread == pytest.approx(1.0)
    assert band.z == pytest.approx(2.5)
    assert band.status == "outside"

    # A mean/SD band over the same series would have called today normal.
    mean = sum(series) / len(series)
    sd = (sum((v - mean) ** 2 for v in series) / len(series)) ** 0.5
    assert abs((2.5 - mean) / sd) < 1.0


@pytest.mark.unit
def test_band_zero_mad_falls_back_to_sd():
    """A series more than half identical has MAD 0; the SD keeps the band usable."""
    series = [0.0] * 15 + [5.0, 6.0, 7.0]

    band = compute_band(series, 3.0, higher_is_worse=True)

    assert band.spread is not None
    assert band.spread > 0
    assert band.status != "insufficient"
    assert band.z == pytest.approx(3.0 / band.spread, abs=0.01)


@pytest.mark.unit
def test_band_without_any_spread_is_insufficient():
    band = compute_band([4.0] * 12, 9.0, higher_is_worse=True)

    assert band.status == "insufficient"
    assert band.reason == "baseline has no spread"


@pytest.mark.unit
def test_band_skips_none_and_nan_entries():
    series: list[float | None] = [*_series(), None, float("nan")]

    band = compute_band(series, 1.0, higher_is_worse=True)

    assert band.n == 30
    assert band.status == "within"


# --------------------------------------------------------------------------- #
# robust_spread() / oriented_z() / Band
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_robust_spread_matches_mad_scale():
    series = _series(spread=2.5)

    assert robust_spread(series, 0.0) == pytest.approx(2.5)


@pytest.mark.unit
def test_oriented_z_flips_for_lower_is_worse():
    assert oriented_z(-3.0, 0.0, 1.5, higher_is_worse=False) == pytest.approx(2.0)
    assert oriented_z(-3.0, 0.0, 1.5, higher_is_worse=True) == pytest.approx(-2.0)


@pytest.mark.unit
def test_oriented_z_is_none_without_a_band():
    assert oriented_z(3.0, None, None, higher_is_worse=True) is None
    assert oriented_z(None, 0.0, 1.0, higher_is_worse=True) is None
    assert oriented_z(3.0, 0.0, 0.0, higher_is_worse=True) is None


@pytest.mark.unit
def test_judged_property_tracks_status():
    judged = compute_band(_series(), 0.5, higher_is_worse=True)
    unjudged = compute_band([], 0.5, higher_is_worse=True)

    assert isinstance(judged, Band)
    assert judged.judged is True
    assert unjudged.judged is False
