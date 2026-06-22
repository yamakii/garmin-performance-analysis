import { useMemo } from "react";
import EChart from "../../components/EChart";
import {
  AXIS_STYLE,
  BASE_CHART_OPTION,
  ZONE_COLORS,
} from "../../components/chartTheme";
import { axisTooltipFormatter } from "../../utils/formatNumber";
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
      ...BASE_CHART_OPTION,
      tooltip: {
        trigger: "axis" as const,
        formatter: axisTooltipFormatter({}),
      },
      legend: { data: ZONE_KEYS.map((_, i) => `Zone ${i + 1}`) },
      xAxis: {
        type: "category" as const,
        data: data.map((p) => p.date),
        ...AXIS_STYLE,
      },
      yAxis: { type: "value" as const, name: "%", max: 100, ...AXIS_STYLE },
      series: ZONE_KEYS.map((key, i) => ({
        name: `Zone ${i + 1}`,
        type: "bar" as const,
        stack: "zones",
        itemStyle: { color: ZONE_COLORS[i] },
        data: data.map((p) => p[key]),
      })),
    }),
    [data],
  );

  return (
    <section
      aria-label="効率"
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <h2 className="mb-3 font-display text-base font-semibold text-ink">
        効率推移 (HRゾーン分布)
      </h2>
      {data.length === 0 ? (
        <p className="py-8 text-center text-sm text-slate-500">
          データがありません
        </p>
      ) : (
        <EChart option={option} ariaLabel="HRゾーン分布の積み上げ棒グラフ" />
      )}
    </section>
  );
}
