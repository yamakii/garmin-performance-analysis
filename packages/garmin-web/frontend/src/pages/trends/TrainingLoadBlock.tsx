import { useMemo } from "react";
import EChart from "../../components/EChart";
import {
  AXIS_STYLE,
  BASELINE_BAND_COLOR,
  BASE_CHART_OPTION,
  INK_COLOR,
  METRIC_COLORS,
  THRESHOLD_LINE,
  X_AXIS_STYLE,
} from "../../components/chartTheme";
import { axisTooltipFormatter } from "../../utils/formatNumber";
import type { EChartsOption } from "../../lib/echarts";
import type { AcwrStatus, AcwrTrend } from "../../types";

interface TrainingLoadBlockProps {
  data: AcwrTrend;
}

/** Status wording + the colour it earns; only 注意 / 高リスク get one. */
const STATUS_META: Record<AcwrStatus, { label: string; className: string }> = {
  undertraining: { label: "負荷不足", className: "text-ink-muted" },
  optimal: { label: "最適", className: "text-ink-soft" },
  caution: { label: "注意", className: "font-bold text-status-warn" },
  high_risk: { label: "高リスク", className: "font-bold text-status-bad" },
  insufficient_data: { label: "データ不足", className: "text-ink-muted" },
};

/** ACWR warning line: ratios above 1.5 carry elevated injury risk. */
const ACWR_WARNING_LINE = 1.5;
/** The 0.8-1.3 sweet spot: enough stimulus without an injury-risk spike. */
const ACWR_OPTIMAL_MIN = 0.8;
const ACWR_OPTIMAL_MAX = 1.3;

const LOAD_SERIES = "週間距離 (km)";
const ACWR_SERIES = "ACWR";

/** Chart height: the load bars only have to carry the ACWR line's shape. */
const CHART_HEIGHT = 200;

/**
 * 訓練負荷: weekly distance as bars with the acute:chronic ratio over them.
 *
 * The block opens with the reading as one mono line, so the chart is read as
 * evidence rather than as the answer. Only the 1.5 risk line is drawn: the
 * optimal band is already shaded, and a second dotted line at 0.8 turned a
 * two-state question ("in the band or over the edge?") into a three-line
 * thicket (#1120).
 */
export default function TrainingLoadBlock({ data }: TrainingLoadBlockProps) {
  const { current, trend } = data;
  const weeks = trend.weeks;

  // Annotated so the markArea band checks as a [start, end] tuple.
  const option = useMemo<EChartsOption>(
    () => ({
      ...BASE_CHART_OPTION,
      grid: { left: 48, right: 48, top: 24, bottom: 24 },
      tooltip: {
        trigger: "axis" as const,
        formatter: axisTooltipFormatter({ [LOAD_SERIES]: 1, [ACWR_SERIES]: 2 }),
      },
      xAxis: {
        type: "category" as const,
        data: weeks.map((w) => w.week_start),
        ...X_AXIS_STYLE,
      },
      // Each axis name is painted in its series' color so the reader can tell
      // at a glance which scale a line belongs to (Issue #913).
      yAxis: [
        {
          type: "value" as const,
          name: "km",
          nameTextStyle: { color: INK_COLOR },
          ...AXIS_STYLE,
        },
        {
          type: "value" as const,
          name: "ACWR",
          nameTextStyle: { color: METRIC_COLORS.acwr },
          scale: true,
          ...AXIS_STYLE,
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: LOAD_SERIES,
          type: "bar" as const,
          data: weeks.map((w) => w.load_km),
          itemStyle: { color: INK_COLOR, borderRadius: 0 },
        },
        {
          name: ACWR_SERIES,
          type: "line" as const,
          yAxisIndex: 1,
          itemStyle: { color: METRIC_COLORS.acwr },
          lineStyle: { color: METRIC_COLORS.acwr },
          data: weeks.map((w) => w.acwr),
          // The optimal band gives the ACWR line a reference to be read
          // against: inside the shaded area is "on target".
          markArea: {
            silent: true,
            data: [
              [
                {
                  yAxis: ACWR_OPTIMAL_MIN,
                  itemStyle: { color: BASELINE_BAND_COLOR },
                },
                { yAxis: ACWR_OPTIMAL_MAX },
              ],
            ],
          },
          markLine: {
            silent: true,
            symbol: "none",
            data: [
              {
                yAxis: ACWR_WARNING_LINE,
                lineStyle: { color: THRESHOLD_LINE.bad, type: "dotted" as const },
                label: { formatter: "高リスク 1.5", color: THRESHOLD_LINE.bad },
              },
            ],
          },
        },
      ],
    }),
    [weeks],
  );

  const statusMeta = STATUS_META[current.status];
  const isInsufficient =
    current.status === "insufficient_data" || current.acwr == null;

  if (isInsufficient) {
    return (
      <p className="text-[15px] leading-[1.7] text-ink-muted">
        ACWRを算出するためのデータが不足しています
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="font-mono text-[13px] text-ink-muted">
        ACWR{" "}
        <span className="font-semibold text-ink">
          {current.acwr?.toFixed(2)}
        </span>{" "}
        · 急性 {current.acute_load_7d.toFixed(1)}km / 慢性週平均{" "}
        {current.chronic_load_28d_weekly.toFixed(1)}km · {weeks.length}週{" · "}
        <span className={statusMeta.className}>{statusMeta.label}</span>
      </p>
      {current.status === "high_risk" && (
        <p
          role="alert"
          className="rounded-md border border-bad-line bg-bad-tint px-4 py-3 text-sm text-status-bad"
        >
          急性負荷が慢性負荷を大きく上回っています。故障リスクが高いため、ボリュームを抑えてください。
        </p>
      )}
      <EChart
        option={option}
        ariaLabel="週間距離とACWRの推移グラフ"
        height={CHART_HEIGHT}
      />
    </div>
  );
}
