import { useMemo } from "react";
import EChart from "../../components/EChart";
import {
  AXIS_STYLE,
  BASE_CHART_OPTION,
  METRIC_COLORS,
} from "../../components/chartTheme";
import type {
  DurabilityActivity,
  DurabilityDirection,
  DurabilityTrend,
} from "../../types";

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
/** GCT fade above 5% in the second half flags muscular fade (same convention). */
const GCT_FADE_WARNING_LINE = 5;

const DECOUPLING_SERIES = "デカップリング (%)";
const GCT_FADE_SERIES = "GCT後半失速 (%)";

function formatFade(value: number | null): string {
  return value == null ? "—" : `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

export default function DurabilityBlock({ data }: DurabilityBlockProps) {
  const { activities, trend } = data;

  const option = useMemo(() => {
    const byDate = new Map<string, DurabilityActivity>(
      activities.map((a) => [a.activity_date, a]),
    );
    return {
      ...BASE_CHART_OPTION,
      tooltip: {
        trigger: "axis" as const,
        formatter: (params: unknown) => {
          const list = Array.isArray(params) ? params : [params];
          const first = list[0] as { axisValue?: string } | undefined;
          const axisValue = first?.axisValue ?? "";
          const activity = byDate.get(axisValue);
          if (!activity) return axisValue;
          return [
            `<strong>${axisValue}</strong>`,
            `デカップリング: ${formatFade(activity.decoupling_pct)}`,
            `GCT後半失速: ${formatFade(activity.gct_fade_pct)}`,
            `上下動後半失速: ${formatFade(activity.vo_fade_pct)}`,
            `上下動比後半失速: ${formatFade(activity.vr_fade_pct)}`,
          ].join("<br/>");
        },
      },
      legend: { data: [DECOUPLING_SERIES, GCT_FADE_SERIES] },
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
          name: DECOUPLING_SERIES,
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
        {
          name: GCT_FADE_SERIES,
          type: "line" as const,
          connectNulls: false,
          itemStyle: { color: METRIC_COLORS.ground_contact_time },
          lineStyle: { color: METRIC_COLORS.ground_contact_time },
          // null form fades render as gaps (connectNulls: false).
          data: activities.map((a) => a.gct_fade_pct),
          markLine: {
            silent: true,
            symbol: "none",
            lineStyle: { color: "#fbbf24", type: "dashed" as const },
            label: { formatter: "GCT 5%", color: "#d97706" },
            data: [{ yAxis: GCT_FADE_WARNING_LINE }],
          },
        },
      ],
    };
  }, [activities]);

  const directionMeta = DIRECTION_META[trend.direction];
  const formDirectionMeta = DIRECTION_META[trend.form_direction];
  const isEmpty = activities.length === 0;

  return (
    <section
      aria-label="耐久性 (心拍デカップリング)"
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="font-display text-base font-semibold text-ink">
          耐久性 (心拍デカップリング・フォーム失速)
        </h2>
        <div className="flex shrink-0 items-center gap-1.5">
          <span
            className={`rounded-full px-2.5 py-1 text-xs font-semibold ${directionMeta.className}`}
          >
            心拍 {directionMeta.label}
          </span>
          <span
            className={`rounded-full px-2.5 py-1 text-xs font-semibold ${formDirectionMeta.className}`}
          >
            フォーム {formDirectionMeta.label}
          </span>
        </div>
      </div>
      {isEmpty ? (
        <p className="py-8 text-center text-sm text-slate-500">
          15km以上のロングランがないため、耐久性トレンドを算出できません
        </p>
      ) : (
        <>
          <p className="mb-1 text-sm text-slate-600">
            ロングラン{" "}
            <span className="font-semibold text-ink">{trend.data_points}</span>{" "}
            本のデカップリングとGCT後半失速の推移 (いずれも5%超で後半失速の目安)
          </p>
          <EChart
            option={option}
            ariaLabel="ロングランのデカップリング・GCT失速推移グラフ"
          />
        </>
      )}
    </section>
  );
}
