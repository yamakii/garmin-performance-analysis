import { useMemo } from "react";
import EChart from "../../components/EChart";
import {
  AXIS_STYLE,
  BASE_CHART_OPTION,
  CHART_GRID,
  CHART_SPLIT_NUMBER,
  INK_COLOR,
  X_AXIS_STYLE,
} from "../../components/chartTheme";
import { axisTooltipFormatter } from "../../utils/formatNumber";
import type { Granularity, VolumeTrendPoint } from "../../api/trends";
import { BLOCK_SUMMARY_CLASS, BlockEmpty, CHART_HEIGHT } from "./blockShell";

interface VolumeBlockProps {
  data: VolumeTrendPoint[];
  /**
   * Display-only: which bucket the data is aggregated by. The control that
   * changes it lives at the page level (Performance), because the same choice
   * also drives the coach narration at the top of the page — a switch hidden
   * inside this block would silently rewrite content far above it (#892).
   */
  granularity: Granularity;
}

/** How many buckets the trailing average covers. */
const AVERAGE_BUCKETS = 4;

/**
 * "今週 62.7km · 4週平均 58.1" — the latest bucket against its recent normal.
 *
 * A single week means nothing on its own: the trailing average is what says
 * whether the week was a build, a hold or a cutback, so both numbers travel
 * together in the one line above the chart.
 */
export function volumeSummaryLine(
  data: VolumeTrendPoint[],
  granularity: Granularity,
): string {
  if (data.length === 0) {
    return "";
  }
  const latest = data[data.length - 1];
  const window = data.slice(-AVERAGE_BUCKETS);
  const average =
    window.reduce((sum, point) => sum + point.distance_km, 0) / window.length;
  const bucketLabel = granularity === "week" ? "今週" : "今月";
  const averageLabel = granularity === "week" ? "4週平均" : "4ヶ月平均";
  return `${bucketLabel} ${latest.distance_km.toFixed(1)}km · ${averageLabel} ${average.toFixed(1)}`;
}

export default function VolumeBlock({ data, granularity }: VolumeBlockProps) {
  const option = useMemo(
    () => ({
      ...BASE_CHART_OPTION,
      grid: { ...CHART_GRID },
      tooltip: {
        trigger: "axis" as const,
        formatter: axisTooltipFormatter({ "距離 (km)": 1 }),
      },
      xAxis: {
        type: "category" as const,
        data: data.map((p) => p.bucket),
        ...X_AXIS_STYLE,
      },
      yAxis: {
        type: "value" as const,
        name: "km",
        splitNumber: CHART_SPLIT_NUMBER,
        ...AXIS_STYLE,
      },
      series: [
        {
          name: "距離 (km)",
          type: "bar" as const,
          data: data.map((p) => p.distance_km),
          // Square bars: a rounded cap reads as decoration on a value that is
          // meant to be compared bar to bar (Morning Brief §Charts).
          itemStyle: { color: INK_COLOR, borderRadius: 0 },
        },
      ],
    }),
    [data],
  );

  if (data.length === 0) {
    return <BlockEmpty message="データがありません" />;
  }
  return (
    <div className="flex flex-col gap-3">
      <p className={BLOCK_SUMMARY_CLASS}>
        {volumeSummaryLine(data, granularity)} ·{" "}
        {data[data.length - 1].run_count}回
      </p>
      <EChart
        option={option}
        ariaLabel="走行量の棒グラフ"
        height={CHART_HEIGHT}
      />
    </div>
  );
}
