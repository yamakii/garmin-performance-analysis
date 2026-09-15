import {
  AXIS_LABEL_COLOR,
  AXIS_STYLE,
  BASE_CHART_OPTION,
  CHART_FONT_SIZE,
  CHART_GRID,
  CHART_SPLIT_NUMBER,
  COMPARE_COLOR,
  INK_COLOR,
  X_AXIS_STYLE,
} from "../../components/chartTheme";
import { formatTargetTime } from "../../utils/race";
import {
  formatDateLabel,
  formatFullDateLabel,
  toIsoDate,
} from "../../utils/format";
import type { EChartsOption } from "../../lib/echarts";
import type { RacePredictionHistory } from "../../types";

const PREDICTION_SERIES = "予測タイム";
const REQUIRED_SERIES = "必要な傾き";

/**
 * "予測の推移": the goal-race time each day's fitness implied, read against
 * the target (Issue #1133).
 *
 * The x axis is a *time* axis, so every day sits at its real distance from
 * every other one. That is the whole point of the panel: race day is typically
 * months past the last fitness day, and the "必要な傾き" hairline from the
 * latest prediction to the target on race day only reads as a slope when that
 * gap is drawn to scale. On the category axis this started with, race day was
 * one extra slot at the end — 152 days squeezed into one tick, which turned
 * the hairline into a near-vertical stub (Issue #1152).
 *
 * Returns null when there is nothing to plot, so the caller can omit the whole
 * section rather than render an empty frame.
 */
export function buildPredictionChartOption(
  history: RacePredictionHistory,
): EChartsOption | null {
  const points = history.series;
  if (points.length === 0) {
    return null;
  }

  const raceDate = history.goal?.race_date ?? null;
  const target = history.goal?.target_time_seconds ?? null;
  const latest = points[points.length - 1];
  // ISO days compare lexicographically, so a race already run keeps the whole
  // series on screen instead of cropping it.
  const lastDay =
    raceDate != null && raceDate > latest.date ? raceDate : latest.date;

  const markLineData: Record<string, unknown>[] = [];
  if (target != null) {
    markLineData.push({
      yAxis: target,
      lineStyle: { type: "dashed" as const, color: COMPARE_COLOR, width: 1 },
      label: {
        formatter: `目標 ${formatTargetTime(target)}`,
        position: "insideStartTop" as const,
        color: COMPARE_COLOR,
        fontSize: CHART_FONT_SIZE,
      },
    });
  }
  if (raceDate != null) {
    markLineData.push({
      xAxis: raceDate,
      lineStyle: { type: "dotted" as const, color: AXIS_LABEL_COLOR, width: 1 },
      label: {
        formatter: "レース",
        color: AXIS_LABEL_COLOR,
        fontSize: CHART_FONT_SIZE,
      },
    });
  }

  const series: Record<string, unknown>[] = [
    {
      name: PREDICTION_SERIES,
      type: "line" as const,
      symbol: "circle" as const,
      symbolSize: 4,
      lineStyle: { width: 2.5 },
      connectNulls: false,
      data: points.map((point) => [point.date, point.predicted_time_seconds]),
      markLine: {
        silent: true,
        symbol: "none" as const,
        data: markLineData,
      },
    },
  ];

  if (raceDate != null && target != null) {
    series.push({
      name: REQUIRED_SERIES,
      type: "line" as const,
      symbol: "none" as const,
      lineStyle: { width: 1.5, color: COMPARE_COLOR },
      data: [
        [latest.date, latest.predicted_time_seconds],
        [raceDate, target],
      ],
    });
  }

  return {
    ...BASE_CHART_OPTION,
    // The prediction is the primary series; everything it is measured against
    // (target line, race marker, required slope) stays hairline.
    color: [INK_COLOR, COMPARE_COLOR],
    grid: { ...CHART_GRID },
    tooltip: {
      trigger: "axis" as const,
      // A time axis would otherwise head the tooltip with a full timestamp
      // ("2026-09-15 00:00:00") for what is only ever a calendar day.
      formatter: formatTooltip,
    },
    xAxis: {
      type: "time" as const,
      min: points[0].date,
      max: lastDay,
      ...X_AXIS_STYLE,
      axisLabel: {
        ...X_AXIS_STYLE.axisLabel,
        formatter: (value: number) => {
          const day = isoDay(value);
          return day != null ? formatDateLabel(day).slice(0, 5) : "";
        },
      },
    },
    yAxis: {
      type: "value" as const,
      scale: true,
      // hh:mm:ss labels are wide and the panel is short: four of them is all
      // that fits without stacking (#1142).
      splitNumber: CHART_SPLIT_NUMBER,
      ...AXIS_STYLE,
      axisLabel: {
        ...AXIS_STYLE.axisLabel,
        formatter: (value: number) => formatTargetTime(value),
      },
    },
    series,
  } as EChartsOption;
}

/**
 * The calendar day of an axis value. Series data carries the original ISO day
 * string; axis ticks arrive as epoch milliseconds, which ECharts derives in
 * the reader's timezone (the same one it parsed the day string in).
 */
function isoDay(value: unknown): string | null {
  if (typeof value === "string") {
    return value.slice(0, 10);
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return toIsoDate(new Date(value));
  }
  return null;
}

type TooltipParam = {
  seriesName?: string;
  marker?: string;
  value?: unknown;
};

function formatTooltip(params: unknown): string {
  const rows = (Array.isArray(params) ? params : [params]) as TooltipParam[];
  const lines: string[] = [];
  let day: string | null = null;
  for (const row of rows) {
    if (!Array.isArray(row.value)) {
      continue;
    }
    day = day ?? isoDay(row.value[0]);
    const seconds = row.value[1];
    const shown = typeof seconds === "number" ? formatTargetTime(seconds) : "-";
    lines.push(`${row.marker ?? ""}${row.seriesName ?? ""} ${shown}`);
  }
  const head = day != null ? formatFullDateLabel(day) : "";
  return [head, ...lines].filter((line) => line !== "").join("<br/>");
}
