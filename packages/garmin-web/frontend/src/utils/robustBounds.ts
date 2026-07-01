export interface AxisBounds {
  min: number;
  max: number;
}

/**
 * Percentile-based robust min/max for a value axis, ignoring nulls.
 *
 * The core range comes from the loPct/hiPct percentiles (linear interpolation).
 * That range is additionally clamped to a Tukey IQR fence (Q1-1.5*IQR,
 * Q3+1.5*IQR) so a lone extreme outlier — which a percentile of a small sample
 * cannot trim by rank alone — still falls outside [min,max]. ECharts clips such
 * points off-screen without mutating the underlying series data (tooltips keep
 * the real value).
 *
 * Returns null when there is no finite data (caller falls back to auto-scale).
 */
export function robustAxisBounds(
  values: (number | null | undefined)[],
  loPct = 2,
  hiPct = 98,
  padRatio = 0.1,
): AxisBounds | null {
  const finite = values
    .filter((v): v is number => typeof v === "number" && Number.isFinite(v))
    .sort((a, b) => a - b);

  if (finite.length === 0) {
    return null;
  }

  const q1 = percentile(finite, 25);
  const q3 = percentile(finite, 75);
  const iqr = q3 - q1;
  const fenceLo = q1 - 1.5 * iqr;
  const fenceHi = q3 + 1.5 * iqr;

  // Percentile core range, clamped to the IQR fence to reject lone outliers.
  const lo = Math.max(percentile(finite, loPct), fenceLo);
  const hi = Math.min(percentile(finite, hiPct), fenceHi);

  if (hi === lo) {
    return { min: lo - 1, max: hi + 1 };
  }

  const pad = (hi - lo) * padRatio;
  return { min: lo - pad, max: hi + pad };
}

/**
 * Linear-interpolated percentile over an ascending-sorted array of finite numbers.
 */
function percentile(sorted: number[], pct: number): number {
  if (sorted.length === 1) {
    return sorted[0];
  }
  const rank = (pct / 100) * (sorted.length - 1);
  const lowIdx = Math.floor(rank);
  const highIdx = Math.ceil(rank);
  const weight = rank - lowIdx;
  return sorted[lowIdx] * (1 - weight) + sorted[highIdx] * weight;
}
