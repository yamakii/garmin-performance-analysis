import { useMemo } from "react";
import EChart from "../../components/EChart";
import {
  buildDeltaChartOption,
  buildScoreChartOption,
} from "./formChartOptions";
import type { FormTrendPoint } from "../../api/trends";
import { BLOCK_SUMMARY_CLASS, BlockEmpty, CHART_HEIGHT } from "./blockShell";

interface FormBlockProps {
  data: FormTrendPoint[];
}

/** "±0.4" — a delta that always states its sign, or "—" when missing. */
function delta(value: number | null, unit: string): string {
  if (value == null) {
    return "—";
  }
  const sign = value > 0 ? "+" : value < 0 ? "-" : "±";
  return `${sign}${Math.abs(value).toFixed(1)}${unit}`;
}

/** "スコア 4.2 · GCT +2.5% · VO +0.4cm · VR +0.3%" — the latest run's form. */
export function formSummaryLine(data: FormTrendPoint[]): string {
  const latest = data[data.length - 1] ?? null;
  if (latest == null) {
    return "";
  }
  const score =
    latest.overall_score != null ? latest.overall_score.toFixed(1) : "—";
  return [
    `スコア ${score}`,
    `GCT ${delta(latest.gct_delta, "%")}`,
    `VO ${delta(latest.vo_delta, "cm")}`,
    `VR ${delta(latest.vr_delta, "%")}`,
  ].join(" · ");
}

export default function FormBlock({ data }: FormBlockProps) {
  // Two stacked panels: score (1-5, the primary read) on top, form deltas
  // (%/cm, robust-bounded) below. Overlaying both on one plot made the line
  // crossings meaningless (Issue #691), so each gets its own axis + option.
  const scoreOption = useMemo(() => buildScoreChartOption(data), [data]);
  const deltaOption = useMemo(() => buildDeltaChartOption(data), [data]);

  if (data.length === 0) {
    return <BlockEmpty message="データがありません" />;
  }
  return (
    <div className="flex flex-col gap-4">
      <p className={BLOCK_SUMMARY_CLASS}>{formSummaryLine(data)}</p>
      <div className="flex flex-col gap-1">
        <p className="font-mono text-xs text-ink-muted">
          フォームスコア (1〜5)
        </p>
        <EChart
          option={scoreOption}
          ariaLabel="フォームスコアの折れ線グラフ"
          height={CHART_HEIGHT}
        />
      </div>
      <div className="flex flex-col gap-1">
        <p className="font-mono text-xs text-ink-muted">フォーム偏差 (Δ)</p>
        <EChart
          option={deltaOption}
          ariaLabel="フォーム偏差の折れ線グラフ"
          height={CHART_HEIGHT}
        />
      </div>
    </div>
  );
}
