import type { JSX } from "react";
import { sessionLabel, targetSummary } from "../../components/plan/DayCell";
import type { PlanActivity, PlanDay, Prescription, PlanWeek } from "../../types";
import {
  formatBpmValue,
  formatDistanceKmValue,
  formatPaceValue,
} from "../../utils/format";
import { WEEKDAYS, dayOfMonthLabel } from "../../utils/week";

/** Weekday character of a calendar day, computed in UTC (#920). */
function weekdayChar(isoDate: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate);
  if (match == null) {
    return "";
  }
  const day = new Date(
    Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])),
  ).getUTCDay();
  return WEEKDAYS[day];
}

/**
 * The session name: the coach's own title when it starts with the session
 * label ("ロング 22km"), otherwise the label alone — a title written for a
 * different surface must not push the target out of a 1/7-wide cell.
 */
function nameOf(prescription: Prescription): string {
  const label = sessionLabel(prescription.session_type);
  const title = prescription.title ?? "";
  return title.startsWith(label) ? title : label;
}

/** "21.4km · 6:19 · 146" — what actually happened on a done day. */
function actualSummary(activity: PlanActivity): string {
  return [
    `${formatDistanceKmValue(activity.total_distance_km, 1)}km`,
    formatPaceValue(activity.avg_pace_seconds_per_km),
    formatBpmValue(activity.avg_heart_rate),
  ].join(" · ");
}

/**
 * The week at a glance: seven cells, one per day, each stating the prescribed
 * session and either its target or what was actually run.
 *
 * It replaces the home page's row list (#1117): a week is a shape, and seven
 * columns show where the long run sits and how much of the week is already
 * behind the reader. Colour is reserved for the exceptions the reader must
 * act on — today (accent), and a rest directive or a replaced session
 * (注意) — so an ordinary week is all ink.
 */
export default function WeekStrip({
  week,
  days,
  today,
}: {
  week: PlanWeek | null;
  /** The seven ISO days of the week, in display order. */
  days: string[];
  /** Today's ISO date, so the highlight is testable without a clock. */
  today: string;
}): JSX.Element {
  const byDate = new Map<string, PlanDay>(
    (week?.days ?? []).map((day) => [day.date, day]),
  );

  return (
    <div
      role="list"
      className="grid grid-cols-7 border-t border-l border-ink border-l-hairline"
    >
      {days.map((date) => {
        const day = byDate.get(date) ?? null;
        const prescription = day?.prescriptions[0] ?? null;
        const activity = day?.activities[0] ?? null;
        const isToday = date === today;
        const isRest = prescription?.session_type === "rest";
        const isReplaced = prescription?.status === "replaced";
        const isSkipped = prescription?.status === "skipped";
        const tinted = isRest || isReplaced;
        const name = prescription != null ? nameOf(prescription) : null;
        const target = prescription != null ? targetSummary(prescription) : "";

        return (
          <div
            role="listitem"
            key={date}
            className={`flex min-h-[118px] flex-col gap-1.5 border-r border-b border-hairline p-3 ${
              isToday ? "bg-accent-tint" : tinted ? "bg-warn-tint" : ""
            }`}
          >
            <p
              className={`font-mono text-xs ${
                isToday ? "font-semibold text-accent" : "text-ink-muted"
              }`}
            >
              {dayOfMonthLabel(date)} {weekdayChar(date)}
              {isToday && (
                <span className="ml-1 text-[10px] tracking-[0.06em]">
                  TODAY
                </span>
              )}
            </p>

            {prescription == null ? (
              <p className="text-sm text-ink-muted">休養</p>
            ) : isReplaced ? (
              <>
                <p className="text-sm font-bold text-status-warn">
                  <s>
                    {name}
                    {target !== "" && ` ${target}`}
                  </s>
                </p>
                <p className="font-mono text-xs text-status-warn">→ 代替</p>
              </>
            ) : (
              <>
                <p
                  className={`text-sm font-bold ${
                    isRest
                      ? "text-status-warn"
                      : isSkipped
                        ? "text-ink-muted line-through"
                        : "text-ink"
                  }`}
                >
                  {name}
                </p>
                {isRest && prescription.rationale != null && (
                  <p className="text-xs text-status-warn">
                    {prescription.rationale}
                  </p>
                )}
                {activity != null ? (
                  <p className="font-mono text-xs text-ink">
                    {actualSummary(activity)}
                  </p>
                ) : (
                  target !== "" && (
                    <p
                      className={`font-mono text-xs ${
                        isSkipped
                          ? "text-ink-muted line-through"
                          : "text-ink-muted"
                      }`}
                    >
                      {target}
                    </p>
                  )
                )}
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}
