/**
 * Race-goal formatting helpers shared by the Goal page and the dashboard's
 * RaceProgress strip. They live here (rather than on a page module) so a
 * dashboard card never has to import from a page component just to format a
 * countdown or a gap.
 */

/** Format a target time in seconds as H:MM:SS (e.g. 16200 -> "4:30:00"). */
export function formatTargetTime(seconds: number | null): string {
  if (seconds == null || seconds < 0) {
    return "-";
  }
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  return `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(
    2,
    "0",
  )}`;
}

/**
 * Whole days from today (local) until `isoDate` (YYYY-MM-DD). Returns null when
 * the date is missing or unparseable. Negative values mean the date has passed.
 * Pure so the countdown is testable without mocking the clock at call sites.
 */
export function daysUntil(
  isoDate: string | null,
  today: Date = new Date(),
): number | null {
  if (isoDate == null) {
    return null;
  }
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate.trim());
  if (match == null) {
    return null;
  }
  const target = Date.UTC(
    Number(match[1]),
    Number(match[2]) - 1,
    Number(match[3]),
  );
  const now = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.round((target - now) / 86_400_000);
}

/** Format a signed gap in seconds as ±H:MM:SS / ±M:SS (0 -> "±0:00"). */
export function formatGap(seconds: number): string {
  const sign = seconds > 0 ? "+" : seconds < 0 ? "−" : "±";
  const abs = Math.abs(seconds);
  const hours = Math.floor(abs / 3600);
  const minutes = Math.floor((abs % 3600) / 60);
  const secs = abs % 60;
  const body =
    hours > 0
      ? `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`
      : `${minutes}:${String(secs).padStart(2, "0")}`;
  return `${sign}${body}`;
}
