import { useMemo } from "react";
import EChart from "../../components/EChart";
import {
  AXIS_STYLE,
  BASE_CHART_OPTION,
  CHART_GRID,
  CHART_SPLIT_NUMBER,
  INK_COLOR,
  METRIC_COLORS,
  THRESHOLD_LINE,
  X_AXIS_STYLE,
} from "../../components/chartTheme";
import type {
  DurabilityActivity,
  DurabilityDirection,
  DurabilityTrend,
} from "../../types";
import { BLOCK_SUMMARY_CLASS, BlockEmpty, CHART_HEIGHT } from "./blockShell";

interface DurabilityBlockProps {
  data: DurabilityTrend;
}

const DIRECTION_META: Record<
  DurabilityDirection,
  { label: string; className: string }
> = {
  improving: { label: "改善傾向", className: "text-status-good" },
  worsening: { label: "悪化傾向", className: "font-bold text-status-warn" },
  stable: { label: "横ばい", className: "text-ink-soft" },
  insufficient_data: { label: "データ不足", className: "text-ink-muted" },
};

/**
 * 5% is the shared threshold for both plotted series: decoupling above it means
 * insufficient durability, GCT fade above it flags muscular fade. One line, not
 * two coincident ones at the same height (Issue #913).
 */
const FADE_WARNING_LINE = 5;

const DECOUPLING_SERIES = "デカップリング (%)";
const GCT_FADE_SERIES = "GCT後半失速 (%)";

function formatFade(value: number | null): string {
  return value == null ? "—" : `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

/**
 * "ロング 5本 · 直近デカップリング 6.3% · GCT後半失速 +5.8%" — how the last long
 * run held together, against how many runs the trend is drawn from.
 */
export function durabilitySummaryLine(data: DurabilityTrend): string {
  const latest = data.activities[data.activities.length - 1] ?? null;
  if (latest == null) {
    return "";
  }
  return [
    `ロング ${data.trend.data_points}本`,
    `直近デカップリング ${formatFade(latest.decoupling_pct)}`,
    `GCT後半失速 ${formatFade(latest.gct_fade_pct)}`,
  ].join(" · ");
}

export default function DurabilityBlock({ data }: DurabilityBlockProps) {
  const { activities, trend } = data;

  const option = useMemo(() => {
    const byDate = new Map<string, DurabilityActivity>(
      activities.map((a) => [a.activity_date, a]),
    );
    return {
      ...BASE_CHART_OPTION,
      grid: { ...CHART_GRID },
      tooltip: {
        trigger: "axis" as const,
        formatter: (params: unknown) => {
          const list = Array.isArray(params) ? params : [params];
          const first = list[0] as { axisValue?: string } | undefined;
          const axisValue = first?.axisValue ?? "";
          const activity = byDate.get(axisValue);
          if (!activity) return axisValue;
          // Only the two plotted series: VO / VR fades are not on this chart,
          // so listing them made the tooltip describe invisible lines (#913).
          return [
            `<strong>${axisValue}</strong>`,
            `デカップリング: ${formatFade(activity.decoupling_pct)}`,
            `GCT後半失速: ${formatFade(activity.gct_fade_pct)}`,
          ].join("<br/>");
        },
      },
      xAxis: {
        type: "category" as const,
        data: activities.map((a) => a.activity_date),
        ...X_AXIS_STYLE,
      },
      yAxis: {
        type: "value" as const,
        name: "%",
        splitNumber: CHART_SPLIT_NUMBER,
        ...AXIS_STYLE,
      },
      series: [
        {
          name: DECOUPLING_SERIES,
          type: "line" as const,
          // Decoupling is the durability read this block is named after: ink.
          itemStyle: { color: INK_COLOR },
          lineStyle: { color: INK_COLOR },
          data: activities.map((a) => a.decoupling_pct),
          // Single shared threshold line for both series: a 注意 marker, not a
          // failure — 5% is where a long run starts to fade (§Charts).
          markLine: {
            silent: true,
            symbol: "none",
            lineStyle: { color: THRESHOLD_LINE.warn, type: "dotted" as const },
            label: {
              formatter: "5% 目安",
              color: THRESHOLD_LINE.warn,
              fontSize: 11,
            },
            data: [{ yAxis: FADE_WARNING_LINE }],
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
        },
      ],
    };
  }, [activities]);

  const directionMeta =
    DIRECTION_META[trend.direction] ?? DIRECTION_META.insufficient_data;
  // form_direction is optional on empty/older payloads; fall back safely so the
  // line never reads an undefined meta.
  const formDirectionMeta =
    (trend.form_direction != null
      ? DIRECTION_META[trend.form_direction]
      : undefined) ?? DIRECTION_META.insufficient_data;

  if (activities.length === 0) {
    return (
      <BlockEmpty message="10km以上のロングランがないため、耐久性トレンドを算出できません" />
    );
  }
  return (
    <div className="flex flex-col gap-3">
      <p className={BLOCK_SUMMARY_CLASS}>
        {durabilitySummaryLine(data)}
        {" · "}
        <span className={directionMeta.className}>
          心拍 {directionMeta.label}
        </span>
        {" / "}
        <span className={formDirectionMeta.className}>
          フォーム {formDirectionMeta.label}
        </span>
      </p>
      <EChart
        option={option}
        ariaLabel="ロングランのデカップリング・GCT失速推移グラフ"
        height={CHART_HEIGHT}
      />
    </div>
  );
}
