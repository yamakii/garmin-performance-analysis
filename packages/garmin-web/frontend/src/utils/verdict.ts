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
