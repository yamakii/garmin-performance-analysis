import { useMemo } from "react";
import EChart from "../../components/EChart";
import type { PhysiologyTrend } from "../../api/trends";

interface PhysiologyBlockProps {
  data: PhysiologyTrend;
}

export default function PhysiologyBlock({ data }: PhysiologyBlockProps) {
  const option = useMemo(
    () => ({
      tooltip: { trigger: "axis" as const },
      legend: { data: ["VO2max", "LT心拍"] },
      xAxis: { type: "category" as const, data: data.vo2max.map((p) => p.date) },
      yAxis: [
        { type: "value" as const, name: "VO2max", scale: true },
        { type: "value" as const, name: "LT心拍 (bpm)", scale: true },
      ],
      series: [
        {
          name: "VO2max",
          type: "line" as const,
          data: data.vo2max.map((p) => p.value),
        },
        {
          name: "LT心拍",
          type: "line" as const,
          yAxisIndex: 1,
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
    <section aria-label="生理指標">
      <h2>生理指標 (VO2max / 乳酸閾値)</h2>
      {isEmpty ? (
        <p>データがありません</p>
      ) : (
        <>
          {latestVo2max?.value != null && (
            <p>
              最新VO2max: {latestVo2max.value.toFixed(1)} ({latestVo2max.date})
            </p>
          )}
          <EChart option={option} ariaLabel="VO2maxと乳酸閾値の折れ線グラフ" />
        </>
      )}
    </section>
  );
}
