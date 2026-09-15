import { phaseLabel } from "../components/plan/BlockBands";
import type { MonthPlan, PlanDay, TrainingBlock } from "../types";

/**
 * The month's opening sentence and its four numbers, as data (#1119).
 *
 * `/plan` answers "この1ヶ月どう積むか" and the grid below answers it day by
 * day; this is the paragraph that answers it in one line — where the month
 * sits in the block, how much of what was prescribed actually happened, and
 * what the next long run asks for. It lives here rather than in the page so
 * the wording is unit-testable without rendering, the same rule
 * `utils/verdict.ts` follows for the home page (#1117).
 */
export interface MonthSummary {
  /** Display label of the block the month sits in ("ビルド"), null when none. */
  phase: string | null;
  /** 1-based week of that block, null when no block covers the month. */
  weekIndex: number | null;
  /** How many weeks the block spans. */
  weekTotal: number | null;
  /** Prescription rows inside the month. */
  prescribed: number;
  done: number;
  replaced: number;
  /** Past sessions that were prescribed and never run. */
  late: number;
  /** Sum of the prescribed target distances, in km. */
  plannedKm: number;
  /** Sum of what was actually run inside the month, in km. */
  actualKm: number;
  /** Prescriptions whose outcome is settled (`prescribed` minus pending). */
  resolved: number;
  /** The block's quality-session budget, per week. */
  qualityPerWeek: number | null;
  /** Target of the next long run still ahead, in km. */
  nextLongKm: number | null;
}

const DAY_MS = 86_400_000;

/** Session types that count as the week's long run. */
const LONG_TYPES = new Set(["long", "long_run"]);

/** UTC epoch of a `YYYY-MM-DD` day; null when it is not a calendar day. */
function utcDay(iso: string | null | undefined): number | null {
  const match = iso != null ? /^(\d{4})-(\d{2})-(\d{2})/.exec(iso) : null;
  return match == null
    ? null
    : Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
}

/** One decimal place, so summed floats do not print 21.400000000000002. */
function round1(km: number): number {
  return Math.round(km * 10) / 10;
}

/** "22km" / "21.4km" — a distance without a trailing ".0". */
export function kmText(km: number): string {
  return `${Number.isInteger(km) ? String(km) : km.toFixed(1)}km`;
}

/** The block covering `anchor`, else the first one overlapping the month. */
function blockFor(
  blocks: TrainingBlock[],
  anchor: string,
  monthStart: string,
  monthEnd: string,
): TrainingBlock | null {
  const covers = (block: TrainingBlock, from: string, to: string) => {
    const start = block.start_date ?? from;
    const end = block.end_date ?? to;
    return start <= to && from <= end;
  };
  return (
    blocks.find((block) => covers(block, anchor, anchor)) ??
    blocks.find((block) => covers(block, monthStart, monthEnd)) ??
    null
  );
}

/**
 * Where the month sits in its block, and how much of it happened.
 *
 * Counting runs over the days inside the month only — a grid row that reaches
 * into the neighbouring month is geometry, not this month's workload. A
 * session is `late` once its day is behind the reader and it was never run:
 * a Sunday long run still ahead is unfinished, not missed, which is the rule
 * `adherenceTone` already applies to the week chips.
 */
export function monthSummary(plan: MonthPlan, todayIso: string): MonthSummary {
  const monthStart = `${plan.month}-01`;
  const monthEnd = `${plan.month}-31`;
  // A month the reader navigated to is anchored to its own first day, so the
  // phase clause describes the month on screen rather than today's block.
  const anchor =
    todayIso >= monthStart && todayIso <= monthEnd ? todayIso : monthStart;

  const days: PlanDay[] = plan.weeks
    .flatMap((week) => week.days)
    .filter((day) => day.in_month);

  let prescribed = 0;
  let done = 0;
  let replaced = 0;
  let resolved = 0;
  let late = 0;
  let plannedKm = 0;
  let actualKm = 0;
  let nextLongKm: number | null = null;

  for (const day of days) {
    for (const prescription of day.prescriptions) {
      prescribed += 1;
      plannedKm += prescription.target_km ?? 0;
      const status = prescription.status;
      if (status === "done") {
        done += 1;
      } else if (status === "replaced") {
        replaced += 1;
      }
      if (status === "done" || status === "replaced" || status === "skipped") {
        resolved += 1;
      }
      if (status === "skipped" && day.date < todayIso) {
        late += 1;
      }
      if (
        nextLongKm == null &&
        day.date >= todayIso &&
        // A long run already run (or written off) is behind the reader even
        // when its calendar day is not.
        status !== "done" &&
        status !== "replaced" &&
        status !== "skipped" &&
        LONG_TYPES.has(prescription.session_type) &&
        prescription.target_km != null
      ) {
        nextLongKm = prescription.target_km;
      }
    }
    for (const activity of day.activities) {
      actualKm += activity.total_distance_km ?? 0;
    }
  }

  if (nextLongKm == null) {
    // No long run prescribed yet — the block's ladder still states one.
    const step = plan.weeks.find(
      (week) => week.week_end >= todayIso && week.ladder_step?.target_km != null,
    )?.ladder_step;
    nextLongKm = step?.target_km ?? null;
  }

  const block = blockFor(plan.blocks, anchor, monthStart, monthEnd);
  const blockStart = utcDay(block?.start_date);
  const blockEnd = utcDay(block?.end_date);
  const anchorWeekStart =
    plan.weeks.find(
      (week) => week.week_start <= anchor && anchor <= week.week_end,
    )?.week_start ?? anchor;
  const weekStart = utcDay(anchorWeekStart);
  const dated = blockStart != null && blockEnd != null && weekStart != null;

  return {
    phase: block != null ? phaseLabel(block.phase) : null,
    weekIndex: dated
      ? Math.max(1, Math.floor((weekStart - blockStart) / (7 * DAY_MS)) + 1)
      : null,
    weekTotal: dated
      ? Math.max(1, Math.round((blockEnd - blockStart) / DAY_MS / 7 + 1 / 7))
      : null,
    prescribed,
    done,
    replaced,
    late,
    plannedKm: round1(plannedKm),
    actualKm: round1(actualKm),
    resolved,
    qualityPerWeek: block?.quality_sessions_per_week ?? null,
    nextLongKm,
  };
}

/**
 * The summary as two halves: the bold phase clause and the regular-weight
 * account of the month. An unplanned month says so instead of reporting
 * "0 本のうち 0 本" — no prescriptions is an empty plan, not a failed one.
 */
export function monthSentence(summary: MonthSummary): {
  lead: string;
  rest: string;
} {
  const lead =
    summary.phase != null &&
    summary.weekIndex != null &&
    summary.weekTotal != null
      ? `${summary.phase}期 ${summary.weekIndex}/${summary.weekTotal} 週。`
      : "";

  const parts: string[] = [];
  if (summary.prescribed === 0) {
    parts.push("今月の処方はまだありません。");
  } else {
    const replacedText =
      summary.replaced > 0 ? `・${summary.replaced} 本代替` : "";
    const lateText = summary.late > 0 ? `遅れ ${summary.late} 本` : "遅れなし";
    parts.push(
      `今月の処方 ${summary.prescribed} 本のうち ${summary.done} 本実施${replacedText}、${lateText}。`,
    );
  }
  if (summary.nextLongKm != null) {
    parts.push(`次のロングは ${kmText(summary.nextLongKm)}。`);
  }
  return { lead, rest: parts.join("") };
}
