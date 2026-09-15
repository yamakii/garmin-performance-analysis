import { useMemo } from "react";
import EChart from "../../components/EChart";
import {
  AXIS_STYLE,
  BASE_CHART_OPTION,
  METRIC_COLORS,
  X_AXIS_STYLE,
} from "../../components/chartTheme";
import {
  axisTooltipFormatter,
  formatNumber,
  formatSigned,
} from "../../utils/formatNumber";
import type { WeightEconomyCoupling } from "../../types";
import { BLOCK_SUMMARY_CLASS, BlockEmpty, CHART_HEIGHT } from "./blockShell";

interface WeightEconomyChartProps {
  data: WeightEconomyCoupling;
}

const WEIGHT_SERIES = "体重 (kg)";
const EF_SERIES = "EF (易ラン)";

const WEIGHT_COLOR = METRIC_COLORS.weight;
const EF_COLOR = METRIC_COLORS.ef;

/**
 * "体重 78.8kg · EF 0.0181 · 約5kg減 → +0.0022 EF (易ラン6本)" — the latest
 * pairing and the effect size fitted across the window. The effect size can be
 * negative (a lighter athlete fitted as less economical), so its sign comes
 * from the formatter, not from the template.
 */
export function weightEconomySummaryLine(data: WeightEconomyCoupling): string {
  const latest = data.series.at(-1) ?? null;
  const parts: string[] = [];
  if (latest?.weight_kg != null) {
    parts.push(`体重 ${formatNumber(latest.weight_kg, 1)}kg`);
  }
  if (latest?.ef != null) {
    parts.push(`EF ${formatNumber(latest.ef, 4)}`);
  }
  if (data.model != null) {
    parts.push(
      `約5kg減 → ${formatSigned(data.model.delta_ef_per_5kg_loss, 4)} EF (易ラン${data.model.n}本)`,
    );
  }
  return parts.join(" · ");
}

export default function WeightEconomyChart({ data }: WeightEconomyChartProps) {
  const { series, model, note } = data;

  const option = useMemo(
    () => ({
      ...BASE_CHART_OPTION,
      tooltip: {
        trigger: "axis" as const,
        // EF moves in the 4th decimal, so it needs more precision than weight.
        formatter: axisTooltipFormatter({
          [WEIGHT_SERIES]: 1,
          [EF_SERIES]: 4,
        }),
      },
      xAxis: {
        type: "category" as const,
        data: series.map((p) => p.run_date),
        ...X_AXIS_STYLE,
      },
      // Each axis name is painted in its series' color so the reader can tell
      // at a glance which scale a line belongs to (Issue #913); the coloured
      // names are the labels, so the chart needs no legend box.
      yAxis: [
        {
          type: "value" as const,
          name: "kg",
          nameTextStyle: { color: WEIGHT_COLOR },
          scale: true,
          ...AXIS_STYLE,
        },
        {
          type: "value" as const,
          name: "EF",
          nameTextStyle: { color: EF_COLOR },
          scale: true,
          ...AXIS_STYLE,
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: WEIGHT_SERIES,
          type: "line" as const,
          yAxisIndex: 0,
          smooth: true,
          connectNulls: false,
          itemStyle: { color: WEIGHT_COLOR },
          lineStyle: { color: WEIGHT_COLOR },
          data: series.map((p) => p.weight_kg),
        },
        {
          name: EF_SERIES,
          type: "line" as const,
          yAxisIndex: 1,
          smooth: true,
          connectNulls: false,
          itemStyle: { color: EF_COLOR },
          lineStyle: { color: EF_COLOR },
          data: series.map((p) => p.ef),
        },
      ],
    }),
    [series],
  );

  if (model == null && series.length === 0) {
    return (
      <BlockEmpty message="易しいランと体重を結び付けられるデータがまだ不足しています" />
    );
  }
  return (
    <div className="flex flex-col gap-3">
      <p className={BLOCK_SUMMARY_CLASS}>{weightEconomySummaryLine(data)}</p>
      {model != null && model.collinearity_flag && (
        <p
          role="alert"
          className="rounded-md border border-warn-line bg-warn-tint px-3 py-2 text-xs text-status-warn"
        >
          共線性のため、これは関連であってクリーンな因果係数ではありません。
          {note ? `（${note}）` : ""}
        </p>
      )}
      <EChart
        option={option}
        ariaLabel="体重とEF（易ラン）の二軸推移グラフ"
        height={CHART_HEIGHT}
      />
    </div>
  );
}
