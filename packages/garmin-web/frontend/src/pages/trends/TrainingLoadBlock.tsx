import { useMemo } from "react";
import EChart from "../../components/EChart";
import {
  AXIS_STYLE,
  BASE_CHART_OPTION,
  INK_COLOR,
  METRIC_COLORS,
} from "../../components/chartTheme";
import type { AcwrStatus, AcwrTrend } from "../../types";

interface TrainingLoadBlockProps {
  data: AcwrTrend;
}

const STATUS_META: Record<AcwrStatus, { label: string; className: string }> = {
  undertraining: { label: "負荷不足", className: "bg-sky-100 text-sky-700" },
  optimal: { label: "最適", className: "bg-emerald-100 text-emerald-700" },
  caution: { label: "注意", className: "bg-amber-100 text-amber-700" },
  high_risk: { label: "高リスク", className: "bg-red-100 text-red-700" },
  insufficient_data: {
    label: "データ不足",
    className: "bg-slate-100 text-slate-600",
  },
};

/** ACWR warning line: ratios above 1.5 carry elevated injury risk. */
const ACWR_WARNING_LINE = 1.5;

export default function TrainingLoadBlock({ data }: TrainingLoadBlockProps) {
  const { current, trend } = data;
  const weeks = trend.weeks;

  const option = useMemo(
    () => ({
      ...BASE_CHART_OPTION,
      tooltip: { trigger: "axis" as const },
      legend: { data: ["週間距離 (km)", "ACWR"] },
      xAxis: {
        type: "category" as const,
        data: weeks.map((w) => w.week_start),
        ...AXIS_STYLE,
      },
      yAxis: [
        { type: "value" as const, name: "km", ...AXIS_STYLE },
        {
          type: "value" as const,
          name: "ACWR",
          scale: true,
          ...AXIS_STYLE,
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: "週間距離 (km)",
          type: "bar" as const,
          data: weeks.map((w) => w.load_km),
          itemStyle: { color: INK_COLOR, borderRadius: [3, 3, 0, 0] },
        },
        {
          name: "ACWR",
          type: "line" as const,
          yAxisIndex: 1,
          itemStyle: { color: METRIC_COLORS.heart_rate },
          lineStyle: { color: METRIC_COLORS.heart_rate },
          data: weeks.map((w) => w.acwr),
          markLine: {
            silent: true,
            symbol: "none",
            lineStyle: { color: "#f87171", type: "dashed" as const },
            label: { formatter: "高リスク 1.5", color: "#ef4444" },
            data: [{ yAxis: ACWR_WARNING_LINE }],
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
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="font-display text-base font-semibold text-ink">
          訓練負荷 (ACWR)
        </h2>
        <span
          className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${statusMeta.className}`}
        >
          {statusMeta.label}
        </span>
      </div>
      {isInsufficient ? (
        <p className="py-8 text-center text-sm text-slate-500">
          ACWRを算出するためのデータが不足しています
        </p>
      ) : (
        <>
          <p className="mb-1 text-sm text-slate-600">
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
              className="mb-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
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
