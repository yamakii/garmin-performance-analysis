import type { MetricBaseline, WellnessBaselineDeviation } from "../types";
import { formatNumber } from "./formatNumber";

/**
 * The personal-baseline deviation as rows of a bar chart (Morning Brief,
 * #1120).
 *
 * The three metrics used to be three boxed cards repeating mean, σ and today's
 * value; what the reader actually asks in the morning is "how far out am I,
 * and is that direction good or bad?". That is one number per metric — the z
 * score — plus the direction it points, so the panel becomes three bars
 * hanging off a centre line and the arithmetic lives here, testable without
 * rendering.
 */

/** Japanese name per baseline metric, shared by every surface naming one. */
export const BASELINE_METRIC_LABELS: Record<MetricBaseline["metric"], string> = {
  hrv: "HRV",
  rhr: "安静時心拍",
  readiness: "準備度",
};

/**
 * Metrics whose *higher* readings are the good ones. RHR is the exception: a
 * resting heart rate above the baseline is the unfavourable direction, so its
 * bar must point the same way as a low HRV.
 */
const HIGHER_IS_BETTER: Record<MetricBaseline["metric"], boolean> = {
  hrv: true,
  readiness: true,
  rhr: false,
};

/** Outside the personal band: |z| beyond this is what the page calls 基準外. */
export const Z_OUTSIDE = 1.5;

/** Half-width of the bar track, in percent of the track. */
const HALF_TRACK = 50;

/** z of this magnitude fills the half track; anything beyond is clamped. */
const Z_FULL_SCALE = 3;

/** Which way a deviation points once the metric's polarity is applied. */
export type ZDirection = "favorable" | "unfavorable" | "neutral";

/**
 * The minimum a row needs to be drawn as a bar: how far out it is and which
 * way that is. The wellness panel and the single run's normal-range rows both
 * hang bars off the same centre line, so they share this arithmetic rather
 * than each growing a z-bar of their own (#1252).
 */
export interface ZBarRow {
  z: number | null;
  direction: ZDirection;
}

/** One metric's deviation, ready to draw. */
export interface ZRow extends ZBarRow {
  key: MetricBaseline["metric"];
  label: string;
  /** The reader's own adverse flag, as served. */
  adverse: boolean;
  /** |z| > 1.5 — far enough out to be called 基準外. */
  outside: boolean;
}

/** Fixed row order: the two readings the morning turns on, then readiness. */
const ROW_ORDER: MetricBaseline["metric"][] = ["hrv", "rhr", "readiness"];

/**
 * Direction of a deviation given which side of the baseline is the bad one.
 *
 * `higherIsWorse` is the metric's polarity, not the sign of the reading: a
 * resting heart rate and a ground contact time are worse when high, a cadence
 * is worse when low, and both must end up on the same side of the track.
 */
export function zDirection(
  z: number | null,
  higherIsWorse: boolean,
): ZDirection {
  if (z == null || z === 0) {
    return "neutral";
  }
  return z > 0 === higherIsWorse ? "unfavorable" : "favorable";
}

/** Direction of one metric's deviation, or neutral when it has none. */
function directionOf(
  metric: MetricBaseline["metric"],
  z: number | null,
): ZDirection {
  return zDirection(z, !HIGHER_IS_BETTER[metric]);
}

/** The three metrics as bar rows, in display order. */
export function baselineZRows(data: WellnessBaselineDeviation): ZRow[] {
  return ROW_ORDER.map((key) => {
    const baseline = data[key];
    const z = baseline.flag === "insufficient" ? null : baseline.z;
    return {
      key,
      label: BASELINE_METRIC_LABELS[key],
      z,
      adverse: baseline.adverse,
      outside: z != null && Math.abs(z) > Z_OUTSIDE,
      direction: directionOf(key, z),
    };
  });
}

/**
 * Where one row's bar sits on its track, as CSS percentages.
 *
 * The track's midpoint is the baseline: an unfavourable deviation grows to the
 * right, a favourable one to the left, so a glance down the column reads as
 * "everything on the right is what to worry about" regardless of which
 * direction each metric's good side happens to be.
 */
export function zBarStyle(row: ZBarRow): { left: string; width: string } {
  const magnitude = row.z == null ? 0 : Math.abs(row.z);
  const width = Math.min((magnitude / Z_FULL_SCALE) * HALF_TRACK, HALF_TRACK);
  const left = row.direction === "unfavorable" ? HALF_TRACK : HALF_TRACK - width;
  return { left: `${percent(left)}%`, width: `${percent(width)}%` };
}

/** One decimal at most, and never the float noise of 1.8 / 3 * 50. */
function percent(value: number): string {
  return String(Number(value.toFixed(1)));
}

/**
 * "55–65" — one metric's personal band (mean ± σ) as the vitals rows state it,
 * or null when the baseline has not been built yet.
 */
export function baselineBand(metric: MetricBaseline | null): string | null {
  if (metric?.mean == null || metric.std == null) {
    return null;
  }
  return `${formatNumber(metric.mean - metric.std, 0)}–${formatNumber(
    metric.mean + metric.std,
    0,
  )}`;
}

/** The metrics whose deviation is flagged adverse, in display order. */
export function adverseMetricLabels(
  data: WellnessBaselineDeviation | null,
): string[] {
  if (data == null) {
    return [];
  }
  return ROW_ORDER.filter((key) => data[key].adverse === true).map(
    (key) => BASELINE_METRIC_LABELS[key],
  );
}
