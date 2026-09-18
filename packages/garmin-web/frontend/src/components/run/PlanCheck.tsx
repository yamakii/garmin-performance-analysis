import type { JSX, ReactNode } from "react";
import SectionBlock from "../SectionBlock";
import type { HrCeiling, PlanCheckRow, RunPlan } from "../../types";
import { formatNumber } from "../../utils/formatNumber";

/** Japanese name per plan axis; an unknown axis keeps its own key. */
const AXIS_LABELS: Record<string, string> = {
  intensity: "強度",
  volume: "量",
  hr_ceiling: "心拍上限",
  rest: "休養",
};

/** Column order at `md` and up; below it each check stacks (see below). */
const COLUMNS = ["項目", "目標", "実績", "状態"];

/**
 * The four tracks at `md`+, fixed rather than content-sized.
 *
 * Header and rows are one grid — each row is `display: contents` inside it —
 * because a grid per row sizes its own columns off its own text, and the
 * result was 計画どおり sitting under 目標 and nothing at all under 状態
 * (#1270).
 */
const GRID_COLUMNS =
  "md:grid-cols-[96px_minmax(0,1fr)_minmax(0,1.5fr)_72px]";

/**
 * Cell chrome at `md`+: the row's own box is gone there, so the hairline and
 * the vertical rhythm belong to each cell.
 */
const CELL = "md:border-b md:border-hairline md:py-3 md:pr-3";

/**
 * "5:21" / "1:04:09" — how long the run spent above the cap.
 *
 * Minutes are unpadded: this is a length of time in prose, not a clock
 * reading, and "00:02" next to "上限 150" reads as a timestamp.
 */
export function formatOverTime(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = String(total % 60).padStart(2, "0");
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${secs}`
    : `${minutes}:${secs}`;
}

function StatusTag({ onPlan }: { onPlan: boolean }) {
  return (
    <span
      className={`font-mono text-xs whitespace-nowrap ${
        onPlan ? "text-ink-muted" : "font-bold text-status-warn"
      }`}
    >
      {onPlan ? "計画どおり" : "ずれ"}
    </span>
  );
}

/**
 * How much of the run sat above the prescribed ceiling, as a bar and a time.
 *
 * "心拍が高め" is an impression; "超過 5:21（12%）" is the same statement with a
 * size, and the size is what decides whether the run needs an answer. The bar
 * belongs to the 実績 cell because it *is* the actual reading of that axis.
 */
function OverCeilingBar({ ceiling }: { ceiling: HrCeiling }): JSX.Element {
  if (ceiling.seconds_over <= 0) {
    return <p className="mt-1 font-mono text-xs text-ink-muted">超過なし</p>;
  }
  return (
    <div className="mt-1.5 flex flex-col gap-1">
      <span
        aria-hidden="true"
        className="relative block h-1.5 w-full max-w-[180px] bg-well"
      >
        <span
          className="absolute inset-y-0 left-0 bg-status-warn"
          style={{ width: `${Math.min(100, ceiling.pct_over)}%` }}
        />
      </span>
      <span className="font-mono text-xs text-status-warn">
        超過 {formatOverTime(ceiling.seconds_over)}（
        {formatNumber(ceiling.pct_over, 1)}%）
      </span>
    </div>
  );
}

/** The label a stacked row prints in front of a value below `md`. */
function StackedLabel({ children }: { children: ReactNode }) {
  return (
    <span className="mr-1.5 font-mono text-xs text-ink-muted md:hidden">
      {children}
    </span>
  );
}

function CheckRow({
  check,
  ceiling,
}: {
  check: PlanCheckRow;
  ceiling: HrCeiling | null;
}): JSX.Element {
  const label = AXIS_LABELS[check.axis] ?? check.axis;
  return (
    <div
      role="group"
      aria-label={label}
      className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-3 gap-y-1 border-b border-hairline py-3 md:contents"
    >
      <div className={`order-1 font-bold text-ink md:order-none ${CELL}`}>
        {label}
      </div>
      <div
        className={`order-3 col-span-2 font-mono text-[13px] text-ink-soft md:order-none md:col-span-1 ${CELL}`}
      >
        <StackedLabel>目標</StackedLabel>
        <span>{check.target}</span>
      </div>
      <div
        className={`order-4 col-span-2 font-mono text-[13px] text-ink md:order-none md:col-span-1 ${CELL}`}
      >
        <StackedLabel>実績</StackedLabel>
        <span>{check.actual}</span>
        {ceiling != null && <OverCeilingBar ceiling={ceiling} />}
      </div>
      {/* Stacked, the tag sits on the name's line at the right edge, which is
          what keeps it on screen at 400px — a table pushed it off the side
          entirely. `order` does that without moving it out of the 状態 column
          at `md`, where the shared grid places cells in DOM order. */}
      <div
        className={`order-2 justify-self-end md:order-none md:justify-self-stretch ${CELL}`}
      >
        <StatusTag onPlan={check.on_plan} />
      </div>
    </div>
  );
}

/**
 * 計画との照合 (#1252): what the day asked for, what the run did, per axis.
 *
 * Nothing is re-judged here — each row states on / off plan exactly as the
 * deterministic verdict decided it, so a tolerance band can never drift
 * between the verdict and the card that explains it.
 *
 * It is a CSS grid rather than a `<table>`: four numeric-ish columns in a
 * table push the 状態 column off a 400px screen, and the answer the reader
 * came for is precisely that column. Stacked, each check becomes four lines
 * with the status on the first one.
 */
export default function PlanCheck({
  id,
  plan,
}: {
  id?: string;
  plan: RunPlan | null;
}): JSX.Element | null {
  if (plan == null || plan.checks.length === 0) {
    return null;
  }
  return (
    <SectionBlock
      id={id}
      title="計画との照合"
      note={plan.title !== "" ? `処方「${plan.title}」` : undefined}
      noteMono
    >
      <div className={`md:grid ${GRID_COLUMNS}`}>
        <div aria-hidden="true" className="hidden md:contents">
          {COLUMNS.map((column) => (
            <span
              key={column}
              className="border-b border-ink pb-2 pr-3 font-mono text-[11px] tracking-[0.04em] text-ink-muted"
            >
              {column}
            </span>
          ))}
        </div>
        {plan.checks.map((check) => (
          <CheckRow
            key={check.axis}
            check={check}
            ceiling={check.axis === "hr_ceiling" ? plan.hr_ceiling : null}
          />
        ))}
      </div>
    </SectionBlock>
  );
}
