import { useMemo } from "react";
import EChart from "../../components/EChart";
import type { EfficiencyTrendPoint } from "../../api/trends";

interface EfficiencyBlockProps {
  data: EfficiencyTrendPoint[];
}

const ZONE_KEYS = [
  "zone1_percentage",
  "zone2_percentage",
  "zone3_percentage",
  "zone4_percentage",
  "zone5_percentage",
] as const;

export default function EfficiencyBlock({ data }: EfficiencyBlockProps) {
  const option = useMemo(
    () => ({
      tooltip: { trigger: "axis" as const },
      legend: { data: ZONE_KEYS.map((_, i) => `Zone ${i + 1}`) },
      xAxis: { type: "category" as const, data: data.map((p) => p.date) },
      yAxis: { type: "value" as const, name: "%", max: 100 },
      series: ZONE_KEYS.map((key, i) => ({
        name: `Zone ${i + 1}`,
        type: "bar" as const,
        stack: "zones",
        data: data.map((p) => p[key]),
      })),
    }),
    [data],
  );

  return (
    <section aria-label="効率">
      <h2>効率推移 (HRゾーン分布)</h2>
      {data.length === 0 ? (
        <p>データがありません</p>
      ) : (
        <EChart option={option} ariaLabel="HRゾーン分布の積み上げ棒グラフ" />
      )}
    </section>
  );
}
