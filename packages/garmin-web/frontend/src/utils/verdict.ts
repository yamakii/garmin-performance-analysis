import type { TrendNarration } from "../api/trends";
import { sessionLabel } from "../components/plan/DayCell";
import { RECOMMENDATION_LABELS } from "../labels/recovery";
import type { PlanWeek, Prescription, RecoveryStatus } from "../types";

/**
 * The home page's opening sentence, as data (Morning Brief, #1117).
 *
 * The brief opens with one line: the morning go/no-go verdict, then what that
 * means for today's prescribed session. Both halves are derived here rather
 * than in the component so the wording and the tone are unit-testable without
 * rendering, and so the verdict word stays the shared label every other
 * surface uses (#915).
 */
export interface Verdict {
  /** Bold half: the recommendation word plus a full stop ("休養推奨。"). */
  verdict: string;
  /** Colour of the bold half; only 注意 / 悪 get one. */
  tone: "neutral" | "warn" | "bad";
  /** Regular-weight half: what today's prescription asks for. */
  rest: string;
}

/** Recommendation → verdict colour. Anything else stays ink. */
const TONE_BY_RECOMMENDATION: Record<string, Verdict["tone"]> = {
  rest: "bad",
  easy: "warn",
};

/** "10km" / "8.5km" — a target distance without a trailing ".0". */
function kmText(km: number): string {
  return `${Number.isInteger(km) ? String(km) : km.toFixed(1)}km`;
}

/** "イージー 10km、心拍 145 以下。" — what the prescription asks for. */
function prescriptionText(prescription: Prescription): string {
  if (prescription.session_type === "rest") {
    return "今日は休養日。";
  }
  const parts = [sessionLabel(prescription.session_type)];
  if (prescription.target_km != null) {
    parts.push(kmText(prescription.target_km));
  } else if (prescription.target_minutes != null) {
    parts.push(`${Math.round(prescription.target_minutes)}分`);
  }
  const session = parts.join(" ");
  return prescription.hr_high != null
    ? `今日は${session}、心拍 ${prescription.hr_high} 以下。`
    : `今日は${session}。`;
}

/**
 * The verdict line of the home page: the morning recommendation plus today's
 * prescription. A day with no prescription says so rather than guessing — the
 * plan is the coach's, not the page's.
 */
export function homeVerdict(
  status: RecoveryStatus,
  prescription: Prescription | null,
): Verdict {
  const label =
    RECOMMENDATION_LABELS[status.recommendation] ??
    RECOMMENDATION_LABELS.unknown;
  return {
    verdict: `${label}。`,
    tone: TONE_BY_RECOMMENDATION[status.recommendation] ?? "neutral",
    rest:
      prescription != null
        ? prescriptionText(prescription)
        : "今日の処方はありません。",
  };
}

/**
 * Today's prescribed session out of the current plan week, or null when the
 * day carries none. The first row wins: a day holds at most one run in
 * practice, and the brief has room for one sentence.
 */
export function todayPrescription(
  week: PlanWeek | null,
  todayIso: string,
): Prescription | null {
  const day = week?.days.find((planDay) => planDay.date === todayIso) ?? null;
  return day?.prescriptions[0] ?? null;
}

/**
 * The objective numbers the performance verdict rests on (Morning Brief P3b,
 * #1121). All of them are optional: a fresh database, a missing body-weight
 * series or a runner with no long runs each leave one blank, and the verdict
 * has to survive that instead of inventing a direction.
 */
export interface PerformanceKpis {
  /** Latest real-run derived VDOT. */
  objectiveVdot: number | null;
  /** Its change against the reading of four weeks ago. */
  vdotDelta4w: number | null;
  /** Latest easy-run efficiency factor (speed per heartbeat). */
  ef: number | null;
  /** Its change against four weeks ago, in percent. */
  efDeltaPct4w: number | null;
  /** Latest long-run HR decoupling, in percent. */
  decouplingPct: number | null;
}

/**
 * Smallest move that counts as a direction rather than noise: a VDOT point is
 * worth roughly 6 s/km, and EF wanders a percent or two between two easy runs
 * of the same shape.
 */
const VDOT_MOVE = 0.3;
const EF_MOVE_PCT = 2;

/** "+0.8" / "-0.5" / "±0.0" — a delta that always states its sign. */
function signedDelta(value: number, digits: number): string {
  const sign = value > 0 ? "+" : value < 0 ? "-" : "±";
  return `${sign}${Math.abs(value).toFixed(digits)}`;
}

/**
 * The verdict line of `/performance`: is the runner getting faster?
 *
 * The judgement comes from the objective KPIs, never from the coach's prose —
 * the narration is this page's explanation, and a verdict read out of it would
 * only quote that explanation back. The narration is still consulted for one
 * thing: telling "there is prose but no numbers yet" (判断材料が不足) apart from
 * "this page has nothing at all" (データがまだありません), which are different
 * problems for the reader.
 *
 * Mixed signals (VDOT up while EF falls, or the reverse) read as 停滞: the two
 * measures disagree, so the honest answer is that nothing is established.
 */
export function performanceVerdict(
  narration: TrendNarration | null,
  kpis: PerformanceKpis,
): Verdict {
  const { vdotDelta4w, efDeltaPct4w, decouplingPct } = kpis;
  const improving =
    (vdotDelta4w != null && vdotDelta4w > VDOT_MOVE) ||
    (efDeltaPct4w != null && efDeltaPct4w > EF_MOVE_PCT);
  const declining =
    (vdotDelta4w != null && vdotDelta4w < -VDOT_MOVE) ||
    (efDeltaPct4w != null && efDeltaPct4w < -EF_MOVE_PCT);

  const evidence: string[] = [];
  if (vdotDelta4w != null) {
    evidence.push(`4週で客観VDOT ${signedDelta(vdotDelta4w, 1)}`);
  }
  if (efDeltaPct4w != null) {
    evidence.push(`EF ${signedDelta(efDeltaPct4w, 1)}%`);
  }
  if (decouplingPct != null) {
    evidence.push(`デカップリング ${decouplingPct.toFixed(1)}%`);
  }

  const rest =
    evidence.length > 0
      ? `${evidence.join(" · ")}。`
      : narration != null
        ? "判断材料が不足。"
        : "データがまだありません。";

  if (improving && !declining) {
    return { verdict: "速くなっている。", tone: "neutral", rest };
  }
  if (declining && !improving) {
    return { verdict: "落ちている。", tone: "warn", rest };
  }
  return { verdict: "停滞。", tone: "neutral", rest };
}
