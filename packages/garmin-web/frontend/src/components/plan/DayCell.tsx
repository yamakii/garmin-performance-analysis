import type { JSX } from "react";
import type { StatusTone } from "../StatusBadge";
import type { LadderStep, PlanActivity, PlanDay, Prescription } from "../../types";
import {
  formatBpmValue,
  formatDistanceKmValue,
  formatPaceValue,
} from "../../utils/format";
import { formatNumber } from "../../utils/formatNumber";
import { dayOfMonthLabel } from "../../utils/week";

/** Japanese label per prescribed session type; unknown types show verbatim. */
const SESSION_TYPE_LABEL: Record<string, string> = {
  easy: "イージー",
  recovery: "リカバリー",
  long: "ロング",
  long_run: "ロング",
  tempo: "テンポ",
  threshold: "閾値",
  interval: "インターバル",
  repetition: "レペティション",
  race: "レース",
  rest: "休養",
  strength: "筋トレ",
  cross: "クロス",
};

/** Lifecycle status → the shared 良/注意/悪/情報 tone vocabulary. */
const STATUS_TONE: Record<string, StatusTone> = {
  prescribed: "info",
  registered: "info",
  done: "good",
  replaced: "warn",
  skipped: "bad",
};

const STATUS_LABEL: Record<string, string> = {
  prescribed: "予定",
  registered: "登録済",
  done: "実施",
  replaced: "代替",
  skipped: "未実施",
};

export function sessionLabel(sessionType: string): string {
  return SESSION_TYPE_LABEL[sessionType] ?? sessionType;
}

export function statusTone(status: string): StatusTone {
  return STATUS_TONE[status] ?? "info";
}

export function statusLabel(status: string): string {
  return STATUS_LABEL[status] ?? status;
}

/** "22km ≤150" — the target of a prescription (or a ladder step) in one line. */
export function targetSummary(target: {
  target_km?: number | null;
  target_minutes?: number | null;
  hr_high?: number | null;
  hr_ceiling?: number | null;
}): string {
  const parts: string[] = [];
  if (target.target_km != null) {
    parts.push(`${formatNumber(target.target_km, 1)}km`);
  }
  if (target.target_minutes != null) {
    parts.push(`${formatNumber(target.target_minutes, 0)}分`);
  }
  const hr = target.hr_high ?? target.hr_ceiling;
  if (hr != null) {
    parts.push(`≤${hr}`);
  }
  return parts.join(" ");
}

/** "21.4 · 6:19 · 146" — what actually happened, in one mono line. */
function actualSummary(activity: PlanActivity): string {
  return [
    formatDistanceKmValue(activity.total_distance_km, 1),
    formatPaceValue(activity.avg_pace_seconds_per_km),
    formatBpmValue(activity.avg_heart_rate),
  ].join(" · ");
}

/**
 * One prescribed session inside a day cell.
 *
 * The status is carried by the shape of the rows rather than by a badge
 * (Morning Brief, #1119): a session that happened states what was run under a
 * bold name, a session that did not is struck through, and a replaced one
 * keeps its original line struck with the substitute after an arrow. Only the
 * two exceptions a reader has to act on take colour.
 */
function PrescriptionRow({
  prescription,
  activity,
}: {
  prescription: Prescription;
  activity: PlanActivity | null;
}) {
  const name = sessionLabel(prescription.session_type);
  const target = targetSummary(prescription);
  const status = prescription.status;

  if (status === "replaced") {
    return (
      <div className="flex flex-col gap-0.5 text-status-warn">
        <p className="text-[13px] font-bold">
          <s>
            {name}
            {target !== "" && ` ${target}`}
          </s>
        </p>
        <p className="font-mono text-xs">
          → {activity != null ? actualSummary(activity) : "代替"}
        </p>
      </div>
    );
  }

  const isRest = prescription.session_type === "rest";
  const isSkipped = status === "skipped";
  return (
    <div className="flex flex-col gap-0.5">
      <p
        className={`text-[13px] font-bold ${
          isRest
            ? "text-status-warn"
            : isSkipped
              ? "text-ink-muted line-through"
              : ""
        }`}
      >
        {name}
      </p>
      {isRest && prescription.rationale != null ? (
        <p className="text-xs text-status-warn">{prescription.rationale}</p>
      ) : activity != null ? (
        <p className="font-mono text-xs">{actualSummary(activity)}</p>
      ) : (
        target !== "" && (
          <p
            className={`font-mono text-xs ${
              isSkipped ? "text-ink-muted line-through" : "text-ink-muted"
            }`}
          >
            {target}
          </p>
        )
      )}
    </div>
  );
}

/**
 * One day of the month grid: what was prescribed above what was actually run.
 *
 * A long-run day with no prescription row yet still states the block's ladder
 * target, so the month reads as a plan before the week is prescribed. Days
 * outside the month keep their place in the grid but drop to `ink-faint` —
 * the shape of the calendar survives, the content stops competing.
 */
export default function DayCell({
  day,
  isToday = false,
  ladderStep = null,
}: {
  day: PlanDay;
  isToday?: boolean;
  /** The week's ladder step, passed only to the long-run column. */
  ladderStep?: LadderStep | null;
}): JSX.Element {
  const ladderTarget =
    day.prescriptions.length === 0 && ladderStep != null
      ? targetSummary(ladderStep)
      : "";
  const prescriptions = day.prescriptions;
  const replaced = prescriptions.some(
    (prescription) => prescription.status === "replaced",
  );
  const rest = prescriptions.some(
    (prescription) => prescription.session_type === "rest",
  );
  // A day's runs pair up with its prescriptions in order; anything left over
  // was run without one and is listed on its own below.
  const extraActivities = day.activities.slice(prescriptions.length);

  return (
    <div
      role="cell"
      // `min-w-0` keeps the cell from widening its grid column, and the
      // inherited `overflow-wrap` breaks the one token a rationale can carry
      // that has no break opportunity at all (`extra_rest_days=1`, #1143).
      className={`flex min-h-[96px] min-w-0 flex-col gap-1 border-r border-hairline p-2.5 pr-2 [overflow-wrap:anywhere] ${
        isToday
          ? "bg-accent-tint"
          : replaced || rest
            ? "bg-warn-tint"
            : ""
      } ${day.in_month ? "text-ink" : "text-ink-faint"}`}
    >
      <p
        className={`font-mono text-xs ${
          !day.in_month
            ? "text-ink-faint"
            : isToday
              ? "font-semibold text-accent"
              : replaced || rest
                ? "text-status-warn"
                : "text-ink-muted"
        }`}
      >
        {dayOfMonthLabel(day.date)}
        {isToday && (
          <span className="ml-1 text-[10px] tracking-[0.06em]">TODAY</span>
        )}
      </p>

      {prescriptions.map((prescription, index) => (
        <PrescriptionRow
          key={prescription.prescription_id}
          prescription={prescription}
          activity={day.activities[index] ?? null}
        />
      ))}

      {ladderTarget !== "" && (
        <div className="flex flex-col gap-0.5">
          <p className="text-[13px] text-ink-muted">ロング目標</p>
          <p className="font-mono text-xs text-ink-muted">{ladderTarget}</p>
        </div>
      )}

      {extraActivities.map((activity) => (
        <p key={activity.activity_id} className="font-mono text-xs">
          {actualSummary(activity)}
        </p>
      ))}
    </div>
  );
}
