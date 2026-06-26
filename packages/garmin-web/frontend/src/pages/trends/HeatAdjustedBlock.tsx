import { useMemo } from "react";
import EChart from "../../components/EChart";
import {
  AXIS_STYLE,
  BASE_CHART_OPTION,
  METRIC_COLORS,
} from "../../components/chartTheme";
import type { HeatAdjustedTrend } from "../../api/trends";

interface HeatAdjustedBlockProps {
  data: HeatAdjustedTrend;
}

const RAW_HR_SERIES = "生HR";
const NEUTRAL_HR_SERIES = "気候中立HR";
const HEAT_COST_SERIES = "heat_cost (bpm)";

/** Neutral HR uses the editorial ink navy; heat_cost uses a warm amber. */
const NEUTRAL_COLOR = "#16213a";
const HEAT_COST_COLOR = "#d97706";

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
      tooltip: { trigger: "axis" as const },
      legend: { data: [RAW_HR_SERIES, NEUTRAL_HR_SERIES, HEAT_COST_SERIES] },
      xAxis: {
        type: "category" as const,
        data: points.map((p) => p.date),
        ...AXIS_STYLE,
      },
      yAxis: [
        { type: "value" as const, name: "bpm", scale: true, ...AXIS_STYLE },
        { type: "value" as const, name: "heat_cost", ...AXIS_STYLE },
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
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
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
            (破線) の重ね描き。暑熱係数{" "}
            <span className="font-semibold text-ink">
              β_heat {formatBpmPerC(coefficients?.beta_heat)} bpm/°C
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
