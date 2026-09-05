import type { JSX } from "react";
import type { TrainingBlock } from "../../types";
import { formatDate } from "../../utils/format";

/**
 * Phase → band styling. Building phases carry the brand signal, easing phases
 * take the 注意 tint and a race takes the 悪 tint (it is the deadline, not a
 * problem — the tint marks it as the fixed point everything bends around).
 * No new colour tokens: every band reuses an existing one (#911).
 */
const PHASE_STYLE: Record<string, string> = {
  base: "border-signal/40 bg-signal/5 text-ink",
  build: "border-signal/40 bg-signal/5 text-ink",
  peak: "border-signal/40 bg-signal/5 text-ink",
  cutback: "border-status-warn/30 bg-status-warn/10 text-status-warn",
  recovery: "border-status-warn/30 bg-status-warn/10 text-status-warn",
  taper: "border-status-warn/30 bg-status-warn/10 text-status-warn",
  race: "border-status-bad/30 bg-status-bad/10 text-status-bad",
};

const PHASE_LABEL: Record<string, string> = {
  base: "ベース",
  build: "ビルド",
  peak: "ピーク",
  cutback: "カットバック",
  recovery: "リカバリー",
  taper: "テーパー",
  race: "レース",
};

export function phaseStyle(phase: string | null): string {
  return PHASE_STYLE[phase ?? ""] ?? "border-slate-200 bg-slate-50 text-ink";
}

export function phaseLabel(phase: string | null): string {
  return PHASE_LABEL[phase ?? ""] ?? (phase ?? "-");
}

/**
 * The training blocks the month sits inside, as a band strip above the grid.
 *
 * The grid answers "what happens on each day"; the bands answer "which part of
 * the season those days belong to" — phase, span, weight mode and the quality
 * budget the week is allowed to spend.
 */
export default function BlockBands({
  blocks,
}: {
  blocks: TrainingBlock[];
}): JSX.Element | null {
  if (blocks.length === 0) {
    return null;
  }
  return (
    <ul aria-label="トレーニングブロック" className="space-y-2">
      {blocks.map((block) => (
        <li
          key={block.block_id}
          className={`flex flex-wrap items-baseline gap-x-3 gap-y-1 rounded-lg border-l-4 px-3 py-2 ${phaseStyle(
            block.phase,
          )}`}
        >
          <span className="text-xs font-bold tracking-wide">
            {phaseLabel(block.phase)}
          </span>
          <span className="font-display text-sm font-semibold text-ink">
            {block.title ?? "-"}
          </span>
          <span className="font-numeric text-xs tabular-nums text-slate-600">
            {formatDate(block.start_date)} 〜 {formatDate(block.end_date)}
          </span>
          {block.quality_sessions_per_week != null && (
            <span className="text-xs text-slate-600">
              ポイント練 週{block.quality_sessions_per_week}回
            </span>
          )}
          {block.weight_mode != null && (
            <span className="text-xs text-slate-600">
              体重 {block.weight_mode}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}
