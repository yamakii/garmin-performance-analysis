import {
  AXIS_STYLE,
  BASE_CHART_OPTION,
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
 * Score panel: the single overall_score series on a fixed 1-5 left axis.
 * Fixing the axis keeps the score trend readable regardless of how flat or
 * spiky the values are — this panel is the primary read.
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
    yAxis: { type: "value" as const, min: 1, max: 5, ...AXIS_STYLE },
    series: [
      {
        name: SCORE_SERIES,
        type: "line" as const,
        data: data.map((p) => p.overall_score),
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
    // Form deltas = violet family (Issue #214), skipping the ink slot.
    color: FORM_LINE_COLORS.slice(1),
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
        data: data.map((p) => p.gct_delta),
      },
      {
        name: DELTA_SERIES[1],
        type: "line" as const,
        data: data.map((p) => p.vo_delta),
      },
      {
        name: DELTA_SERIES[2],
        type: "line" as const,
        data: data.map((p) => p.vr_delta),
      },
    ],
  };
}
