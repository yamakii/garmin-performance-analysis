import { useMemo } from "react";
import type { TopLevelFormatterParams } from "echarts/types/dist/shared";
import EChart from "../../components/EChart";
import {
  AXIS_STYLE,
  BASE_CHART_OPTION,
  CHART_GRID,
  CHART_SPLIT_NUMBER,
  COMPARE_COLOR,
  INK_COLOR,
  METRIC_COLORS,
  X_AXIS_STYLE,
} from "../../components/chartTheme";
import { formatNumber } from "../../utils/formatNumber";
import { toDeltaSeries } from "./bodyCompositionDelta";
import type { BodyCompositionSeriesPoint, BodyCompositionTrend } from "../../types";

interface BodyCompositionChartProps {
  data: BodyCompositionTrend;
}

const WEIGHT_SERIES = "体重";
const FAT_SERIES = "体脂肪";
const LEAN_SERIES = "除脂肪";

const WEIGHT_COLOR = INK_COLOR;
const FAT_COLOR = METRIC_COLORS.fat_mass;
const LEAN_COLOR = METRIC_COLORS.lean_mass;

/** The kg fields of a series point (excludes `date`). */
type KgField = "weight_kg" | "fat_mass" | "lean_mass";

/** Field on a series point each named series reads its actual (non-delta)
 *  value from, for the tooltip. */
const ACTUAL_FIELD: Record<string, KgField> = {
  [WEIGHT_SERIES]: "weight_kg",
  [LEAN_SERIES]: "lean_mass",
  [FAT_SERIES]: "fat_mass",
};

/**
 * Chart height on `/condition`: the Morning Brief spec (§7) sizes this chart
 * at 160, shorter than the shared `CHART_HEIGHT` (180) Performance charts use
 * (Issue #1167). Kept local so Performance's constant is untouched.
 */
const CONDITION_CHART_HEIGHT = 160;

/** Signed kg string, e.g. -1.2kg / +0.3kg / —. */
function signedKg(value: number | null): string {
  if (value == null) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatNumber(value)}kg`;
}

/**
 * "体重 78.2kg（-1.8）": the actual reading plus the change it represents,
 * since the plotted value is the change itself (Issue #1167).
 */
function deltaTooltipFormatter(
  series: BodyCompositionSeriesPoint[],
): (params: TopLevelFormatterParams) => string {
  return (params) => {
    const list = Array.isArray(params) ? params : [params];
    const header =
      (list[0] as { axisValueLabel?: string })?.axisValueLabel ?? "";
    const rows = list
      .map((p) => {
        const param = p as {
          seriesName?: string;
          marker?: string;
          value?: unknown;
          dataIndex?: number;
        };
        const name = param.seriesName ?? "";
        const point =
          param.dataIndex != null ? series[param.dataIndex] : undefined;
        const field = ACTUAL_FIELD[name];
        const actual = point && field ? point[field] : null;
        const delta = typeof param.value === "number" ? param.value : null;
        return `${param.marker ?? ""}${name} ${formatNumber(actual)}kg（${formatNumber(delta)}）`;
      })
      .join("<br/>");
    return header ? `${header}<br/>${rows}` : rows;
  };
}

export default function BodyCompositionChart({
  data,
}: BodyCompositionChartProps) {
  const { series, change } = data;

  const option = useMemo(() => {
    const deltas = toDeltaSeries(series);
    return {
      ...BASE_CHART_OPTION,
      grid: { ...CHART_GRID },
      tooltip: {
        trigger: "axis" as const,
        formatter: deltaTooltipFormatter(series),
      },
      // No legend box: the readings above carry the color key, so the legend
      // would only repeat them — and, being laid out below the grid, it used
      // to sit on top of the bars and the date labels (Issue #1148).
      xAxis: {
        type: "category" as const,
        data: series.map((p) => p.date),
        ...X_AXIS_STYLE,
      },
      // Absolute kg buries the ~2kg period movement in the body's own mass
      // (under 3% of a 50-90kg axis). Plotting each series as its change from
      // the window's first reading puts all three on one 0-anchored scale, so
      // the slope — not the altitude — carries the story (Issue #1167).
      yAxis: {
        type: "value" as const,
        name: "変化量 (kg)",
        scale: true,
        splitNumber: CHART_SPLIT_NUMBER,
        ...AXIS_STYLE,
      },
      series: [
        {
          name: WEIGHT_SERIES,
          type: "line" as const,
          itemStyle: { color: WEIGHT_COLOR },
          lineStyle: { color: WEIGHT_COLOR },
          data: deltas.weight,
          // Hairline at zero: every line starts there by construction, so it
          // marks "no change yet" rather than a threshold.
          markLine: {
            silent: true,
            symbol: "none" as const,
            lineStyle: { color: COMPARE_COLOR, type: "dotted" as const },
            label: { show: false },
            data: [{ yAxis: 0 }],
          },
        },
        {
          name: LEAN_SERIES,
          type: "line" as const,
          itemStyle: { color: LEAN_COLOR },
          lineStyle: { color: LEAN_COLOR },
          data: deltas.lean,
        },
        {
          name: FAT_SERIES,
          type: "line" as const,
          itemStyle: { color: FAT_COLOR },
          lineStyle: { color: FAT_COLOR },
          data: deltas.fat,
        },
      ],
    };
  }, [series]);

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
        height={CONDITION_CHART_HEIGHT}
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
