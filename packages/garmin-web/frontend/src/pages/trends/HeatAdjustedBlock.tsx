import { useMemo } from "react";
import EChart from "../../components/EChart";
import {
  AXIS_STYLE,
  BASE_CHART_OPTION,
  INK_COLOR,
  METRIC_COLORS,
} from "../../components/chartTheme";
import { axisTooltipFormatter } from "../../utils/formatNumber";
import type { HeatAdjustedTrend } from "../../api/trends";
import { CARD_CLASS } from "../../components/Card";

interface HeatAdjustedBlockProps {
  data: HeatAdjustedTrend;
}

const RAW_HR_SERIES = "生HR";
const NEUTRAL_HR_SERIES = "気候中立HR";
/** Japanese label: "heat_cost" is an internal column name, not reader-facing. */
const HEAT_COST_SERIES = "暑熱コスト (bpm)";

/** Neutral HR uses the editorial ink navy; heat_cost its own warm orange. */
const NEUTRAL_COLOR = INK_COLOR;
const HEAT_COST_COLOR = METRIC_COLORS.heat_cost;

function formatBpmPerC(value: number | null | undefined): string {
  return value == null ? "—" : value.toFixed(2);
}

function formatTemp(value: number | null | undefined): string {
  return value == null ? "—" : `${value.toFixed(0)}°C`;
}

export default function HeatAdjustedBlock({ data }: HeatAdjustedBlockProps) {
  const { points, coefficients, status } = data;

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
      legend: { data: [RAW_HR_SERIES, NEUTRAL_HR_SERIES, HEAT_COST_SERIES] },
      xAxis: {
        type: "category" as const,
        data: points.map((p) => p.date),
        ...AXIS_STYLE,
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
        },
      ],
      series: [
        {
          name: RAW_HR_SERIES,
          type: "line" as const,
          itemStyle: { color: METRIC_COLORS.heart_rate },
          lineStyle: { color: METRIC_COLORS.heart_rate },
          data: points.map((p) => p.raw_hr),
        },
        {
          name: NEUTRAL_HR_SERIES,
          type: "line" as const,
          itemStyle: { color: NEUTRAL_COLOR },
          // Dashed line distinguishes the climate-neutral (reprojected) HR.
          lineStyle: { color: NEUTRAL_COLOR, type: "dashed" as const },
          data: points.map((p) => p.neutral_hr),
        },
        {
          name: HEAT_COST_SERIES,
          type: "bar" as const,
          yAxisIndex: 1,
          itemStyle: { color: HEAT_COST_COLOR, opacity: 0.4 },
          data: points.map((p) => p.heat_cost),
        },
      ],
    };
  }, [points]);

  const isEmpty = status !== "ok" || points.length === 0;

  return (
    <section
      aria-label="気候中立HRトレンド (暑熱補正)"
      className={CARD_CLASS}
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="font-display text-base font-semibold text-ink">
          気候中立HRトレンド (暑熱補正)
        </h2>
      </div>
      {isEmpty ? (
        <p className="py-8 text-center text-sm text-slate-500">
          暑熱補正トレンドを算出するにはランが不足しています
        </p>
      ) : (
        <>
          <p className="mb-1 text-sm text-slate-600">
            <span className="font-semibold text-ink">{RAW_HR_SERIES}</span>{" "}
            (実線) と{" "}
            <span className="font-semibold text-ink">{NEUTRAL_HR_SERIES}</span>{" "}
            (破線) の重ね描き。暑熱コスト係数{" "}
            <span className="font-semibold text-ink">
              {formatBpmPerC(coefficients?.beta_heat)} bpm/°C
            </span>{" "}
            ・ 基準温度 {formatTemp(coefficients?.ref_temp_c)}
          </p>
          <EChart
            option={option}
            ariaLabel="生HRと気候中立HRの推移グラフ"
          />
        </>
      )}
    </section>
  );
}
