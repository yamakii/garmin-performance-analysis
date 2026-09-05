import type { JSX } from "react";
import StatusBadge, { type StatusTone } from "../StatusBadge";
import type { LadderStep, PlanDay, Prescription } from "../../types";
import { formatDistanceKmValue, formatPace } from "../../utils/format";
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

function PrescriptionRow({ prescription }: { prescription: Prescription }) {
  const target = targetSummary(prescription);
  return (
    <div className="space-y-0.5">
      <div className="flex flex-wrap items-center gap-1">
        <span className="text-xs font-semibold text-ink">
          {sessionLabel(prescription.session_type)}
        </span>
        <StatusBadge tone={statusTone(prescription.status)}>
          {statusLabel(prescription.status)}
        </StatusBadge>
      </div>
      {target !== "" && (
        <p className="font-numeric text-xs tabular-nums text-slate-600">
          {target}
        </p>
      )}
    </div>
  );
}

/**
 * One day of the month grid: what was prescribed (type + target + status)
 * above what was actually run (distance + pace).
 *
 * A long-run day with no prescription row yet still states the block's ladder
 * target, so the month reads as a plan before the week is prescribed. Days
 * outside the month are muted rather than blank — the grid keeps its shape.
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
  return (
    <td
      className={`h-full min-w-[6.5rem] align-top ${
        isToday ? "rounded-lg ring-2 ring-signal/60 ring-inset" : ""
      } ${day.in_month ? "" : "bg-slate-50/60"}`}
    >
      <div className="space-y-1 p-1.5">
        <div className="flex items-baseline gap-1">
          <span
            className={`font-numeric text-xs tabular-nums ${
              day.in_month ? "font-semibold text-ink" : "text-slate-500"
            }`}
          >
            {dayOfMonthLabel(day.date)}
          </span>
          {isToday && (
            <span className="rounded-full bg-signal/15 px-1.5 py-0.5 text-[10px] font-bold text-signal-ink">
              今日
            </span>
          )}
        </div>

        {day.prescriptions.map((prescription) => (
          <PrescriptionRow
            key={prescription.prescription_id}
            prescription={prescription}
          />
        ))}

        {ladderTarget !== "" && (
          <p className="font-numeric text-xs tabular-nums text-slate-500">
            <span className="mr-1 text-[10px] font-semibold tracking-wide text-slate-600">
              ロング目標
            </span>
            {ladderTarget}
          </p>
        )}

        {day.activities.map((activity) => (
          <p
            key={activity.activity_id}
            className="font-numeric text-xs tabular-nums text-slate-600"
          >
            {formatDistanceKmValue(activity.total_distance_km, 1)}km{" "}
            {formatPace(activity.avg_pace_seconds_per_km)}
          </p>
        ))}
      </div>
    </td>
  );
}
