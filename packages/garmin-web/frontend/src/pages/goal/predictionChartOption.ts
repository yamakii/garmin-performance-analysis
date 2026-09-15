import {
  AXIS_LABEL_COLOR,
  AXIS_STYLE,
  BASE_CHART_OPTION,
  CHART_FONT_SIZE,
  COMPARE_COLOR,
  INK_COLOR,
  X_AXIS_STYLE,
} from "../../components/chartTheme";
import { formatTargetTime } from "../../utils/race";
import type { EChartsOption } from "../../lib/echarts";
import type { RacePredictionHistory } from "../../types";

const PREDICTION_SERIES = "予測タイム";
const REQUIRED_SERIES = "必要な傾き";

/**
 * "予測の推移": the goal-race time each day's fitness implied, read against
 * the target (Issue #1133).
 *
 * The x axis is categorical (one slot per fitness day), so race day is not a
 * position on it — it is appended as one extra category at the end, with the
 * prediction line stopping short of it (a `null` in its last slot). That gives
 * the vertical race marker something to sit on and lets the "必要な傾き" line
 * run from the latest prediction to the target on race day: the improvement
 * still to find, drawn as the hairline it is compared against.
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

  const dates = points.map((point) => point.date);
  const raceDate = history.goal?.race_date ?? null;
  // Race day only earns its own slot when it is not already a fitness day.
  const raceCategory =
    raceDate != null && !dates.includes(raceDate) ? raceDate : null;
  const categories = raceCategory != null ? [...dates, raceCategory] : dates;

  const target = history.goal?.target_time_seconds ?? null;
  const predicted: (number | null)[] = points.map(
    (point) => point.predicted_time_seconds,
  );
  if (raceCategory != null) {
    predicted.push(null);
  }

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
      data: predicted,
      markLine: {
        silent: true,
        symbol: "none" as const,
        data: markLineData,
      },
    },
  ];

  const latest = points[points.length - 1];
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
    tooltip: {
      trigger: "axis" as const,
      valueFormatter: (value: unknown) =>
        typeof value === "number" ? formatTargetTime(value) : "-",
    },
    xAxis: {
      type: "category" as const,
      data: categories,
      ...X_AXIS_STYLE,
    },
    yAxis: {
      type: "value" as const,
      scale: true,
      ...AXIS_STYLE,
      axisLabel: {
        ...AXIS_STYLE.axisLabel,
        formatter: (value: number) => formatTargetTime(value),
      },
    },
    series,
  } as EChartsOption;
}
