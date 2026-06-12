import { useMemo } from "react";
import EChart from "../../components/EChart";
import type { FormTrendPoint } from "../../api/trends";

interface FormBlockProps {
  data: FormTrendPoint[];
}

export default function FormBlock({ data }: FormBlockProps) {
  const option = useMemo(
    () => ({
      tooltip: { trigger: "axis" as const },
      legend: { data: ["総合スコア", "GCT Δ%", "VO Δcm", "VR Δ%"] },
      xAxis: { type: "category" as const, data: data.map((p) => p.date) },
      yAxis: { type: "value" as const, scale: true },
      series: [
        {
          name: "総合スコア",
          type: "line" as const,
          data: data.map((p) => p.overall_score),
        },
        {
          name: "GCT Δ%",
          type: "line" as const,
          data: data.map((p) => p.gct_delta),
        },
        {
          name: "VO Δcm",
          type: "line" as const,
          data: data.map((p) => p.vo_delta),
        },
        {
          name: "VR Δ%",
          type: "line" as const,
          data: data.map((p) => p.vr_delta),
        },
      ],
    }),
    [data],
  );

  return (
    <section aria-label="フォーム">
      <h2>フォームスコア推移</h2>
      {data.length === 0 ? (
        <p>データがありません</p>
      ) : (
        <EChart option={option} ariaLabel="フォーム評価の折れ線グラフ" />
      )}
    </section>
  );
}
