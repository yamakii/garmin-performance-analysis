import type { JSX } from "react";
import { Link } from "react-router-dom";
import type { MonthPlan, PlanDay, PlanWeek } from "../../types";
import { toIsoDate } from "../../utils/format";
import { formatNumber } from "../../utils/formatNumber";
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

/** The shared column geometry: the week header, then the seven days. */
const ROW_CLASS = "grid grid-cols-[96px_repeat(7,1fr)]";

/**
 * "計画 38km" / "ロング 16km" — what the week asks for in one line.
 *
 * A prescribed week states the distance it adds up to; an unprescribed one
 * still has the block's ladder step, which is the only commitment that exists
 * that far ahead.
 */
function weekTargetLine(week: PlanWeek): string {
  const planned = week.days
    .flatMap((day) => day.prescriptions)
    .reduce((sum, prescription) => sum + (prescription.target_km ?? 0), 0);
  if (planned > 0) {
    return `計画 ${formatNumber(planned, 1)}km`;
  }
  const ladder =
    week.ladder_step != null ? targetSummary(week.ladder_step) : "";
  return ladder !== "" ? `ロング ${ladder}` : "";
}

/**
 * The month as a calendar: one row per week, columns ordered from the athlete's
 * `week_start_day` (Monday start → the Sunday long run is the last column).
 *
 * It is a CSS grid carrying table roles rather than a `<table>` (Morning
 * Brief, #1119): the cells have to share their column geometry with the block
 * bands drawn above them, which a table cannot do, while the roles keep the
 * grid navigable as the table it reads as.
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
    <div className="flex flex-col gap-2 overflow-x-auto">
      <div role="table" aria-label="月間プラン" className="min-w-[720px]">
        <div role="rowgroup">
          <div role="row" className={`${ROW_CLASS} border-b border-ink`}>
            <div
              role="columnheader"
              className="pb-2 font-mono text-xs text-ink-muted"
            >
              週
            </div>
            {labels.map((label) => (
              <div
                key={label}
                role="columnheader"
                className="pb-2 pl-2.5 font-mono text-xs text-ink-muted"
              >
                {label}
              </div>
            ))}
          </div>
        </div>
        <div role="rowgroup">
          {rows.map((row) => {
            const week =
              weekByStart.get(row.weekStart) ??
              emptyWeek(row.weekStart, row.days);
            const targetLine = weekTargetLine(week);
            return (
              <div
                key={row.weekStart}
                role="row"
                className={`${ROW_CLASS} border-b border-hairline`}
              >
                <div
                  role="rowheader"
                  className="flex flex-col gap-1 border-r border-hairline py-2.5 pr-2.5"
                >
                  <Link
                    to={`/weekly-reviews/${row.weekStart}`}
                    className={`font-mono text-[13px] font-semibold ${
                      week.review_exists ? "text-accent" : "text-ink"
                    }`}
                  >
                    {weekRowLabel(row.weekStart)}
                  </Link>
                  <AdherenceChip adherence={week.adherence} />
                  {targetLine !== "" && (
                    <p className="font-mono text-xs text-ink-muted">
                      {targetLine}
                    </p>
                  )}
                </div>
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
              </div>
            );
          })}
        </div>
      </div>
      <p className="font-mono text-xs text-ink-muted">
        太字 + 実績行 = 実施 ／ 取り消し線 = 未実施 ／ 注意色 = 代替・休養指示 ／
        淡色 = 月外
      </p>
    </div>
  );
}
