import { useMemo } from "react";
import EChart from "../../components/EChart";
import {
  AXIS_STYLE,
  BASE_CHART_OPTION,
  CHART_GRID_DUAL,
  CHART_SPLIT_NUMBER,
  INK_COLOR,
  METRIC_COLORS,
  X_AXIS_STYLE,
} from "../../components/chartTheme";
import { axisTooltipFormatter, formatNumber } from "../../utils/formatNumber";
import { CHART_HEIGHT } from "./blockShell";
import type { BodyCompositionSeriesPoint, BodyCompositionTrend } from "../../types";

interface BodyCompositionChartProps {
  data: BodyCompositionTrend;
}

const WEIGHT_SERIES = "体重 (kg)";
const FAT_SERIES = "体脂肪 (kg)";
const LEAN_SERIES = "除脂肪 (kg)";

const WEIGHT_COLOR = INK_COLOR;
const FAT_COLOR = METRIC_COLORS.fat_mass;
const LEAN_COLOR = METRIC_COLORS.lean_mass;

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
      grid: { ...CHART_GRID_DUAL },
      tooltip: {
        trigger: "axis" as const,
        formatter: axisTooltipFormatter({
          [WEIGHT_SERIES]: 1,
          [LEAN_SERIES]: 1,
          [FAT_SERIES]: 1,
        }),
      },
      // No legend box: the readings above carry the color key, so the legend
      // would only repeat them — and, being laid out below the grid, it used
      // to sit on top of the bars and the date labels (Issue #1148).
      xAxis: {
        type: "category" as const,
        data: series.map((p) => p.date),
        ...X_AXIS_STYLE,
      },
      // A stacked bar from zero drew every week at the same ~78kg height: the
      // whole period's movement is ~2kg, i.e. under 3% of the bar. Lines on
      // scaled axes spend the full plot height on that movement instead, with
      // fat mass on its own axis because it is a third of the other two.
      yAxis: [
        {
          type: "value" as const,
          name: "体重・除脂肪 (kg)",
          scale: true,
          splitNumber: CHART_SPLIT_NUMBER,
          ...AXIS_STYLE,
        },
        {
          type: "value" as const,
          name: "体脂肪 (kg)",
          nameTextStyle: { color: FAT_COLOR },
          scale: true,
          splitNumber: CHART_SPLIT_NUMBER,
          ...AXIS_STYLE,
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: WEIGHT_SERIES,
          type: "line" as const,
          itemStyle: { color: WEIGHT_COLOR },
          lineStyle: { color: WEIGHT_COLOR },
          data: series.map((p) => p.weight_kg),
        },
        {
          name: LEAN_SERIES,
          type: "line" as const,
          itemStyle: { color: LEAN_COLOR },
          lineStyle: { color: LEAN_COLOR },
          data: series.map((p) => p.lean_mass),
        },
        {
          name: FAT_SERIES,
          type: "line" as const,
          yAxisIndex: 1,
          itemStyle: { color: FAT_COLOR },
          lineStyle: { color: FAT_COLOR },
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
          swatch={WEIGHT_COLOR}
          value={latest.weight_kg}
          delta={change.delta_weight}
        />
        <Reading
          label="体脂肪"
          swatch={FAT_COLOR}
          value={latest.fat_mass}
          delta={change.delta_fat}
        />
        <Reading
          label="除脂肪"
          swatch={LEAN_COLOR}
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
        ariaLabel="体重・体脂肪量・除脂肪量の推移グラフ"
        height={CHART_HEIGHT}
      />
    </div>
  );
}

/** One kilo reading: the latest value, with the period's change under it. */
function Reading({
  label,
  swatch,
  value,
  delta,
  deltaTone = "muted",
}: {
  label: string;
  /** Color of this reading's line in the chart below — the legend, inlined. */
  swatch: string;
  value: number | null;
  delta: number | null;
  deltaTone?: "muted" | "bad";
}) {
  return (
    <div>
      <dt className="flex items-center gap-1.5 font-mono text-xs text-ink-muted">
        <span
          aria-hidden="true"
          className="inline-block h-2 w-2 shrink-0"
          style={{ backgroundColor: swatch }}
        />
        {label}
      </dt>
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
