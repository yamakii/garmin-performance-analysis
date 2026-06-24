import { useMemo } from "react";
import EChart from "../../components/EChart";
import { AXIS_STYLE, BASE_CHART_OPTION } from "../../components/chartTheme";
import { formatNumber } from "../../utils/formatNumber";
import type { BodyCompositionTrend } from "../../types";

interface BodyCompositionChartProps {
  data: BodyCompositionTrend;
}

const FAT_SERIES = "脂肪 (kg)";
const LEAN_SERIES = "除脂肪 (kg)";

const FAT_COLOR = "#fbbf24";
const LEAN_COLOR = "#0d9488";

/** Latest weight from the date-ascending series (null when empty). */
function latestWeight(data: BodyCompositionTrend): number | null {
  const last = data.series[data.series.length - 1];
  return last?.weight_kg ?? null;
}

/** Signed kg string, e.g. -1.2kg / +0.3kg / —. */
function signedKg(value: number | null): string {
  if (value == null) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatNumber(value)}kg`;
}

export default function BodyCompositionChart({ data }: BodyCompositionChartProps) {
  const { series, change } = data;

  const option = useMemo(
    () => ({
      ...BASE_CHART_OPTION,
      tooltip: { trigger: "axis" as const },
      legend: { data: [FAT_SERIES, LEAN_SERIES] },
      xAxis: {
        type: "category" as const,
        data: series.map((p) => p.date),
        ...AXIS_STYLE,
      },
      yAxis: { type: "value" as const, name: "kg", ...AXIS_STYLE },
      series: [
        {
          name: LEAN_SERIES,
          type: "bar" as const,
          stack: "weight",
          itemStyle: { color: LEAN_COLOR },
          data: series.map((p) => p.lean_mass),
        },
        {
          name: FAT_SERIES,
          type: "bar" as const,
          stack: "weight",
          itemStyle: { color: FAT_COLOR },
          data: series.map((p) => p.fat_mass),
        },
      ],
    }),
    [series],
  );

  const isEmpty = series.length === 0;
  const weight = latestWeight(data);

  return (
    <section
      aria-label="体組成 (体重内訳)"
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="font-display text-base font-semibold text-ink">
          体組成 (体重内訳)
        </h2>
        {weight != null && (
          <span className="shrink-0 text-sm font-semibold text-ink">
            最新 {formatNumber(weight)}kg
          </span>
        )}
      </div>
      {isEmpty ? (
        <p className="py-8 text-center text-sm text-slate-500">
          体組成の記録がないため、内訳を表示できません
        </p>
      ) : (
        <>
          <p className="mb-1 text-sm text-slate-600">
            今期 <span className="font-semibold text-ink">{signedKg(change.delta_weight)}</span>
            （脂肪 {signedKg(change.delta_fat)} / 除脂肪 {signedKg(change.delta_lean)}）
          </p>
          {change.muscle_loss_warning && (
            <p
              role="alert"
              className="mb-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700"
            >
              除脂肪量の減少が大きめです。減量ペースを緩めてください
            </p>
          )}
          <EChart
            option={option}
            ariaLabel="体重の脂肪・除脂肪スタック推移グラフ"
          />
        </>
      )}
    </section>
  );
}
