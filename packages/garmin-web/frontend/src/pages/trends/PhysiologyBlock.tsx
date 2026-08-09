import { useMemo } from "react";
import EChart from "../../components/EChart";
import {
  AXIS_STYLE,
  BASE_CHART_OPTION,
  METRIC_COLORS,
} from "../../components/chartTheme";
import { axisTooltipFormatter } from "../../utils/formatNumber";
import type { PhysiologyTrend } from "../../api/trends";
import { CARD_CLASS } from "../../components/Card";

interface PhysiologyBlockProps {
  data: PhysiologyTrend;
}

export default function PhysiologyBlock({ data }: PhysiologyBlockProps) {
  const option = useMemo(
    () => ({
      ...BASE_CHART_OPTION,
      tooltip: {
        trigger: "axis" as const,
        formatter: axisTooltipFormatter({ VO2max: 1, LT心拍: 0 }),
      },
      legend: { data: ["VO2max", "LT心拍"] },
      xAxis: {
        type: "category" as const,
        data: data.vo2max.map((p) => p.date),
        ...AXIS_STYLE,
      },
      // Each axis name is painted in its series' color so the reader can tell
      // at a glance which scale a line belongs to (Issue #913).
      yAxis: [
        {
          type: "value" as const,
          name: "VO2max",
          nameTextStyle: { color: METRIC_COLORS.vo2max },
          scale: true,
          ...AXIS_STYLE,
        },
        {
          type: "value" as const,
          name: "LT心拍 (bpm)",
          nameTextStyle: { color: METRIC_COLORS.heart_rate },
          scale: true,
          ...AXIS_STYLE,
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: "VO2max",
          type: "line" as const,
          // Same token as ObjectiveFitnessBlock's Garmin VO2max line.
          itemStyle: { color: METRIC_COLORS.vo2max },
          lineStyle: { color: METRIC_COLORS.vo2max },
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
      className={CARD_CLASS}
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
