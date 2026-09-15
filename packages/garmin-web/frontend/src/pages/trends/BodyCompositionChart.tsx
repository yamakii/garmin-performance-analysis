import { useMemo } from "react";
import EChart from "../../components/EChart";
import {
  AXIS_STYLE,
  BASE_CHART_OPTION,
  METRIC_COLORS,
  X_AXIS_STYLE,
} from "../../components/chartTheme";
import { axisTooltipFormatter, formatNumber } from "../../utils/formatNumber";
import type { BodyCompositionSeriesPoint, BodyCompositionTrend } from "../../types";

interface BodyCompositionChartProps {
  data: BodyCompositionTrend;
}

const FAT_SERIES = "脂肪 (kg)";
const LEAN_SERIES = "除脂肪 (kg)";

const FAT_COLOR = METRIC_COLORS.fat_mass;
const LEAN_COLOR = METRIC_COLORS.lean_mass;

/** Chart height: the split is stated by the numbers, the bars show its drift. */
const CHART_HEIGHT = 160;

/** Signed kg string, e.g. -1.2kg / +0.3kg / —. */
function signedKg(value: number | null): string {
  if (value == null) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatNumber(value)}kg`;
}

export default function BodyCompositionChart({
  data,
}: BodyCompositionChartProps) {
  const { series, change } = data;

  const option = useMemo(
    () => ({
      ...BASE_CHART_OPTION,
      grid: { left: 48, right: 12, top: 24, bottom: 24 },
      tooltip: {
        trigger: "axis" as const,
        formatter: axisTooltipFormatter({
          [LEAN_SERIES]: 1,
          [FAT_SERIES]: 1,
        }),
      },
      legend: { data: [FAT_SERIES, LEAN_SERIES] },
      xAxis: {
        type: "category" as const,
        data: series.map((p) => p.date),
        ...X_AXIS_STYLE,
      },
      yAxis: { type: "value" as const, name: "kg", ...AXIS_STYLE },
      series: [
        {
          name: LEAN_SERIES,
          type: "bar" as const,
          stack: "weight",
          itemStyle: { color: LEAN_COLOR, borderRadius: 0 },
          data: series.map((p) => p.lean_mass),
        },
        {
          name: FAT_SERIES,
          type: "bar" as const,
          stack: "weight",
          itemStyle: { color: FAT_COLOR, borderRadius: 0 },
          data: series.map((p) => p.fat_mass),
        },
      ],
    }),
    [series],
  );

  if (series.length === 0) {
    return (
      <p className="text-[15px] leading-[1.7] text-ink-muted">
        体組成の記録がないため、内訳を表示できません
      </p>
    );
  }

  const latest: BodyCompositionSeriesPoint = series[series.length - 1];

  return (
    <div className="flex flex-col gap-4">
      <dl className="grid grid-cols-3 gap-4">
        <Reading
          label="体重"
          value={latest.weight_kg}
          delta={change.delta_weight}
        />
        <Reading
          label="体脂肪"
          value={latest.fat_mass}
          delta={change.delta_fat}
        />
        <Reading
          label="除脂肪"
          value={latest.lean_mass}
          delta={change.delta_lean}
          deltaTone={change.muscle_loss_warning ? "bad" : "muted"}
        />
      </dl>
      {change.muscle_loss_warning && (
        <p
          role="alert"
          className="rounded-md border border-bad-line bg-bad-tint px-4 py-3 text-sm text-status-bad"
        >
          除脂肪量の減少が大きめです。減量ペースを緩めてください
        </p>
      )}
      <EChart
        option={option}
        ariaLabel="体重の脂肪・除脂肪スタック推移グラフ"
        height={CHART_HEIGHT}
      />
    </div>
  );
}

/** One kilo reading: the latest value, with the period's change under it. */
function Reading({
  label,
  value,
  delta,
  deltaTone = "muted",
}: {
  label: string;
  value: number | null;
  delta: number | null;
  deltaTone?: "muted" | "bad";
}) {
  return (
    <div>
      <dt className="font-mono text-xs text-ink-muted">{label}</dt>
      <dd className="mt-1 font-mono text-[20px] leading-none font-medium text-ink">
        {value != null ? formatNumber(value) : "—"}
        <span className="ml-[3px] font-sans text-[13px] text-ink-muted">kg</span>
      </dd>
      <dd
        className={`mt-1.5 font-mono text-xs ${
          deltaTone === "bad" ? "font-bold text-status-bad" : "text-ink-muted"
        }`}
      >
        今期 {signedKg(delta)}
      </dd>
    </div>
  );
}
