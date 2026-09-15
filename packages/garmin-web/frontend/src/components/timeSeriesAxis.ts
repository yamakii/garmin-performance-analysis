import { robustAxisBounds } from "../utils/robustBounds";

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

/**
 * Metrics whose axis range ignores stop-time zeros and one-off spikes
 * (Issue #1176).
 *
 * A run holds still at traffic lights and water stops, so cadence and power
 * samples drop to 0; ground contact time can carry a single-sample sensor
 * spike. Auto-scaling to those squeezes the running values into a sliver of
 * the band, so these metrics get the same robust percentile/IQR range pace
 * has used since #1148.
 */
export const ROBUST_RANGE_METRICS: ReadonlySet<string> = new Set([
  "speed",
  "cadence",
  "power",
  "ground_contact_time",
  "vertical_oscillation",
  "vertical_ratio",
]);

/** Finite values of `values`, dropping null/undefined/NaN. */
function finiteValues(values: (number | null)[]): number[] {
  return values.filter(
    (v): v is number => typeof v === "number" && Number.isFinite(v),
  );
}

/** Plain min/max over the finite values of `values`; `{ lo: 0, hi: 0 }` when none. */
function plainMinMax(values: (number | null)[]): { lo: number; hi: number } {
  const finite = finiteValues(values);
  return {
    lo: finite.length > 0 ? Math.min(...finite) : 0,
    hi: finite.length > 0 ? Math.max(...finite) : 0,
  };
}

/**
 * The `[lo, hi]` a band's axis should cover before snapping to three ticks
 * (`threeTickAxis`).
 *
 * `ROBUST_RANGE_METRICS` get the percentile/IQR robust range
 * (`robustAxisBounds`), falling back to the plain finite min/max when there
 * are fewer than two finite values to compute percentiles from. `heart_rate`
 * uses the plain min/max, stretched to include `hrCeiling` when given so the
 * prescribed-cap line always lands inside the axis. Every other metric
 * (including `elevation`, where the terrain change is real data, not an
 * outlier) uses the plain finite min/max.
 *
 * `values` for "speed" are already pace in seconds per km (Issue #1148).
 */
export function axisRangeFor(
  metric: string,
  values: (number | null)[],
  hrCeiling?: number | null,
): { lo: number; hi: number } {
  if (ROBUST_RANGE_METRICS.has(metric)) {
    if (finiteValues(values).length >= 2) {
      const bounds = robustAxisBounds(values);
      if (bounds != null) {
        return { lo: bounds.min, hi: bounds.max };
      }
    }
    return plainMinMax(values);
  }

  const range = plainMinMax(values);
  if (metric === "heart_rate" && hrCeiling != null) {
    return {
      lo: Math.min(range.lo, hrCeiling),
      hi: Math.max(range.hi, hrCeiling),
    };
  }
  return range;
}
