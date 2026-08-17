/**
 * Single source for the app's display formatting (Issue #915).
 *
 * The audit in #910 found the same quantities rendered six different ways
 * (pace with and without `/km`, distance at one or two decimals, dates as raw
 * ISO datetimes) because every page grew its own private helper. Those helpers
 * now live here so a unit or a decimal place is decided once.
 *
 * Each quantity comes in two flavours: `formatX` returns the number with its
 * unit ("15.04 km"), `formatXValue` returns the number alone ("15.04") for
 * layouts that typeset the unit themselves. Callers must never strip a unit
 * back off a formatted string.
 */

/** Rendered in place of a missing measurement (matches `formatNumber`). */
export const MISSING = "-";

/** Unit suffix for pace, attached without a space ("6:26/km"). */
export const PACE_UNIT = "/km";

function isMeasured(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/** "6:26" — minutes:seconds per km, no unit. */
export function formatPaceValue(secPerKm: number | null | undefined): string {
  if (!isMeasured(secPerKm) || secPerKm <= 0) {
    return MISSING;
  }
  let minutes = Math.floor(secPerKm / 60);
  let seconds = Math.round(secPerKm % 60);
  if (seconds === 60) {
    minutes += 1;
    seconds = 0;
  }
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

/** "6:26/km" */
export function formatPace(secPerKm: number | null | undefined): string {
  const value = formatPaceValue(secPerKm);
  return value === MISSING ? MISSING : `${value}${PACE_UNIT}`;
}

/** "15.04" — kilometres at `digits` decimals, no unit. */
export function formatDistanceKmValue(
  km: number | null | undefined,
  digits: 1 | 2 = 2,
): string {
  return isMeasured(km) ? km.toFixed(digits) : MISSING;
}

/** "15.04 km" */
export function formatDistanceKm(
  km: number | null | undefined,
  digits: 1 | 2 = 2,
): string {
  const value = formatDistanceKmValue(km, digits);
  return value === MISSING ? MISSING : `${value} km`;
}

/** "144" — heart rate rounded to a whole beat, no unit. */
export function formatBpmValue(bpm: number | null | undefined): string {
  return isMeasured(bpm) ? String(Math.round(bpm)) : MISSING;
}

/** "144 bpm" */
export function formatBpm(bpm: number | null | undefined): string {
  const value = formatBpmValue(bpm);
  return value === MISSING ? MISSING : `${value} bpm`;
}

/** "182" — cadence rounded to a whole step, no unit (spm is implied). */
export function formatCadence(cadence: number | null | undefined): string {
  return isMeasured(cadence) ? String(Math.round(cadence)) : MISSING;
}

/** "36:26" under an hour, "1:02:13" over it. */
export function formatDuration(
  totalSeconds: number | null | undefined,
): string {
  if (!isMeasured(totalSeconds) || totalSeconds < 0) {
    return MISSING;
  }
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = Math.floor(totalSeconds % 60);
  const mmss = `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  return hours > 0 ? `${hours}:${mmss}` : mmss;
}

/** Leading `YYYY-MM-DD` of an ISO date or datetime string. */
const ISO_DATE = /^(\d{4}-\d{2}-\d{2})/;

/** Leading `YYYY-MM-DD` plus `HH:MM`, separated by "T" or a space. */
const ISO_DATE_TIME = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/;

/**
 * "2026-08-08" — the calendar day of an ISO date or datetime string.
 * Unparseable input is returned as-is rather than hidden.
 */
export function formatDate(iso: string | null | undefined): string {
  if (iso == null || iso === "") {
    return MISSING;
  }
  return ISO_DATE.exec(iso)?.[1] ?? iso;
}

/**
 * "2026-06-22 09:00" — an ISO datetime without the "T" or the seconds, which
 * is what a reader picking between saved analysis runs needs to see.
 * Date-only input falls back to {@link formatDate}.
 */
export function formatDateTime(iso: string | null | undefined): string {
  const match = iso != null ? ISO_DATE_TIME.exec(iso) : null;
  return match != null ? `${match[1]} ${match[2]}` : formatDate(iso);
}

/**
 * "2026-08-16" — the last day (start + 6 days) of the week beginning at
 * `weekStartIso`; null when the input is missing or is not a calendar day.
 *
 * The arithmetic runs through `Date.UTC` so the week end never lands a day
 * early or late for a reader east of Greenwich (#920): a week boundary is a
 * calendar fact, not an instant, so it must not pass through a local timezone.
 */
export function weekEndIso(
  weekStartIso: string | null | undefined,
): string | null {
  const day = weekStartIso != null ? ISO_DATE.exec(weekStartIso)?.[1] : null;
  if (day == null) {
    return null;
  }
  const [year, month, dayOfMonth] = day.split("-").map(Number);
  // `Date.UTC` silently rolls a nonexistent day over ("2026-02-30" ->
  // March 2), so the start day is round-tripped before it is trusted.
  const start = new Date(Date.UTC(year, month - 1, dayOfMonth));
  if (
    Number.isNaN(start.getTime()) ||
    start.toISOString().slice(0, 10) !== day
  ) {
    return null;
  }
  // The same rollover carries the end across a month or year boundary.
  const end = new Date(Date.UTC(year, month - 1, dayOfMonth + 6));
  return end.toISOString().slice(0, 10);
}

/**
 * Local-date ISO string (YYYY-MM-DD).
 *
 * `Date.toISOString()` reports the UTC day, which is the previous day for any
 * JST morning before 09:00 — an off-by-one on every date bound the app sends
 * to the API. Activity dates are local calendar days, so the local fields are
 * the only correct source.
 */
export function toIsoDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/**
 * "easy_z1_z2" -> "easy z1 z2".
 *
 * Payload keys reach the UI whenever a schema grows a field no component
 * consumes yet; showing the raw identifier leaks the wire format into the
 * page. Underscores and hyphens become spaces so the key at least reads as
 * words.
 */
export function humanizeKey(key: string): string {
  return key.replace(/[_-]+/g, " ").trim();
}
