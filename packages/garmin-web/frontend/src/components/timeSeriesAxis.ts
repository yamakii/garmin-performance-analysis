/**
 * Sparse, round-number Y axes for the time-series bands (Issue #1170).
 *
 * #1167 tried to thin the axis down to 2-3 labels with ECharts' own
 * `splitNumber`, but `splitNumber` is only a hint: ECharts still snaps to
 * "nice" intervals on its own and can land on 4 labels (heart rate) or on
 * ragged mm:ss values (pace 7:04 / 8:20). `threeTickAxis` instead computes
 * `min` / `max` / `interval` directly so every band shows EXACTLY three
 * labels (min, mid, max) on multiples of the metric's own unit.
 */

/** A Y axis snapped to exactly three round-number labels. */
export interface SparseAxis {
  min: number;
  max: number;
  interval: number;
}

/** Floating-point noise guard for the floor/ceil snap below. */
const EPSILON = 1e-9;

/**
 * Snap `[lo, hi]` outward to multiples of `unit` so the axis shows exactly
 * three labels: min, mid, max.
 *
 * - `lo === hi` (a flat series) widens the range by one unit on each side
 *   first, so there is something to snap.
 * - `min`/`max` floor/ceil outward to the nearest multiple of `unit`.
 * - If that span is an odd multiple of `unit`, `max` grows by one more unit
 *   so the midpoint itself lands on a multiple of `unit` too.
 */
export function threeTickAxis(lo: number, hi: number, unit: number): SparseAxis {
  let widenedLo = lo;
  let widenedHi = hi;
  if (widenedLo === widenedHi) {
    widenedLo -= unit;
    widenedHi += unit;
  }

  const min = Math.floor(widenedLo / unit + EPSILON) * unit;
  let max = Math.ceil(widenedHi / unit - EPSILON) * unit;

  const span = Math.round((max - min) / unit);
  if (span % 2 !== 0) {
    max += unit;
  }

  const interval = (max - min) / 2;
  return { min, max, interval };
}

/** Label unit per time-series metric key (Issue #1170). */
export const AXIS_UNIT: Record<string, number> = {
  heart_rate: 10,
  speed: 30,
  cadence: 5,
  power: 10,
  ground_contact_time: 10,
  vertical_oscillation: 0.5,
  vertical_ratio: 0.5,
  elevation: 5,
};

/**
 * Smallest "nice" step (1 / 2 / 5 x 10^k) at or above `value`.
 *
 * Used to pick a fallback unit for metrics `AXIS_UNIT` doesn't know about:
 * about a quarter of the range, rounded up so the axis never needs more than
 * three labels to cover it.
 */
function niceStepAtLeast(value: number): number {
  if (value <= 0) {
    return 1;
  }
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const residual = value / magnitude;
  const niceResidual = residual <= 1 ? 1 : residual <= 2 ? 2 : residual <= 5 ? 5 : 10;
  return niceResidual * magnitude;
}

/**
 * `AXIS_UNIT[metric]`, or a 1/2/5x10^k step covering about a quarter of the
 * `[lo, hi]` range for metrics with no known unit.
 */
export function axisUnitFor(metric: string, lo: number, hi: number): number {
  const known = AXIS_UNIT[metric];
  if (known != null) {
    return known;
  }
  return niceStepAtLeast((hi - lo) / 4);
}
