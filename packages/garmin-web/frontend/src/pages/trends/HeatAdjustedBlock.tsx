import { useMemo } from "react";
import EChart from "../../components/EChart";
import {
  AXIS_STYLE,
  BASE_CHART_OPTION,
  COMPARE_COLOR,
  INK_COLOR,
  METRIC_COLORS,
  X_AXIS_STYLE,
} from "../../components/chartTheme";
import { axisTooltipFormatter } from "../../utils/formatNumber";
import type { HeatAdjustedTrend } from "../../api/trends";
import { BLOCK_SUMMARY_CLASS, BlockEmpty, CHART_HEIGHT } from "./blockShell";

interface HeatAdjustedBlockProps {
  data: HeatAdjustedTrend;
}

const RAW_HR_SERIES = "生HR";
const NEUTRAL_HR_SERIES = "気候中立HR";
/** Japanese label: "heat_cost" is an internal column name, not reader-facing. */
const HEAT_COST_SERIES = "暑熱コスト (bpm)";

/**
 * The climate-neutral line is the point of the block, so it takes the ink and
 * the raw HR it is corrected from takes the hairline compare color; the heat
 * cost keeps its own warm token because it scales a second axis.
 */
const NEUTRAL_COLOR = INK_COLOR;
const RAW_COLOR = COMPARE_COLOR;
const HEAT_COST_COLOR = METRIC_COLORS.heat_cost;

function formatBpmPerC(value: number | null | undefined): string {
  return value == null ? "—" : value.toFixed(2);
}

function formatTemp(value: number | null | undefined): string {
  return value == null ? "—" : `${value.toFixed(0)}°C`;
}

/**
 * "気候中立HR 145 · 生HR 150 · 暑熱コスト係数 0.35 bpm/°C · 基準 15°C" — the
 * latest corrected reading and the model that corrected it.
 */
export function heatAdjustedSummaryLine(data: HeatAdjustedTrend): string {
  const latest = data.points.at(-1) ?? null;
  const parts: string[] = [];
  if (latest?.neutral_hr != null) {
    parts.push(`${NEUTRAL_HR_SERIES} ${latest.neutral_hr.toFixed(0)}`);
  }
  if (latest?.raw_hr != null) {
    parts.push(`${RAW_HR_SERIES} ${latest.raw_hr.toFixed(0)}`);
  }
  parts.push(
    `暑熱コスト係数 ${formatBpmPerC(data.coefficients?.beta_heat)} bpm/°C`,
    `基準 ${formatTemp(data.coefficients?.ref_temp_c)}`,
  );
  return parts.join(" · ");
}

export default function HeatAdjustedBlock({ data }: HeatAdjustedBlockProps) {
  const { points, status } = data;

  const option = useMemo(() => {
    return {
      ...BASE_CHART_OPTION,
      tooltip: {
        trigger: "axis" as const,
        formatter: axisTooltipFormatter({
          [RAW_HR_SERIES]: 0,
          [NEUTRAL_HR_SERIES]: 1,
          [HEAT_COST_SERIES]: 1,
        }),
      },
      xAxis: {
        type: "category" as const,
        data: points.map((p) => p.date),
        ...X_AXIS_STYLE,
      },
      // The bpm axis carries both HR series, so it stays neutral; the second
      // axis takes the heat_cost color it exclusively scales (Issue #913).
      yAxis: [
        { type: "value" as const, name: "bpm", scale: true, ...AXIS_STYLE },
        {
          type: "value" as const,
          name: HEAT_COST_SERIES,
          nameTextStyle: { color: HEAT_COST_COLOR },
          ...AXIS_STYLE,
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: RAW_HR_SERIES,
          type: "line" as const,
          itemStyle: { color: RAW_COLOR },
          lineStyle: { color: RAW_COLOR },
          data: points.map((p) => p.raw_hr),
        },
        {
          name: NEUTRAL_HR_SERIES,
          type: "line" as const,
          itemStyle: { color: NEUTRAL_COLOR },
          lineStyle: { color: NEUTRAL_COLOR },
          data: points.map((p) => p.neutral_hr),
        },
        {
          name: HEAT_COST_SERIES,
          type: "bar" as const,
          yAxisIndex: 1,
          itemStyle: {
            color: HEAT_COST_COLOR,
            opacity: 0.4,
            borderRadius: 0,
          },
          data: points.map((p) => p.heat_cost),
        },
      ],
    };
  }, [points]);

  if (status !== "ok" || points.length === 0) {
    return (
      <BlockEmpty message="暑熱補正トレンドを算出するにはランが不足しています" />
    );
  }
  return (
    <div className="flex flex-col gap-3">
      <p className={BLOCK_SUMMARY_CLASS}>{heatAdjustedSummaryLine(data)}</p>
      <EChart
        option={option}
        ariaLabel="生HRと気候中立HRの推移グラフ"
        height={CHART_HEIGHT}
      />
    </div>
  );
}
