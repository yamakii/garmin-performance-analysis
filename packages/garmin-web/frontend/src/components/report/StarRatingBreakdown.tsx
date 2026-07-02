import type { JSX } from "react";
import { META_LABEL } from "./ReportCard";

/**
 * Japanese labels for the weighted-rating axes emitted by the star-weighting
 * feature (Issue #706). Covers every axis set the agents produce:
 * environment, summary, and the three phase categories. Unknown keys fall
 * through to the raw key (graceful degradation for schema evolution).
 */
const AXIS_LABELS: Record<string, string> = {
  // environment
  temperature: "気温",
  humidity: "湿度",
  terrain: "地形",
  wind: "風",
  // summary (4-axis)
  form_efficiency: "フォーム効率",
  pace_consistency: "ペース安定性",
  hr_management: "心拍管理",
  execution_quality: "実行品質",
  // phase: low_moderate
  hr_control: "心拍コントロール",
  pace_stability: "ペース安定性",
  form: "フォーム",
  // phase: tempo_threshold
  target_pace: "目標ペース",
  // phase: interval_sprint
  work_intensity: "運動強度",
  recovery_quality: "リカバリー品質",
  structure: "構成",
};

const MAX_SCORE = 5;

function asRecord(value: unknown): Record<string, unknown> | null {
  return value != null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function asFiniteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** One axis row: label, a proportional score bar, the score, and its weight. */
function AxisRow({
  axisKey,
  score,
  weight,
}: {
  axisKey: string;
  score: number;
  weight: number | null;
}) {
  const label = AXIS_LABELS[axisKey] ?? axisKey;
  const pct = Math.min(100, Math.max(0, (score / MAX_SCORE) * 100));
  return (
    <div className="flex items-center gap-3">
      <span className="w-24 shrink-0 text-sm text-slate-700">{label}</span>
      <span
        aria-hidden="true"
        className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100"
      >
        <span
          className="block h-full rounded-full bg-gold"
          style={{ width: `${pct}%` }}
        />
      </span>
      <span className="w-10 shrink-0 text-right text-sm font-semibold tabular-nums text-slate-700">
        {score.toFixed(1)}
      </span>
      {weight != null && (
        <span className="w-12 shrink-0 text-right text-xs tabular-nums text-slate-400">
          {Math.round(weight * 100)}%
        </span>
      )}
    </div>
  );
}

/**
 * Renders the weighted star-rating breakdown object (Issue #706):
 *
 *     { axis_scores: { <axis>: 0-5 }, weights: { <axis>: 0-1 }, star_rating: 0-5 }
 *
 * Each axis is shown with a Japanese label, a proportional bar, its score and
 * weight; the weighted total star is shown as a footer unless `showTotal` is
 * false (the summary section already shows the same value in its hero rating).
 * Returns null when the payload is not a usable breakdown object — the caller
 * keeps letting FallbackFields handle genuinely unknown shapes.
 */
export default function StarRatingBreakdown({
  data,
  showTotal = true,
}: {
  data: unknown;
  showTotal?: boolean;
}): JSX.Element | null {
  const breakdown = asRecord(data);
  if (!breakdown) {
    return null;
  }
  const axisScores = asRecord(breakdown.axis_scores);
  if (!axisScores) {
    return null;
  }
  const weights = asRecord(breakdown.weights);
  const rows = Object.entries(axisScores)
    .map(([axisKey, rawScore]) => {
      const score = asFiniteNumber(rawScore);
      if (score == null) {
        return null;
      }
      return { axisKey, score, weight: asFiniteNumber(weights?.[axisKey]) };
    })
    .filter((row): row is NonNullable<typeof row> => row != null);
  if (rows.length === 0) {
    return null;
  }
  const total = asFiniteNumber(breakdown.star_rating);
  return (
    <div className="rounded-lg bg-slate-50 p-4">
      <h3 className={META_LABEL}>評価内訳</h3>
      <div className="mt-2 space-y-2">
        {rows.map((row) => (
          <AxisRow
            key={row.axisKey}
            axisKey={row.axisKey}
            score={row.score}
            weight={row.weight}
          />
        ))}
      </div>
      {showTotal && total != null && (
        <div className="mt-3 flex items-center justify-between border-t border-slate-200 pt-2">
          <span className="text-sm font-medium text-slate-600">加重総合</span>
          <span className="rounded-full bg-gold/10 px-2 py-0.5 text-xs font-semibold tabular-nums text-gold">
            {total.toFixed(1)} / {MAX_SCORE.toFixed(1)}
          </span>
        </div>
      )}
    </div>
  );
}
