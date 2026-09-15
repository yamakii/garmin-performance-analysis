import { useMemo } from "react";
import EChart from "../../components/EChart";
import {
  AXIS_LABEL_COLOR,
  AXIS_STYLE,
  BASELINE_BAND_COLOR,
  BASE_CHART_OPTION,
  INK_COLOR,
  METRIC_COLORS,
  THRESHOLD_LINE,
} from "../../components/chartTheme";
import { axisTooltipFormatter } from "../../utils/formatNumber";
import type { EChartsOption } from "../../lib/echarts";
import type { AcwrStatus, AcwrTrend } from "../../types";
import { CARD_CLASS } from "../../components/Card";

interface TrainingLoadBlockProps {
  data: AcwrTrend;
}

const STATUS_META: Record<AcwrStatus, { label: string; className: string }> = {
  undertraining: { label: "負荷不足", className: " text-ink-soft" },
  optimal: { label: "最適", className: " text-status-good" },
  caution: { label: "注意", className: "bg-warn-tint text-status-warn" },
  high_risk: { label: "高リスク", className: "bg-bad-tint text-status-bad" },
  insufficient_data: {
    label: "データ不足",
    className: "bg-well text-ink-muted",
  },
};

/** ACWR warning line: ratios above 1.5 carry elevated injury risk. */
const ACWR_WARNING_LINE = 1.5;
/** The 0.8-1.3 sweet spot: enough stimulus without an injury-risk spike. */
const ACWR_OPTIMAL_MIN = 0.8;
const ACWR_OPTIMAL_MAX = 1.3;

const LOAD_SERIES = "週間距離 (km)";
const ACWR_SERIES = "ACWR";

export default function TrainingLoadBlock({ data }: TrainingLoadBlockProps) {
  const { current, trend } = data;
  const weeks = trend.weeks;

  // Annotated so the markArea band checks as a [start, end] tuple.
  const option = useMemo<EChartsOption>(
    () => ({
      ...BASE_CHART_OPTION,
      tooltip: {
        trigger: "axis" as const,
        formatter: axisTooltipFormatter({ [LOAD_SERIES]: 1, [ACWR_SERIES]: 2 }),
      },
      legend: { data: [LOAD_SERIES, ACWR_SERIES] },
      xAxis: {
        type: "category" as const,
        data: weeks.map((w) => w.week_start),
        ...AXIS_STYLE,
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
          itemStyle: { color: INK_COLOR, borderRadius: [3, 3, 0, 0] },
        },
        {
          name: ACWR_SERIES,
          type: "line" as const,
          yAxisIndex: 1,
          itemStyle: { color: METRIC_COLORS.acwr },
          lineStyle: { color: METRIC_COLORS.acwr },
          data: weeks.map((w) => w.acwr),
          // The optimal band gives the ACWR line a reference to be read
          // against: inside the green area is "on target", above 1.5 is risk.
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
                yAxis: ACWR_OPTIMAL_MIN,
                lineStyle: { color: AXIS_LABEL_COLOR, type: "dotted" as const },
                label: { formatter: "下限 0.8", color: AXIS_LABEL_COLOR },
              },
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

  return (
    <section
      aria-label="訓練負荷 (ACWR)"
      className={CARD_CLASS}
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-base font-semibold text-ink">
          訓練負荷 (ACWR)
        </h2>
        <span
          className={`shrink-0 rounded-sm px-2.5 py-1 text-xs font-semibold ${statusMeta.className}`}
        >
          {statusMeta.label}
        </span>
      </div>
      {isInsufficient ? (
        <p className="py-8 text-center text-sm text-ink-muted">
          ACWRを算出するためのデータが不足しています
        </p>
      ) : (
        <>
          <p className="mb-1 text-sm text-ink-muted">
            現在のACWR:{" "}
            <span className="font-semibold text-ink">
              {current.acwr?.toFixed(2)}
            </span>{" "}
            (急性 {current.acute_load_7d.toFixed(1)} km / 慢性週平均{" "}
            {current.chronic_load_28d_weekly.toFixed(1)} km)
          </p>
          {current.status === "high_risk" && (
            <p
              role="alert"
              className="mb-2 rounded-md border border-bad-line bg-bad-tint px-3 py-2 text-sm text-status-bad"
            >
              急性負荷が慢性負荷を大きく上回っています。故障リスクが高いため、ボリュームを抑えてください。
            </p>
          )}
          <EChart
            option={option}
            ariaLabel="週間距離とACWRの推移グラフ"
          />
        </>
      )}
    </section>
  );
}
