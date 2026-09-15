import { useMemo } from "react";
import EChart from "../../components/EChart";
import {
  AXIS_STYLE,
  BASE_CHART_OPTION,
  COMPARE_COLOR,
  INK_COLOR,
  X_AXIS_STYLE,
} from "../../components/chartTheme";
import { axisTooltipFormatter, formatNumber } from "../../utils/formatNumber";
import type { ObjectiveFitnessTrend } from "../../api/trends";
import { BLOCK_SUMMARY_CLASS, BlockEmpty, CHART_HEIGHT } from "./blockShell";

interface ObjectiveFitnessBlockProps {
  data: ObjectiveFitnessTrend;
}

const GARMIN_SERIES = "Garmin VO2max";
const OBJECTIVE_SERIES = "客観VDOT";

/**
 * "客観VDOT 35.2 · Garmin VO2max 45.1 · 楽観ギャップ 9.4 (約 63 s/km)" — what
 * the runner's own races say against what the watch believes.
 */
export function objectiveFitnessSummaryLine(
  data: ObjectiveFitnessTrend,
): string {
  const objective = data.objective_curve.at(-1) ?? null;
  const garmin = data.garmin_vo2max.at(-1) ?? null;
  const parts: string[] = [];
  if (objective != null) {
    parts.push(`${OBJECTIVE_SERIES} ${formatNumber(objective.vdot, 1)}`);
  }
  if (garmin != null) {
    parts.push(`${GARMIN_SERIES} ${formatNumber(garmin.value, 1)}`);
  }
  if (data.optimism_gap != null) {
    parts.push(
      `楽観ギャップ ${formatNumber(data.optimism_gap.gap_vdot, 1)} (約 ${formatNumber(
        data.optimism_gap.gap_pace_sec_per_km,
        0,
      )} s/km 速い見積もり)`,
    );
  }
  return parts.join(" · ");
}

/**
 * Overlays the objective (real-run derived) fitness curve on Garmin's VO2max
 * series on a shared VDOT/VO2max axis, surfacing the optimism gap (how much
 * faster Garmin's estimate looks than actual best-effort performance).
 *
 * The real-run curve is what this block exists to show, so it takes the ink;
 * Garmin's estimate is the thing it is read against and takes the hairline
 * compare color (Morning Brief §Charts).
 */
export default function ObjectiveFitnessBlock({
  data,
}: ObjectiveFitnessBlockProps) {
  const { objective_curve, garmin_vo2max } = data;

  // Shared category axis: union of both series' dates, ascending.
  const dates = useMemo(
    () =>
      Array.from(
        new Set([
          ...garmin_vo2max.map((p) => p.date),
          ...objective_curve.map((p) => p.date),
        ]),
      ).sort(),
    [garmin_vo2max, objective_curve],
  );

  const option = useMemo(
    () => ({
      ...BASE_CHART_OPTION,
      tooltip: {
        trigger: "axis" as const,
        formatter: axisTooltipFormatter({
          [GARMIN_SERIES]: 1,
          [OBJECTIVE_SERIES]: 1,
        }),
      },
      xAxis: {
        type: "category" as const,
        data: dates,
        ...X_AXIS_STYLE,
      },
      yAxis: [
        {
          type: "value" as const,
          name: "VDOT / VO2max",
          scale: true,
          ...AXIS_STYLE,
        },
      ],
      series: [
        {
          name: GARMIN_SERIES,
          type: "line" as const,
          itemStyle: { color: COMPARE_COLOR },
          lineStyle: { color: COMPARE_COLOR },
          data: garmin_vo2max.map((p) => [p.date, p.value]),
        },
        {
          name: OBJECTIVE_SERIES,
          type: "line" as const,
          itemStyle: { color: INK_COLOR },
          lineStyle: { color: INK_COLOR },
          data: objective_curve.map((p) => [p.date, p.vdot]),
        },
      ],
    }),
    [dates, garmin_vo2max, objective_curve],
  );

  if (garmin_vo2max.length === 0 && objective_curve.length === 0) {
    return <BlockEmpty message="データがありません" />;
  }
  return (
    <div className="flex flex-col gap-3">
      <p className={BLOCK_SUMMARY_CLASS}>{objectiveFitnessSummaryLine(data)}</p>
      <EChart
        option={option}
        ariaLabel="実走VDOTとGarmin VO2maxの推移グラフ"
        height={CHART_HEIGHT}
      />
    </div>
  );
}
