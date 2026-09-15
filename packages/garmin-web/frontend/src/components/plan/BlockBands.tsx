import type { JSX } from "react";
import type { TrainingBlock } from "../../types";
import { formatDateLabel } from "../../utils/format";

/**
 * Phase → band styling (Morning Brief, #1119; revised #1172). Fill is
 * reserved for exceptions: an easing phase takes the 注意 tint and a race
 * takes the 悪 tint — it is the deadline everything bends around, not a
 * problem. A building phase is the ordinary case, so it is an unfilled
 * well-tinted band with a ruled hairline border and ink text, not the
 * page's strongest element (#1172: the earlier `bg-ink` fill made routine
 * building weeks compete with the exceptions for attention). No new colour
 * tokens: every band reuses an existing one (#911).
 */
const PHASE_STYLE: Record<string, string> = {
  base: "border border-hairline bg-well text-ink",
  build: "border border-hairline bg-well text-ink",
  peak: "border border-hairline bg-well text-ink",
  cutback: "border border-warn-line bg-warn-tint text-status-warn",
  recovery: "border border-warn-line bg-warn-tint text-status-warn",
  taper: "border border-warn-line bg-warn-tint text-status-warn",
  race: "border border-bad-line bg-bad-tint text-status-bad",
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
  return PHASE_STYLE[phase ?? ""] ?? "border border-hairline text-ink-muted";
}

export function phaseLabel(phase: string | null): string {
  return PHASE_LABEL[phase ?? ""] ?? (phase ?? "-");
}

/** "08/24" — a day of the band caption, without its weekday. */
function shortDay(iso: string | null): string {
  return iso != null ? formatDateLabel(iso).slice(0, 5) : "";
}

/**
 * Where a block sits inside the days on screen, as 1-based grid columns.
 *
 * The band is drawn over the calendar, so it is clipped to the view: a block
 * that started in August begins at column 1 of a September grid and the band
 * simply runs off the left edge, which is what "we are mid-block" looks like.
 * A block with no visible day returns null rather than a zero-width band.
 */
export function bandSpan(
  block: TrainingBlock,
  days: string[],
): { start: number; span: number } | null {
  const first = days[0] ?? null;
  const last = days[days.length - 1] ?? null;
  if (first == null || last == null) {
    return null;
  }
  // An open-ended block covers everything on that side of the view.
  const start = block.start_date ?? first;
  const end = block.end_date ?? last;
  if (end < first || start > last) {
    return null;
  }
  const firstIndex = days.findIndex((day) => day >= start);
  let lastIndex = firstIndex;
  for (let i = days.length - 1; i >= 0; i -= 1) {
    if (days[i] <= end) {
      lastIndex = i;
      break;
    }
  }
  if (firstIndex < 0 || lastIndex < firstIndex) {
    return null;
  }
  return { start: firstIndex + 1, span: lastIndex - firstIndex + 1 };
}

/** "ビルド · 新潟マラソン ビルド · 08/24 – 10/11 · ポイント練 週2 · 体重 微減" */
function bandCaption(block: TrainingBlock): string {
  const parts = [phaseLabel(block.phase)];
  if (block.title != null && block.title !== "") {
    parts.push(block.title);
  }
  const range = [shortDay(block.start_date), shortDay(block.end_date)].filter(
    (day) => day !== "",
  );
  if (range.length > 0) {
    parts.push(range.join(" – "));
  }
  if (block.quality_sessions_per_week != null) {
    parts.push(`ポイント練 週${block.quality_sessions_per_week}`);
  }
  if (block.weight_mode != null && block.weight_mode !== "") {
    parts.push(`体重 ${block.weight_mode}`);
  }
  return parts.join(" · ");
}

/**
 * The training blocks the month sits inside, as bands over the grid.
 *
 * The grid answers "what happens on each day"; the bands answer "which part of
 * the season those days belong to". Sharing the grid's column geometry
 * (`96px` week header + seven day columns, subdivided by the days in view)
 * makes the answer positional: a band starts where its block starts, so the
 * reader sees a phase change land on a calendar day instead of reading a date
 * range and doing the arithmetic.
 */
export default function BlockBands({
  blocks,
  days,
}: {
  blocks: TrainingBlock[];
  /** Every day on screen, in display order — the grid's own day range. */
  days: string[];
}): JSX.Element | null {
  const bands = blocks
    .map((block) => ({ block, span: bandSpan(block, days) }))
    .filter(
      (band): band is { block: TrainingBlock; span: { start: number; span: number } } =>
        band.span != null,
    );
  if (bands.length === 0) {
    return null;
  }
  return (
    <ul aria-label="トレーニングブロック" className="flex flex-col gap-1">
      {bands.map(({ block, span }) => (
        <li
          key={block.block_id}
          className="grid grid-cols-[96px_repeat(7,minmax(0,1fr))]"
        >
          <div
            className="col-start-2 col-end-9 grid"
            style={{
              gridTemplateColumns: `repeat(${days.length}, minmax(0, 1fr))`,
            }}
          >
            {/*
             * A band is as wide as its block, not as its caption, so the
             * caption has to survive being narrower than its text: it is a
             * block box (not a flex row) so `text-ellipsis` applies, and the
             * full line stays reachable on hover (#1143).
             */}
            <div
              className={`block h-[22px] overflow-hidden rounded-sm px-2 font-mono text-[11px] leading-[22px] tracking-[0.02em] text-ellipsis whitespace-nowrap ${phaseStyle(
                block.phase,
              )}`}
              style={{ gridColumn: `${span.start} / span ${span.span}` }}
              title={bandCaption(block)}
            >
              {bandCaption(block)}
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}
