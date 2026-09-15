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

/** Shown in place of a night the device did not record. */
const MISSING_SLEEP = "—";

/**
 * "7時間12分" — how long a night lasted, from its length in seconds.
 *
 * Sleep is the one duration on the brief that is read in hours, not in the
 * `h:mm:ss` a run is timed in, so it gets its own words rather than
 * {@link formatDuration}. A missing or negative night reads as an em dash.
 */
export function formatSleepDuration(
  seconds: number | null | undefined,
): string {
  if (!isMeasured(seconds) || seconds < 0) {
    return MISSING_SLEEP;
  }
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${hours}時間${minutes}分`;
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
 * "13:45" — the wall-clock time an ISO datetime names, or null when the input
 * carries no time (a date-only string, or nothing at all).
 *
 * Null rather than a dash: a header line drops the time it never had instead
 * of printing a placeholder for it (#1153).
 */
export function formatTimeOfDay(iso: string | null | undefined): string | null {
  const match = iso != null ? ISO_DATE_TIME.exec(iso) : null;
  return match != null ? match[2] : null;
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

/** Three-letter English weekday, indexed by `Date.getDay()` (0=Sun). */
const WEEKDAY_ABBR = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];

/**
 * "2026-09-15 TUE" — the header date of the Morning Brief layout (#1116).
 * Local calendar day, same reasoning as {@link toIsoDate}.
 */
export function formatHeaderDate(date: Date): string {
  return `${toIsoDate(date)} ${WEEKDAY_ABBR[date.getDay()]}`;
}

/**
 * "09/13 SUN" — the short date label used across the brief (week strips,
 * flag rows, "前回 · 09/13 SUN"). Unparseable input is returned as-is rather
 * than hidden. The weekday is computed in UTC so a calendar day never shifts
 * through the reader's timezone (#920).
 */
export function formatDateLabel(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (match == null) {
    return iso;
  }
  const [, year, month, day] = match;
  const weekday = new Date(
    Date.UTC(Number(year), Number(month) - 1, Number(day)),
  ).getUTCDay();
  return `${month}/${day} ${WEEKDAY_ABBR[weekday]}`;
}

/**
 * "2025-10-09 THU" — the full date of a record, in the same
 * `YYYY-MM-DD DDD` shape the page header uses (#1118).
 *
 * {@link formatHeaderDate} says this about "now" (a `Date`); this says it
 * about a stored day, so a report's date line and the site header read
 * identically. Unparseable input is returned as-is rather than hidden, and the
 * weekday is computed in UTC so a calendar day never shifts with the reader's
 * timezone (#920).
 */
export function formatFullDateLabel(iso: string | null | undefined): string {
  if (iso == null || iso === "") {
    return MISSING;
  }
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (match == null) {
    return iso;
  }
  const [, year, month, day] = match;
  const weekday = new Date(
    Date.UTC(Number(year), Number(month) - 1, Number(day)),
  ).getUTCDay();
  return `${year}-${month}-${day} ${WEEKDAY_ABBR[weekday]}`;
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

/**
 * Japanese wording for the intensity buckets a weekly review distributes its
 * volume over. The keys come from the agent's payload, so the map is open:
 * an unknown bucket falls back to `humanizeKey`.
 */
const INTENSITY_LABELS: Record<string, string> = {
  aerobic_base: "有酸素ベース",
  base: "ベース",
  easy: "イージー",
  easy_z1_z2: "イージー（Z1-Z2）",
  recovery: "リカバリー",
  long: "ロング",
  long_run: "ロング",
  tempo: "テンポ",
  threshold: "閾値",
  interval: "インターバル",
  repetition: "レペティション",
  quality: "質練",
  race: "レース",
  strength: "筋トレ",
  cross: "クロス",
};

/** "aerobic_base" -> "有酸素ベース"; an unknown bucket keeps its words. */
export function intensityLabel(key: string): string {
  return INTENSITY_LABELS[key] ?? humanizeKey(key);
}

/**
 * "aerobic_base", 0.5 -> "有酸素ベース 50%".
 *
 * The weekly review card used to print the payload verbatim — "aerobic base:
 * 0.5" — which is the wire format wearing a space instead of an underscore,
 * and a share nobody reads as a half (#1144). A distribution is saved as a
 * fraction of the week, so it is shown as a percentage; a value outside 0..1
 * is a count (older payloads store run counts), and a count is kept as-is
 * rather than being multiplied into a nonsense 400%.
 */
export function formatIntensityShare(key: string, share: number): string {
  const label = intensityLabel(key);
  if (!Number.isFinite(share)) {
    return `${label} ${MISSING}`;
  }
  if (share < 0 || share > 1) {
    return `${label} ${share}`;
  }
  return `${label} ${Math.round(share * 100)}%`;
}
