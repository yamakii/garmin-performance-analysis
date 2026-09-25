import type { JSX, ReactNode } from "react";
import SectionBlock from "../SectionBlock";
import type {
  HrCeiling,
  PlanCheckRow,
  PlanCheckSegment,
  RunJudgedShare,
  RunPlan,
  RunPurpose,
} from "../../types";
import { formatNumber } from "../../utils/formatNumber";

/**
 * "ロング（目標ペース）" / "イージー（推定）" — what the run was for, or null
 * when the report does not know (#1315). An inferred purpose says so: it was
 * read from the run, not prescribed, and the page must not pass it off as the
 * plan.
 */
export function purposeText(purpose: RunPurpose | null | undefined): string | null {
  if (purpose == null || purpose.id === "unknown" || purpose.label_ja === "") {
    return null;
  }
  return purpose.source === "inferred"
    ? `${purpose.label_ja}（推定）`
    : purpose.label_ja;
}

/**
 * "達成" / "達成できず（18 km から崩れ）" — whether the run delivered its
 * purpose (#1348), or null when the report did not judge it (intervals,
 * fartlek, recovery, too little to judge). The verdict is the report's
 * (#1340); nothing is re-judged here.
 */
export function outcomeText(purpose: RunPurpose | null | undefined): string | null {
  const outcome = purpose?.outcome;
  if (purpose == null || purpose.id === "unknown" || outcome == null) {
    return null;
  }
  if (outcome.met) {
    return "達成";
  }
  return outcome.breakdown_from_km == null
    ? "達成できず"
    : `達成できず（${formatNumber(outcome.breakdown_from_km, 1)} km から崩れ）`;
}

/**
 * "心拍 72% · フォーム 80%" — the share of the run the HR ceiling and the form
 * signals were judged on (#1313), or null when there is no time series.
 */
export function judgedShareText(
  share: RunJudgedShare | null | undefined,
): string | null {
  if (share == null) {
    return null;
  }
  const parts: string[] = [];
  if (share.hr != null) {
    parts.push(`心拍 ${Math.round(share.hr * 100)}%`);
  }
  if (share.form != null) {
    parts.push(`フォーム ${Math.round(share.form * 100)}%`);
  }
  return parts.length > 0 ? parts.join(" · ") : null;
}

/**
 * Japanese name per fixed plan axis, for rows older than #1404 that carry no
 * `label_ja`. Structure-derived axes (`hr_band_2`, `reps_2`, ...) name
 * themselves, so they need no entry here; an unknown axis keeps its own key.
 */
const AXIS_LABELS: Record<string, string> = {
  intensity: "強度",
  volume: "量",
  hr_ceiling: "心拍上限",
  rest: "休養",
  strides: "流し",
  continuity: "継続",
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

/** The row's name: the report's own label, else the fixed table, else the id. */
export function axisLabel(check: PlanCheckRow): string {
  return check.label_ja || AXIS_LABELS[check.axis] || check.axis;
}

/**
 * Axes whose steps are listed under the row (#1407): a build-up is read stage
 * by stage, a rep set rep by rep, a band step iteration by iteration.
 */
const STEP_AXIS = /^(stages|reps|hr_band)(_\d+)?$/;

/** Off-plan wording per status; `on_plan` and `insufficient` are neutral. */
const OFF_PLAN_TEXT: Record<string, string> = {
  off_plan: "ずれ",
  short: "不足",
  missing: "未実施",
};

function StatusTag({ check }: { check: PlanCheckRow }) {
  if (check.status === "insufficient") {
    // Not judged is not the same as fine: a neutral tag, no badge colour.
    return (
      <span className="font-mono text-xs whitespace-nowrap text-ink-muted">
        判定不能
      </span>
    );
  }
  const onPlan = check.on_plan;
  return (
    <span
      className={`font-mono text-xs whitespace-nowrap ${
        onPlan ? "text-ink-muted" : "font-bold text-status-warn"
      }`}
    >
      {onPlan ? "計画どおり" : (OFF_PLAN_TEXT[check.status] ?? "ずれ")}
    </span>
  );
}

/**
 * One line per prescribed step under a stages / reps / hr_band row: the
 * step's name, its target band, what was run and a ✅ / 🟡 badge. A missed
 * step is 🟡, never 🔴 -- the axis verdict already carries the severity.
 */
function StepList({
  label,
  segments,
}: {
  label: string;
  segments: PlanCheckSegment[];
}): JSX.Element {
  return (
    <ul
      aria-label={`${label}の内訳`}
      className="order-5 col-span-2 flex flex-col gap-0.5 pb-1 font-mono text-xs md:order-none md:col-span-4 md:border-b md:border-hairline md:pb-3 md:pl-[96px]"
    >
      {segments.map((segment, index) => (
        <li
          key={`${segment.segment_id}-${index}`}
          className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.2fr)_auto] items-baseline gap-x-2"
        >
          <span className="truncate text-ink-muted">{segment.label}</span>
          <span className="text-ink-soft">{segment.target}</span>
          <span className="text-ink">{segment.actual}</span>
          <span aria-label={segment.on_plan ? "計画どおり" : "ずれ"}>
            {segment.on_plan ? "✅" : "🟡"}
          </span>
        </li>
      ))}
    </ul>
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
  const label = axisLabel(check);
  const steps =
    STEP_AXIS.test(check.axis) && check.segments != null
      ? check.segments
      : [];
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
        {ceiling != null && check.status !== "insufficient" && (
          <OverCeilingBar ceiling={ceiling} />
        )}
      </div>
      {/* Stacked, the tag sits on the name's line at the right edge, which is
          what keeps it on screen at 400px — a table pushed it off the side
          entirely. `order` does that without moving it out of the 状態 column
          at `md`, where the shared grid places cells in DOM order. */}
      <div
        className={`order-2 justify-self-end md:order-none md:justify-self-stretch ${CELL}`}
      >
        <StatusTag check={check} />
      </div>
      {/* The step list spans the whole row at `md`+ (a fifth cell of the
          shared grid set to every track) and sits last when stacked. */}
      {steps.length > 0 && <StepList label={label} segments={steps} />}
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
 *
 * Above the grid sits what the run was *for* (#1315) — the purpose every scene
 * of the run was judged against — whether an unprescribed run delivered it
 * (#1348; with a prescription that is the table's 継続 row, #1354), and
 * how much of the run the HR ceiling and
 * the form signals were judged on, so a verdict read off 60% of the run is not
 * mistaken for one about all of it.
 */
export default function PlanCheck({
  id,
  plan,
  purpose = null,
  judgedShare = null,
}: {
  id?: string;
  plan: RunPlan | null;
  purpose?: RunPurpose | null;
  judgedShare?: RunJudgedShare | null;
}): JSX.Element | null {
  const purposeLabel = purposeText(purpose);
  const shareLabel = judgedShareText(judgedShare);
  const hasChecks = plan != null && plan.checks.length > 0;
  // With a prescription the purpose is the prescription's, and whether the
  // run delivered it is the table's 継続 row (#1354); a separate line would
  // answer the same question twice. Only an unprescribed run -- inferred
  // purpose, no table -- shows the outcome here.
  const outcomeLabel =
    purposeLabel == null || hasChecks ? null : outcomeText(purpose);
  // A run with no prescription still has a purpose -- inferred from the run
  // itself -- and a judged share (#1326). Those runs are where "（推定）"
  // matters most, so the section stays with just that line.
  if (!hasChecks && purposeLabel == null && shareLabel == null) {
    return null;
  }
  const note =
    plan == null
      ? "処方なし"
      : plan.title !== ""
        ? `処方「${plan.title}」`
        : undefined;
  return (
    <SectionBlock id={id} title="計画との照合" note={note} noteMono>
      {(purposeLabel != null || shareLabel != null) && (
        // One label column shared by every row, so the values start at the
        // same x however long each label is (#1350). Each item is
        // `display: contents` so its dt / dd sit in the shared tracks.
        <dl className="mb-3 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 font-mono text-[13px]">
          {purposeLabel != null && (
            <div className="contents" data-testid="plan-purpose">
              <dt className="text-ink-muted">目的</dt>
              <dd className="text-ink">{purposeLabel}</dd>
            </div>
          )}
          {outcomeLabel != null && (
            <div className="contents" data-testid="plan-outcome">
              <dt className="text-ink-muted">目的の達成</dt>
              <dd
                className={
                  purpose?.outcome?.met === true
                    ? "text-ink"
                    : "font-bold text-status-warn"
                }
              >
                {outcomeLabel}
              </dd>
            </div>
          )}
          {shareLabel != null && (
            <div className="contents" data-testid="plan-judged-share">
              <dt className="text-ink-muted">判定した範囲</dt>
              <dd className="text-ink-soft">{shareLabel}</dd>
            </div>
          )}
        </dl>
      )}
      {hasChecks && plan != null && (
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
      )}
    </SectionBlock>
  );
}
