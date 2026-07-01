import {
  AXIS_STYLE,
  BASE_CHART_OPTION,
  FORM_DELTA_COLORS,
  FORM_LINE_COLORS,
} from "../../components/chartTheme";
import { axisTooltipFormatter } from "../../utils/formatNumber";
import { robustAxisBounds } from "../../utils/robustBounds";
import type { EChartsOption } from "../../lib/echarts";
import type { FormTrendPoint } from "../../api/trends";

const SCORE_SERIES = "総合スコア";
const DELTA_SERIES = ["GCT Δ%", "VO Δcm", "VR Δ%"] as const;

/** Shared category X axis (dates) for both form panels. */
function dateAxis(data: FormTrendPoint[]) {
  return {
    type: "category" as const,
    data: data.map((p) => p.date),
    ...AXIS_STYLE,
  };
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
    // Overall score = ink (first of the form palette).
    color: [FORM_LINE_COLORS[0]],
    tooltip: {
      trigger: "axis" as const,
      formatter: axisTooltipFormatter({ [SCORE_SERIES]: 1 }),
    },
    legend: { data: [SCORE_SERIES] },
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
        // Faint quality zones behind the line (good / ok / watch).
        markArea: {
          silent: true,
          data: [
            [
              { yAxis: 3.5, itemStyle: { color: "rgba(16,185,129,0.08)" } },
              { yAxis: 5.5 },
            ],
            [
              { yAxis: 2, itemStyle: { color: "rgba(251,191,36,0.08)" } },
              { yAxis: 3.5 },
            ],
            [
              { yAxis: 0.5, itemStyle: { color: "rgba(239,68,68,0.08)" } },
              { yAxis: 2 },
            ],
          ],
        },
      },
    ],
  };
}

/**
 * Delta panel: GCT Δ% / VO Δcm / VR Δ% on a single value axis. The raw range is
 * dominated by rare VR Δ% outliers (e.g. +170%), so derive robust bounds that
 * push those off-screen while leaving the series data untouched (tooltips show
 * reals). Falls back to auto-scale when there is no finite data.
 */
export function buildDeltaChartOption(data: FormTrendPoint[]): EChartsOption {
  const deltaBounds = robustAxisBounds([
    ...data.map((p) => p.gct_delta),
    ...data.map((p) => p.vo_delta),
    ...data.map((p) => p.vr_delta),
  ]);

  return {
    ...BASE_CHART_OPTION,
    // Distinct teal/amber/violet so the three deltas read apart at a glance.
    color: [...FORM_DELTA_COLORS],
    tooltip: {
      trigger: "axis" as const,
      formatter: axisTooltipFormatter({
        [DELTA_SERIES[0]]: 1,
        [DELTA_SERIES[1]]: 1,
        [DELTA_SERIES[2]]: 1,
      }),
    },
    legend: { data: [...DELTA_SERIES] },
    xAxis: dateAxis(data),
    yAxis: {
      type: "value" as const,
      ...(deltaBounds
        ? { min: deltaBounds.min, max: deltaBounds.max }
        : { scale: true }),
      ...AXIS_STYLE,
    },
    series: [
      {
        name: DELTA_SERIES[0],
        type: "line" as const,
        symbol: "circle" as const,
        symbolSize: 5,
        lineStyle: { width: 2 },
        data: data.map((p) => p.gct_delta),
        // Zero-delta baseline: deltas above/below the form baseline read against it.
        markLine: {
          silent: true,
          symbol: "none" as const,
          data: [{ yAxis: 0 }],
          lineStyle: { type: "dashed" as const, color: "#94a3b8", width: 1 },
          label: {
            formatter: "基準",
            position: "insideStartTop" as const,
            color: "#94a3b8",
            fontSize: 11,
          },
        },
      },
      {
        name: DELTA_SERIES[1],
        type: "line" as const,
        symbol: "circle" as const,
        symbolSize: 5,
        lineStyle: { width: 2 },
        data: data.map((p) => p.vo_delta),
      },
      {
        name: DELTA_SERIES[2],
        type: "line" as const,
        symbol: "circle" as const,
        symbolSize: 5,
        lineStyle: { width: 2 },
        data: data.map((p) => p.vr_delta),
      },
    ],
  };
}
