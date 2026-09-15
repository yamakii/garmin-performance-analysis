import { sessionLabel } from "../components/plan/DayCell";
import {
  RECOMMENDATION_LABELS,
  RECOVERY_STATE_LABELS,
} from "../labels/recovery";
import type {
  FormAnomalyFlagsResponse,
  GoalRace,
  PlanWeek,
  Prescription,
  RaceReadiness,
  RaceReadinessProgress,
  RecoveryStatus,
  WellnessBaselineDeviation,
} from "../types";
import { adverseMetricLabels } from "./baselineZ";
import { daysUntil, formatGap, formatTargetTime } from "./race";

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
 * The condition page's opening sentence (#1120): how recovered the body is,
 * then the two things that qualify the answer — which readings sit outside the
 * personal baseline, and how many cautions the recent runs raised.
 *
 * The verdict word is the recommendation read as a state (`回復不足。`), not
 * the prescription word the home page uses (`休養推奨。`): the same value, said
 * in the tense of the question each page asks. Both wordings live in the
 * shared label maps, so a third one cannot appear in a component (#915).
 *
 * A missing reading is not an all-clear: `baseline` / `flags` that failed to
 * load simply drop out of the sentence rather than being reported as 基準内.
 */
export function conditionVerdict(
  status: RecoveryStatus,
  baseline: WellnessBaselineDeviation | null,
  flags: FormAnomalyFlagsResponse | null,
): Verdict {
  const label =
    RECOVERY_STATE_LABELS[status.recommendation] ??
    RECOVERY_STATE_LABELS.unknown;
  const parts: string[] = [];

  const adverse = adverseMetricLabels(baseline);
  if (adverse.length > 0) {
    parts.push(`${adverse.join("・")}が基準外`);
  } else if (baseline != null) {
    parts.push("基準外の項目なし");
  }

  if (flags != null) {
    parts.push(
      flags.flags.length > 0 ? `${flags.flags.length} 件の注意点` : "注意点なし",
    );
  }

  return {
    verdict: `${label}。`,
    tone: TONE_BY_RECOMMENDATION[status.recommendation] ?? "neutral",
    rest: parts.length > 0 ? `${parts.join("、")}。` : "",
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

/** Progress status → the Japanese word the goal line uses for it. */
export const RACE_STATUS_LABELS: Record<
  RaceReadinessProgress["status"],
  string
> = {
  ahead: "前倒し",
  on_track: "順調",
  behind: "遅れ",
};

/** "あと 76 日" / "日程未定" / "開催済み" — the countdown half of the line. */
function countdownText(days: number | null): string {
  if (days == null) {
    return "日程未定";
  }
  return days >= 0 ? `あと ${days} 日` : "開催済み";
}

/**
 * The goal page's opening sentence (Morning Brief, #1122): the target time
 * against the current VDOT prediction, then how far out the race is and
 * whether the plan is on schedule.
 *
 * The tone keys on the sign of the gap rather than on `status`: a positive gap
 * means the prediction is *slower* than the target, which is the one case the
 * reader has to act on. `status` only names the direction in words, so an
 * "順調" race whose prediction still trails the target is marked all the same.
 */
export function goalVerdict(
  readiness: RaceReadiness | null,
  race: GoalRace | null,
  today: Date = new Date(),
): Verdict {
  // Nothing to count down to: the page opens by saying so rather than
  // inventing a target out of the distance predictions.
  if (race == null) {
    return { verdict: "目標レース未登録。", tone: "neutral", rest: "" };
  }

  const progress = readiness?.progress ?? null;
  const target =
    race.target_time_seconds ?? readiness?.goal?.target_time_seconds ?? null;
  const targetText = target != null ? formatTargetTime(target) : null;
  const predictionText =
    progress != null ? formatTargetTime(progress.predicted_time_seconds) : null;

  let verdict: string;
  if (targetText != null && predictionText != null) {
    verdict = `目標 ${targetText} に対して予測 ${predictionText}。`;
  } else if (targetText != null) {
    verdict = `目標 ${targetText}。`;
  } else if (predictionText != null) {
    verdict = `予測 ${predictionText}。`;
  } else {
    verdict = "目標タイム未設定。";
  }

  const countdown = countdownText(daysUntil(race.race_date, today));
  const rest =
    progress != null
      ? `${countdown}、${RACE_STATUS_LABELS[progress.status]}。差 ${formatGap(
          progress.gap_seconds,
        )}。`
      : `${countdown}。`;

  return {
    verdict,
    tone: progress != null && progress.gap_seconds > 0 ? "warn" : "neutral",
    rest,
  };
}
