import { useMemo } from "react";
import EChart from "../../components/EChart";
import {
  AXIS_STYLE,
  BASE_CHART_OPTION,
  METRIC_COLORS,
} from "../../components/chartTheme";
import { axisTooltipFormatter, formatNumber } from "../../utils/formatNumber";
import type { HrvStatus, RecoveryTrend, RhrTrend } from "../../types";
import { CARD_CLASS } from "../../components/Card";

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

  // RHR and HRV are read in opposite directions (low RHR = good, high HRV =
  // good), so overlaying them on a dual axis made every crossing meaningless.
  // Each metric gets its own single-axis panel instead, following the form
  // score/delta split of Issue #691.
  const dateAxis = useMemo(
    () => ({
      type: "category" as const,
      data: series.map((p) => p.date),
      ...AXIS_STYLE,
    }),
    [series],
  );

  const rhrOption = useMemo(
    () => ({
      ...BASE_CHART_OPTION,
      tooltip: {
        trigger: "axis" as const,
        formatter: axisTooltipFormatter({ [RHR_SERIES]: 0 }),
      },
      legend: { data: [RHR_SERIES] },
      xAxis: dateAxis,
      yAxis: {
        type: "value" as const,
        name: "bpm",
        nameTextStyle: { color: METRIC_COLORS.heart_rate },
        scale: true,
        ...AXIS_STYLE,
      },
      series: [
        {
          name: RHR_SERIES,
          type: "line" as const,
          smooth: true,
          connectNulls: false,
          itemStyle: { color: METRIC_COLORS.heart_rate },
          lineStyle: { color: METRIC_COLORS.heart_rate },
          data: series.map((p) => p.resting_hr),
        },
      ],
    }),
    [dateAxis, series],
  );

  const hrvOption = useMemo(
    () => ({
      ...BASE_CHART_OPTION,
      tooltip: {
        trigger: "axis" as const,
        formatter: axisTooltipFormatter({ [HRV_SERIES]: 0 }),
      },
      legend: { data: [HRV_SERIES] },
      xAxis: dateAxis,
      yAxis: {
        type: "value" as const,
        name: "ms",
        nameTextStyle: { color: METRIC_COLORS.hrv },
        scale: true,
        ...AXIS_STYLE,
      },
      series: [
        {
          name: HRV_SERIES,
          type: "line" as const,
          smooth: true,
          connectNulls: false,
          itemStyle: { color: METRIC_COLORS.hrv },
          lineStyle: { color: METRIC_COLORS.hrv },
          data: series.map((p) => p.hrv_overnight_ms),
        },
      ],
    }),
    [dateAxis, series],
  );

  const rhrMeta = rhr.rhr_trend != null ? RHR_TREND_META[rhr.rhr_trend] : null;
  const hrvMeta = hrv.status != null ? HRV_STATUS_META[hrv.status] : null;
  const isEmpty = series.length === 0;

  return (
    <section
      aria-label="回復トレンド (RHR / HRV)"
      className={CARD_CLASS}
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
          <div className="space-y-4">
            <div>
              <h3 className="mb-1 text-sm font-medium text-slate-600">
                安静時心拍 (bpm・低いほど良い)
              </h3>
              <EChart
                option={rhrOption}
                ariaLabel="安静時心拍の推移グラフ"
                height={220}
              />
            </div>
            <div>
              <h3 className="mb-1 text-sm font-medium text-slate-600">
                夜間HRV (ms・高いほど良い)
              </h3>
              <EChart
                option={hrvOption}
                ariaLabel="夜間HRVの推移グラフ"
                height={220}
              />
            </div>
          </div>
        </>
      )}
    </section>
  );
}
