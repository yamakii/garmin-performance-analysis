import type { JSX } from "react";
import { Link } from "react-router-dom";
import type { MonthPlan, PlanDay, PlanWeek } from "../../types";
import { toIsoDate } from "../../utils/format";
import { weekRowLabel, weekRowsForMonth, weekdayLabels } from "../../utils/week";
import AdherenceChip from "./AdherenceChip";
import DayCell, { targetSummary } from "./DayCell";

const EMPTY_ADHERENCE = {
  prescribed: 0,
  done: 0,
  replaced: 0,
  skipped: 0,
  pending: 0,
};

function emptyWeek(weekStart: string, days: string[]): PlanWeek {
  return {
    week_start: weekStart,
    week_end: days[days.length - 1],
    in_month: false,
    ladder_step: null,
    review_exists: false,
    adherence: EMPTY_ADHERENCE,
    days: [],
  };
}

function emptyDay(date: string): PlanDay {
  return { date, in_month: false, prescriptions: [], activities: [] };
}

const HEADER_CELL =
  "px-1.5 pb-2 text-xs font-semibold tracking-wide text-slate-600";

/**
 * The month as a calendar: one row per week, columns ordered from the athlete's
 * `week_start_day` (Monday start → the Sunday long run is the last column).
 *
 * The geometry comes from `weekRowsForMonth` — the same rule the API uses to
 * build its grid range — and the payload only fills the cells, so a row always
 * has seven columns even if a week is missing from the response. Each row
 * header links to that week's review, which is where the prose lives: the grid
 * itself stays numbers and status.
 */
export default function MonthGrid({
  plan,
  today = new Date(),
}: {
  plan: MonthPlan;
  /** Injectable clock for tests. */
  today?: Date;
}): JSX.Element {
  const labels = weekdayLabels(plan.week_start_day);
  const rows = weekRowsForMonth(plan.month, plan.week_start_day);
  const weekByStart = new Map(plan.weeks.map((week) => [week.week_start, week]));
  const dayByDate = new Map(
    plan.weeks.flatMap((week) => week.days).map((day) => [day.date, day]),
  );
  const todayIso = toIsoDate(today);

  return (
    <div className="overflow-x-auto">
      <table
        aria-label="月間プラン"
        className="w-full border-separate border-spacing-1 text-left"
      >
        <thead>
          <tr>
            <th scope="col" className={HEADER_CELL}>
              週
            </th>
            {labels.map((label) => (
              <th key={label} scope="col" className={HEADER_CELL}>
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const week =
              weekByStart.get(row.weekStart) ??
              emptyWeek(row.weekStart, row.days);
            const ladderTarget =
              week.ladder_step != null ? targetSummary(week.ladder_step) : "";
            return (
              <tr key={row.weekStart}>
                <th scope="row" className="min-w-[6rem] align-top">
                  <div className="space-y-1 p-1.5">
                    <Link
                      to={`/weekly-reviews/${row.weekStart}`}
                      className={`block font-numeric text-xs font-semibold tabular-nums ${
                        week.review_exists
                          ? "text-status-info hover:underline"
                          : "text-slate-600 hover:text-ink hover:underline"
                      }`}
                    >
                      {weekRowLabel(row.weekStart)}
                    </Link>
                    <AdherenceChip adherence={week.adherence} />
                    {ladderTarget !== "" && (
                      <p className="font-numeric text-xs tabular-nums text-slate-600">
                        ロング {ladderTarget}
                      </p>
                    )}
                  </div>
                </th>
                {row.days.map((date, index) => (
                  <DayCell
                    key={date}
                    day={dayByDate.get(date) ?? emptyDay(date)}
                    isToday={date === todayIso}
                    // The long run sits on the last column of the row, so the
                    // ladder target lands there even before the week is
                    // prescribed.
                    ladderStep={index === 6 ? week.ladder_step : null}
                  />
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
