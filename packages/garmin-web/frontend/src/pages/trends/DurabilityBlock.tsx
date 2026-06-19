import { useMemo } from "react";
import EChart from "../../components/EChart";
import {
  AXIS_STYLE,
  BASE_CHART_OPTION,
  METRIC_COLORS,
} from "../../components/chartTheme";
import type { DurabilityDirection, DurabilityTrend } from "../../types";

interface DurabilityBlockProps {
  data: DurabilityTrend;
}

const DIRECTION_META: Record<
  DurabilityDirection,
  { label: string; className: string }
> = {
  improving: { label: "改善傾向", className: "bg-emerald-100 text-emerald-700" },
  worsening: { label: "悪化傾向", className: "bg-red-100 text-red-700" },
  stable: { label: "横ばい", className: "bg-sky-100 text-sky-700" },
  insufficient_data: {
    label: "データ不足",
    className: "bg-slate-100 text-slate-600",
  },
};

/** Decoupling above 5% is the common threshold for insufficient durability. */
const DECOUPLING_WARNING_LINE = 5;

export default function DurabilityBlock({ data }: DurabilityBlockProps) {
  const { activities, trend } = data;

  const option = useMemo(
    () => ({
      ...BASE_CHART_OPTION,
      tooltip: { trigger: "axis" as const },
      legend: { data: ["デカップリング (%)"] },
      xAxis: {
        type: "category" as const,
        data: activities.map((a) => a.activity_date),
        ...AXIS_STYLE,
      },
      yAxis: {
        type: "value" as const,
        name: "%",
        ...AXIS_STYLE,
      },
      series: [
        {
          name: "デカップリング (%)",
          type: "line" as const,
          itemStyle: { color: METRIC_COLORS.heart_rate },
          lineStyle: { color: METRIC_COLORS.heart_rate },
          data: activities.map((a) => a.decoupling_pct),
          markLine: {
            silent: true,
            symbol: "none",
            lineStyle: { color: "#f87171", type: "dashed" as const },
            label: { formatter: "警告 5%", color: "#ef4444" },
            data: [{ yAxis: DECOUPLING_WARNING_LINE }],
          },
        },
      ],
    }),
    [activities],
  );

  const directionMeta = DIRECTION_META[trend.direction];
  const isEmpty = activities.length === 0;

  return (
    <section
      aria-label="耐久性 (心拍デカップリング)"
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="font-display text-base font-semibold text-ink">
          耐久性 (心拍デカップリング)
        </h2>
        <span
          className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${directionMeta.className}`}
        >
          {directionMeta.label}
        </span>
      </div>
      {isEmpty ? (
        <p className="py-8 text-center text-sm text-slate-500">
          15km以上のロングランがないため、耐久性トレンドを算出できません
        </p>
      ) : (
        <>
          <p className="mb-1 text-sm text-slate-600">
            ロングラン{" "}
            <span className="font-semibold text-ink">
              {trend.data_points}
            </span>{" "}
            本のデカップリング推移 (5%超で後半失速の目安)
          </p>
          <EChart
            option={option}
            ariaLabel="ロングランのデカップリング推移グラフ"
          />
        </>
      )}
    </section>
  );
}
