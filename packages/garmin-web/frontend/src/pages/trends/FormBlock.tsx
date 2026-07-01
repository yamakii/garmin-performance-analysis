import { useMemo } from "react";
import EChart from "../../components/EChart";
import {
  buildDeltaChartOption,
  buildScoreChartOption,
} from "./formChartOptions";
import type { FormTrendPoint } from "../../api/trends";

interface FormBlockProps {
  data: FormTrendPoint[];
}

export default function FormBlock({ data }: FormBlockProps) {
  // Two stacked panels: score (1-5, the primary read) on top, form deltas
  // (%/cm, robust-bounded) below. Overlaying both on one plot made the line
  // crossings meaningless (Issue #691), so each gets its own axis + option.
  const scoreOption = useMemo(() => buildScoreChartOption(data), [data]);
  const deltaOption = useMemo(() => buildDeltaChartOption(data), [data]);

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
        <div className="space-y-4">
          <div>
            <h3 className="mb-1 text-sm font-medium text-slate-600">
              フォームスコア (1〜5)
            </h3>
            <EChart
              option={scoreOption}
              ariaLabel="フォームスコアの折れ線グラフ"
              height={220}
            />
          </div>
          <div>
            <h3 className="mb-1 text-sm font-medium text-slate-600">
              フォーム偏差 (Δ)
            </h3>
            <EChart
              option={deltaOption}
              ariaLabel="フォーム偏差の折れ線グラフ"
              height={220}
            />
          </div>
        </div>
      )}
    </section>
  );
}
