import { useMemo } from "react";
import EChart from "../../components/EChart";
import {
  AXIS_STYLE,
  BASE_CHART_OPTION,
  FORM_LINE_COLORS,
} from "../../components/chartTheme";
import { axisTooltipFormatter } from "../../utils/formatNumber";
import { robustAxisBounds } from "../../utils/robustBounds";
import type { FormTrendPoint } from "../../api/trends";

interface FormBlockProps {
  data: FormTrendPoint[];
}

export default function FormBlock({ data }: FormBlockProps) {
  const option = useMemo(() => {
    // Right axis carries the three form deltas. Their raw range is dominated by
    // rare VR Δ% outliers (e.g. +170%), so derive robust bounds that push those
    // off-screen while leaving the series data untouched (tooltips show reals).
    const deltaBounds = robustAxisBounds([
      ...data.map((p) => p.gct_delta),
      ...data.map((p) => p.vo_delta),
      ...data.map((p) => p.vr_delta),
    ]);

    return {
      ...BASE_CHART_OPTION,
      // Overall = ink, form deltas = violet family (Issue #214).
      color: FORM_LINE_COLORS,
      tooltip: {
        trigger: "axis" as const,
        formatter: axisTooltipFormatter({
          総合スコア: 1,
          "GCT Δ%": 1,
          "VO Δcm": 1,
          "VR Δ%": 1,
        }),
      },
      legend: { data: ["総合スコア", "GCT Δ%", "VO Δcm", "VR Δ%"] },
      xAxis: {
        type: "category" as const,
        data: data.map((p) => p.date),
        ...AXIS_STYLE,
      },
      yAxis: [
        // Left axis: overall score, fixed 1-5 so the trend stays readable.
        { type: "value" as const, min: 1, max: 5, ...AXIS_STYLE },
        // Right axis: form deltas on robust bounds (auto-scale if unavailable).
        {
          type: "value" as const,
          ...(deltaBounds
            ? { min: deltaBounds.min, max: deltaBounds.max }
            : { scale: true }),
          ...AXIS_STYLE,
          // Only the left axis draws horizontal grid lines to avoid clutter.
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: "総合スコア",
          type: "line" as const,
          yAxisIndex: 0,
          data: data.map((p) => p.overall_score),
        },
        {
          name: "GCT Δ%",
          type: "line" as const,
          yAxisIndex: 1,
          data: data.map((p) => p.gct_delta),
        },
        {
          name: "VO Δcm",
          type: "line" as const,
          yAxisIndex: 1,
          data: data.map((p) => p.vo_delta),
        },
        {
          name: "VR Δ%",
          type: "line" as const,
          yAxisIndex: 1,
          data: data.map((p) => p.vr_delta),
        },
      ],
    };
  }, [data]);

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
