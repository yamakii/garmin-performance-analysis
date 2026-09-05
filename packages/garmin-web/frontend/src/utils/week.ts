/**
 * Calendar-week helpers with a configurable start day (Issue #983).
 *
 * The athlete's week does not have to start on Monday
 * (`athlete_profile.week_start_day`, 0=Mon … 6=Sun — Python's `date.weekday()`
 * convention, which the API mirrors). The month grid, the weekday header and
 * the home plan card all have to agree on where a week begins, so the geometry
 * lives here instead of in each component.
 *
 * Every calculation runs in UTC: a week boundary is a calendar fact, not an
 * instant, so passing it through a local timezone lands the row a day early or
 * late east of Greenwich (same reasoning as `weekEndIso` in `format.ts`).
 */

/** Weekday labels in the app's canonical order (0=Mon … 6=Sun). */
const MONDAY_FIRST = ["月", "火", "水", "木", "金", "土", "日"];

/** Weekday labels indexed by `Date.getDay()` (0=Sun … 6=Sat). */
export const WEEKDAYS = ["日", "月", "火", "水", "木", "金", "土"];

/** "MM/DD (曜)" from a YYYY-MM-DD string; returns the input when unparseable. */
export function formatDayLabel(isoDate: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate);
  if (match == null) {
    return isoDate;
  }
  const [, y, m, d] = match;
  const weekday =
    WEEKDAYS[new Date(Number(y), Number(m) - 1, Number(d)).getDay()];
  return `${m}/${d} (${weekday})`;
}

/** "13" — the day of the month of a YYYY-MM-DD string, without a leading zero. */
export function dayOfMonthLabel(isoDate: string): string {
  const match = /^\d{4}-\d{2}-(\d{2})/.exec(isoDate);
  return match != null ? String(Number(match[1])) : isoDate;
}

/**
 * Weekday header labels starting at `weekStartDay`.
 *
 * `weekdayLabels(0)` → `["月","火","水","木","金","土","日"]`, so a Monday-start
 * week puts the Sunday long run in the last column.
 */
export function weekdayLabels(weekStartDay: number): string[] {
  const start = normalizeStartDay(weekStartDay);
  return [...MONDAY_FIRST.slice(start), ...MONDAY_FIRST.slice(0, start)];
}

/** Clamp an out-of-range start day back to Monday rather than shifting off-grid. */
function normalizeStartDay(weekStartDay: number): number {
  return Number.isInteger(weekStartDay) &&
    weekStartDay >= 0 &&
    weekStartDay <= 6
    ? weekStartDay
    : 0;
}

/** `Date.getUTCDay()` (0=Sun) expressed in the 0=Mon convention. */
function mondayIndex(date: Date): number {
  return (date.getUTCDay() + 6) % 7;
}

function addDaysUtc(date: Date, days: number): Date {
  return new Date(date.getTime() + days * 86400000);
}

function startOfWeekUtc(date: Date, weekStartDay: number): Date {
  const offset = (mondayIndex(date) - normalizeStartDay(weekStartDay) + 7) % 7;
  return addDaysUtc(date, -offset);
}

function isoDay(date: Date): string {
  return date.toISOString().slice(0, 10);
}

/**
 * The grid rows of a month: the week containing day 1 through the week
 * containing the last day, each with its seven `YYYY-MM-DD` days.
 *
 * Mirrors the range `queries/plan.get_month_plan` builds server-side, so the
 * rendered geometry and the payload agree on every row key. A month that is
 * not `YYYY-MM` yields no rows (the caller renders an empty grid rather than
 * throwing mid-render).
 */
export function weekRowsForMonth(
  month: string,
  weekStartDay: number,
): { weekStart: string; days: string[] }[] {
  const match = /^(\d{4})-(\d{2})$/.exec(month);
  if (match == null) {
    return [];
  }
  const year = Number(match[1]);
  const monthIndex = Number(match[2]) - 1;
  if (monthIndex < 0 || monthIndex > 11) {
    return [];
  }
  const firstDay = new Date(Date.UTC(year, monthIndex, 1));
  // Day 0 of the next month is the last day of this one.
  const lastDay = new Date(Date.UTC(year, monthIndex + 1, 0));

  const rows: { weekStart: string; days: string[] }[] = [];
  const lastRowStart = startOfWeekUtc(lastDay, weekStartDay);
  for (
    let cursor = startOfWeekUtc(firstDay, weekStartDay);
    cursor <= lastRowStart;
    cursor = addDaysUtc(cursor, 7)
  ) {
    rows.push({
      weekStart: isoDay(cursor),
      days: Array.from({ length: 7 }, (_, i) => isoDay(addDaysUtc(cursor, i))),
    });
  }
  return rows;
}

/** "2026-09" shifted by `months` (e.g. -1 → "2026-08"). */
export function shiftMonth(month: string, months: number): string {
  const match = /^(\d{4})-(\d{2})$/.exec(month);
  if (match == null) {
    return month;
  }
  const shifted = new Date(
    Date.UTC(Number(match[1]), Number(match[2]) - 1 + months, 1),
  );
  return isoDay(shifted).slice(0, 7);
}

/** "9/7週" — the row label of the week starting on `weekStart`. */
export function weekRowLabel(weekStart: string): string {
  const match = /^\d{4}-(\d{2})-(\d{2})$/.exec(weekStart);
  return match != null
    ? `${Number(match[1])}/${Number(match[2])}週`
    : weekStart;
}

/** "2026年9月" — the month heading. */
export function formatMonthLabel(month: string): string {
  const match = /^(\d{4})-(\d{2})$/.exec(month);
  return match != null ? `${match[1]}年${Number(match[2])}月` : month;
}
