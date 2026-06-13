import { useMemo } from "react";
import EChart from "../../components/EChart";
import {
  AXIS_STYLE,
  BASE_CHART_OPTION,
  FORM_LINE_COLORS,
} from "../../components/chartTheme";
import type { FormTrendPoint } from "../../api/trends";

interface FormBlockProps {
  data: FormTrendPoint[];
}

export default function FormBlock({ data }: FormBlockProps) {
  const option = useMemo(
    () => ({
      ...BASE_CHART_OPTION,
      // Overall = ink, form deltas = violet family (Issue #214).
      color: FORM_LINE_COLORS,
      tooltip: { trigger: "axis" as const },
      legend: { data: ["総合スコア", "GCT Δ%", "VO Δcm", "VR Δ%"] },
      xAxis: {
        type: "category" as const,
        data: data.map((p) => p.date),
        ...AXIS_STYLE,
      },
      yAxis: { type: "value" as const, scale: true, ...AXIS_STYLE },
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
    <section
      aria-label="フォーム"
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <h2 className="mb-3 font-display text-base font-semibold text-ink">
        フォームスコア推移
      </h2>
      {data.length === 0 ? (
        <p className="py-8 text-center text-sm text-slate-500">
          データがありません
        </p>
      ) : (
        <EChart option={option} ariaLabel="フォーム評価の折れ線グラフ" />
      )}
    </section>
  );
}
