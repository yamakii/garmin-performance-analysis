import { useMemo } from "react";
import EChart from "../../components/EChart";
import {
  AXIS_STYLE,
  BASE_CHART_OPTION,
  INK_COLOR,
  METRIC_COLORS,
} from "../../components/chartTheme";
import type { PhysiologyTrend } from "../../api/trends";

interface PhysiologyBlockProps {
  data: PhysiologyTrend;
}

export default function PhysiologyBlock({ data }: PhysiologyBlockProps) {
  const option = useMemo(
    () => ({
      ...BASE_CHART_OPTION,
      tooltip: { trigger: "axis" as const },
      legend: { data: ["VO2max", "LT心拍"] },
      xAxis: {
        type: "category" as const,
        data: data.vo2max.map((p) => p.date),
        ...AXIS_STYLE,
      },
      yAxis: [
        { type: "value" as const, name: "VO2max", scale: true, ...AXIS_STYLE },
        {
          type: "value" as const,
          name: "LT心拍 (bpm)",
          scale: true,
          ...AXIS_STYLE,
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: "VO2max",
          type: "line" as const,
          itemStyle: { color: INK_COLOR },
          lineStyle: { color: INK_COLOR },
          data: data.vo2max.map((p) => p.value),
        },
        {
          name: "LT心拍",
          type: "line" as const,
          yAxisIndex: 1,
          itemStyle: { color: METRIC_COLORS.heart_rate },
          lineStyle: { color: METRIC_COLORS.heart_rate },
          data: data.lactate_threshold.map((p) => [p.date, p.heart_rate]),
        },
      ],
    }),
    [data],
  );

  const latestVo2max = data.vo2max.at(-1);
  const isEmpty =
    data.vo2max.length === 0 && data.lactate_threshold.length === 0;

  return (
    <section
      aria-label="生理指標"
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <h2 className="mb-3 font-display text-base font-semibold text-ink">
        生理指標 (VO2max / 乳酸閾値)
      </h2>
      {isEmpty ? (
        <p className="py-8 text-center text-sm text-slate-500">
          データがありません
        </p>
      ) : (
        <>
          {latestVo2max?.value != null && (
            <p className="mb-2 text-sm text-slate-600">
              最新VO2max: {latestVo2max.value.toFixed(1)} ({latestVo2max.date})
            </p>
          )}
          <EChart option={option} ariaLabel="VO2maxと乳酸閾値の折れ線グラフ" />
        </>
      )}
    </section>
  );
}
