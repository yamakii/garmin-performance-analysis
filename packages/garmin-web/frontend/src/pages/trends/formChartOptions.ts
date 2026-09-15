import {
  AXIS_STYLE,
  BASELINE_BAND_COLOR,
  BASE_CHART_OPTION,
  CHART_GRID,
  CHART_SPLIT_NUMBER,
  COMPARE_COLOR,
  FORM_DELTA_COLORS,
  FORM_SCORE_COLOR,
  THRESHOLD_LINE,
  X_AXIS_STYLE,
} from "../../components/chartTheme";
import { toIsoDate } from "../../utils/format";
import { axisTooltipFormatter } from "../../utils/formatNumber";
import { robustAxisBounds } from "../../utils/robustBounds";
import type { EChartsOption } from "../../lib/echarts";
import type { FormTrendPoint } from "../../api/trends";

const SCORE_SERIES = "総合スコア";
const DELTA_SERIES = ["GCT Δ%", "VO Δcm", "VR Δ%"] as const;

/** Delta panel window: the trailing year, matching the other /performance charts. */
export const DELTA_WINDOW_DAYS = 365;

/** Delta panel smoothing: a run-to-run delta is noise, a week of them is a trend. */
export const DELTA_SMOOTHING_RUNS = 7;

/** Shared category X axis (dates) for both form panels. */
function dateAxis(data: FormTrendPoint[]) {
  return {
    type: "category" as const,
    data: data.map((p) => p.date),
    ...X_AXIS_STYLE,
  };
}

/**
 * Trailing mean over `window` values, aligned to the last value of each window.
 *
 * The first `window - 1` slots have no full window and read null, as does any
 * window containing a null: averaging around a missing run would invent a
 * value the athlete never ran.
 */
export function rollingMean(
  values: (number | null)[],
  window: number,
): (number | null)[] {
  return values.map((_, index) => {
    if (index + 1 < window) {
      return null;
    }
    const slice = values.slice(index + 1 - window, index + 1);
    if (slice.some((value) => value == null)) {
      return null;
    }
    return slice.reduce((sum, value) => sum! + value!, 0)! / window;
  });
}

/** The points dated within `days` before `today`, inclusive. */
function withinWindow(
  data: FormTrendPoint[],
  today: string,
  days: number,
): FormTrendPoint[] {
  const start = new Date(`${today}T00:00:00`);
  start.setDate(start.getDate() - days);
  const cutoff = toIsoDate(start);
  return data.filter((p) => p.date >= cutoff);
}

/**
 * Score panel: the single overall_score series on a padded 1-5 left axis.
 * The axis runs 0.5-5.5 (ticks at 1-5 with half-unit headroom) so the 5.0/1.0
 * extremes never clip against the frame, backed by three faint quality bands
 * (good / ok / watch) and dotted point markers for at-a-glance reading.
 */
export function buildScoreChartOption(data: FormTrendPoint[]): EChartsOption {
  return {
    ...BASE_CHART_OPTION,
    // Overall score = ink.
    color: [FORM_SCORE_COLOR],
    grid: { ...CHART_GRID },
    tooltip: {
      trigger: "axis" as const,
      formatter: axisTooltipFormatter({ [SCORE_SERIES]: 1 }),
    },
    xAxis: dateAxis(data),
    yAxis: {
      type: "value" as const,
      min: 0.5,
      max: 5.5,
      interval: 1,
      ...AXIS_STYLE,
    },
    series: [
      {
        name: SCORE_SERIES,
        type: "line" as const,
        symbol: "circle" as const,
        symbolSize: 6,
        showSymbol: true,
        lineStyle: { width: 2.5 },
        data: data.map((p) => p.overall_score),
        // The good band as a faint ink wash, and the two quality thresholds as
        // dotted status lines — three stacked tints read as a gradient, which
        // is not what "3.5 and 2.0 are the marks" means (§Charts).
        markArea: {
          silent: true,
          data: [
            [
              { yAxis: 3.5, itemStyle: { color: BASELINE_BAND_COLOR } },
              { yAxis: 5.5 },
            ],
          ],
        },
        markLine: {
          silent: true,
          symbol: "none" as const,
          data: [
            {
              yAxis: 3.5,
              lineStyle: {
                type: "dotted" as const,
                color: THRESHOLD_LINE.warn,
              },
              label: {
                formatter: "3.5 注意",
                color: THRESHOLD_LINE.warn,
                fontSize: 11,
              },
            },
            {
              yAxis: 2,
              lineStyle: {
                type: "dotted" as const,
                color: THRESHOLD_LINE.bad,
              },
              label: {
                formatter: "2.0 要改善",
                color: THRESHOLD_LINE.bad,
                fontSize: 11,
              },
            },
          ],
        },
      },
    ],
  };
}

/**
 * Delta panel: GCT Δ% / VO Δcm / VR Δ% on a single value axis, over the
 * trailing year, each series smoothed over {@link DELTA_SMOOTHING_RUNS} runs.
 *
 * Plotting every run since 2020 put three jagged six-year lines on one 180px
 * panel — spaghetti in which no series could be followed (#1149). The window
 * matches the neighbouring charts ("直近365日"), and the moving average is what
 * makes the three lines separable; raw points are dropped rather than drawn
 * underneath, since they were the noise.
 *
 * The raw range is dominated by rare VR Δ% outliers (e.g. +170%), so bounds are
 * still derived robustly from the raw values in the window — they contain the
 * smoothed lines while pushing the outliers off-screen. Falls back to
 * auto-scale when there is no finite data.
 */
export function buildDeltaChartOption(
  data: FormTrendPoint[],
  today: string = toIsoDate(new Date()),
): EChartsOption {
  const recent = withinWindow(data, today, DELTA_WINDOW_DAYS);
  // Fewer runs than the window would leave the panel blank; smooth over what
  // there is instead.
  const window = Math.min(DELTA_SMOOTHING_RUNS, Math.max(1, recent.length));
  const smooth = (values: (number | null)[]) => rollingMean(values, window);

  const deltaBounds = robustAxisBounds([
    ...recent.map((p) => p.gct_delta),
    ...recent.map((p) => p.vo_delta),
    ...recent.map((p) => p.vr_delta),
  ]);

  return {
    ...BASE_CHART_OPTION,
    // Distinct violet/teal/amber so the three deltas read apart at a glance.
    color: [...FORM_DELTA_COLORS],
    tooltip: {
      trigger: "axis" as const,
      formatter: axisTooltipFormatter({
        [DELTA_SERIES[0]]: 1,
        [DELTA_SERIES[1]]: 1,
        [DELTA_SERIES[2]]: 1,
      }),
    },
    grid: { ...CHART_GRID },
    // Pinned to the top, where `CHART_GRID.top` already reserves space for it.
    // ECharts 6 puts a legend at the bottom by default, which on a 180px chart
    // eats the margin the date labels need and collides with them (#1142).
    legend: { data: [...DELTA_SERIES], top: 0 },
    xAxis: dateAxis(recent),
    yAxis: {
      type: "value" as const,
      splitNumber: CHART_SPLIT_NUMBER,
      ...(deltaBounds
        ? { min: deltaBounds.min, max: deltaBounds.max }
        : { scale: true }),
      ...AXIS_STYLE,
    },
    series: [
      {
        name: DELTA_SERIES[0],
        type: "line" as const,
        // A moving average is a curve, not a set of measurements: no markers.
        showSymbol: false,
        lineStyle: { width: 2 },
        data: smooth(recent.map((p) => p.gct_delta)),
        // Zero-delta baseline: deltas above/below the form baseline read against it.
        markLine: {
          silent: true,
          symbol: "none" as const,
          data: [{ yAxis: 0 }],
          lineStyle: { type: "dashed" as const, color: COMPARE_COLOR, width: 1 },
          label: {
            formatter: "基準",
            position: "insideStartTop" as const,
            color: COMPARE_COLOR,
            fontSize: 11,
          },
        },
      },
      {
        name: DELTA_SERIES[1],
        type: "line" as const,
        showSymbol: false,
        lineStyle: { width: 2 },
        data: smooth(recent.map((p) => p.vo_delta)),
      },
      {
        name: DELTA_SERIES[2],
        type: "line" as const,
        showSymbol: false,
        lineStyle: { width: 2 },
        data: smooth(recent.map((p) => p.vr_delta)),
      },
    ],
  };
}
