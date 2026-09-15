import { useMemo } from "react";
import EChart from "../../components/EChart";
import {
  AXIS_STYLE,
  BASE_CHART_OPTION,
  CHART_GRID_DUAL,
  CHART_SPLIT_NUMBER,
  METRIC_COLORS,
  X_AXIS_STYLE,
} from "../../components/chartTheme";
import { axisTooltipFormatter } from "../../utils/formatNumber";
import type { PhysiologyTrend } from "../../api/trends";
import { BLOCK_SUMMARY_CLASS, BlockEmpty, CHART_HEIGHT } from "./blockShell";

interface PhysiologyBlockProps {
  data: PhysiologyTrend;
}

/** "VO2max 50.1 · LT心拍 168bpm · 2025-10-13" — the latest of each estimate. */
export function physiologySummaryLine(data: PhysiologyTrend): string {
  const vo2max = data.vo2max.filter((p) => p.value != null).at(-1) ?? null;
  const threshold =
    data.lactate_threshold.filter((p) => p.heart_rate != null).at(-1) ?? null;
  const parts: string[] = [];
  if (vo2max?.value != null) {
    parts.push(`VO2max ${vo2max.value.toFixed(1)}`);
  }
  if (threshold?.heart_rate != null) {
    parts.push(`LT心拍 ${threshold.heart_rate.toFixed(0)}bpm`);
  }
  const latestDate = vo2max?.date ?? threshold?.date ?? null;
  if (latestDate != null) {
    parts.push(latestDate);
  }
  return parts.join(" · ");
}

export default function PhysiologyBlock({ data }: PhysiologyBlockProps) {
  const option = useMemo(
    () => ({
      ...BASE_CHART_OPTION,
      grid: { ...CHART_GRID_DUAL },
      tooltip: {
        trigger: "axis" as const,
        formatter: axisTooltipFormatter({ VO2max: 1, LT心拍: 0 }),
      },
      xAxis: {
        type: "category" as const,
        data: data.vo2max.map((p) => p.date),
        ...X_AXIS_STYLE,
      },
      // Each axis name is painted in its series' color so the reader can tell
      // at a glance which scale a line belongs to (Issue #913); the names are
      // the labels, so the chart carries no legend box.
      yAxis: [
        {
          type: "value" as const,
          name: "VO2max",
          nameTextStyle: { color: METRIC_COLORS.vo2max },
          scale: true,
          splitNumber: CHART_SPLIT_NUMBER,
          ...AXIS_STYLE,
        },
        {
          type: "value" as const,
          name: "LT心拍 (bpm)",
          nameTextStyle: { color: METRIC_COLORS.heart_rate },
          scale: true,
          splitNumber: CHART_SPLIT_NUMBER,
          ...AXIS_STYLE,
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: "VO2max",
          type: "line" as const,
          // The primary series of this block: ink.
          itemStyle: { color: METRIC_COLORS.vo2max },
          lineStyle: { color: METRIC_COLORS.vo2max },
          data: data.vo2max.map((p) => p.value),
        },
        {
          name: "LT心拍",
          type: "line" as const,
          yAxisIndex: 1,
          itemStyle: { color: METRIC_COLORS.heart_rate },
          lineStyle: { color: METRIC_COLORS.heart_rate },
          data: data.lactate_threshold.map((p) => [p.date, p.heart_rate]),
        },
      ],
    }),
    [data],
  );

  if (data.vo2max.length === 0 && data.lactate_threshold.length === 0) {
    return <BlockEmpty message="データがありません" />;
  }
  return (
    <div className="flex flex-col gap-3">
      <p className={BLOCK_SUMMARY_CLASS}>{physiologySummaryLine(data)}</p>
      <EChart
        option={option}
        ariaLabel="VO2maxと乳酸閾値の折れ線グラフ"
        height={CHART_HEIGHT}
      />
    </div>
  );
}
