import { useMemo } from "react";
import EChart from "../../components/EChart";
import {
  AXIS_STYLE,
  BASE_CHART_OPTION,
  METRIC_COLORS,
} from "../../components/chartTheme";
import { formatNumber } from "../../utils/formatNumber";
import type { HrvStatus, RecoveryTrend, RhrTrend } from "../../types";

interface RecoveryPanelProps {
  data: RecoveryTrend;
}

const RHR_SERIES = "安静時心拍 (bpm)";
const HRV_SERIES = "夜間HRV (ms)";

const RHR_TREND_META: Record<
  Exclude<RhrTrend, null>,
  { label: string; className: string }
> = {
  improving: { label: "改善", className: "bg-emerald-100 text-emerald-700" },
  stable: { label: "安定", className: "bg-sky-100 text-sky-700" },
  fatigued: { label: "疲労", className: "bg-red-100 text-red-700" },
};

const HRV_STATUS_META: Record<
  Exclude<HrvStatus, null>,
  { label: string; className: string }
> = {
  high: { label: "高め", className: "bg-emerald-100 text-emerald-700" },
  balanced: { label: "バランス", className: "bg-sky-100 text-sky-700" },
  low: { label: "低下", className: "bg-amber-100 text-amber-700" },
};

export default function RecoveryPanel({ data }: RecoveryPanelProps) {
  const { rhr, hrv, series } = data;

  const option = useMemo(() => {
    // HRV baseline band drawn as a shaded area between the latest low/high.
    return {
      ...BASE_CHART_OPTION,
      tooltip: { trigger: "axis" as const },
      legend: { data: [RHR_SERIES, HRV_SERIES] },
      xAxis: {
        type: "category" as const,
        data: series.map((p) => p.date),
        ...AXIS_STYLE,
      },
      yAxis: [
        { type: "value" as const, name: "bpm", ...AXIS_STYLE },
        { type: "value" as const, name: "ms", ...AXIS_STYLE },
      ],
      series: [
        {
          name: RHR_SERIES,
          type: "line" as const,
          yAxisIndex: 0,
          smooth: true,
          connectNulls: false,
          itemStyle: { color: METRIC_COLORS.heart_rate },
          lineStyle: { color: METRIC_COLORS.heart_rate },
          data: series.map((p) => p.resting_hr),
        },
        {
          name: HRV_SERIES,
          type: "line" as const,
          yAxisIndex: 1,
          smooth: true,
          connectNulls: false,
          itemStyle: { color: METRIC_COLORS.speed },
          lineStyle: { color: METRIC_COLORS.speed },
          data: series.map((p) => p.hrv_overnight_ms),
        },
      ],
    };
  }, [series]);

  const rhrMeta = rhr.rhr_trend != null ? RHR_TREND_META[rhr.rhr_trend] : null;
  const hrvMeta = hrv.status != null ? HRV_STATUS_META[hrv.status] : null;
  const isEmpty = series.length === 0;

  return (
    <section
      aria-label="回復トレンド (RHR / HRV)"
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="font-display text-base font-semibold text-ink">
          回復トレンド (RHR / HRV)
        </h2>
        <div className="flex shrink-0 items-center gap-1.5">
          {rhrMeta && (
            <span
              className={`rounded-full px-2.5 py-1 text-xs font-semibold ${rhrMeta.className}`}
            >
              RHR {rhrMeta.label}
            </span>
          )}
          {hrvMeta && (
            <span
              className={`rounded-full px-2.5 py-1 text-xs font-semibold ${hrvMeta.className}`}
            >
              HRV {hrvMeta.label}
            </span>
          )}
        </div>
      </div>
      {isEmpty ? (
        <p className="py-8 text-center text-sm text-slate-500">
          回復データ (RHR / HRV) の記録がありません
        </p>
      ) : (
        <>
          <p className="mb-1 text-sm text-slate-600">
            7日RHR中央値{" "}
            <span className="font-semibold text-ink">
              {formatNumber(rhr.median_7d)}
            </span>{" "}
            bpm / 最新HRV{" "}
            <span className="font-semibold text-ink">
              {formatNumber(hrv.latest_ms)}
            </span>{" "}
            ms
            {hrv.under_recovery && (
              <span className="ml-1 font-semibold text-red-600">
                （HRV連夜低下→回復優先）
              </span>
            )}
          </p>
          <EChart option={option} ariaLabel="RHRとHRVの推移グラフ" />
        </>
      )}
    </section>
  );
}
