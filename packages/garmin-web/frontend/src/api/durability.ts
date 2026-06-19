import type { DurabilityTrend } from "../types";

/** Default window: trailing 180 days of long runs. */
const DEFAULT_LOOKBACK_DAYS = 180;

function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

/**
 * Fetch the long-run decoupling trend.
 *
 * The endpoint requires explicit start/end dates; when omitted we default to
 * the trailing {@link DEFAULT_LOOKBACK_DAYS} days so the dashboard shows recent
 * durability without the caller computing dates.
 */
export async function fetchDurabilityTrend(
  lookbackDays = DEFAULT_LOOKBACK_DAYS,
): Promise<DurabilityTrend> {
  const end = new Date();
  const start = new Date(end);
  start.setDate(start.getDate() - lookbackDays);

  const query = new URLSearchParams({
    start_date: isoDate(start),
    end_date: isoDate(end),
  });
  const response = await fetch(`/api/durability-trend?${query.toString()}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch durability trend: ${response.status}`);
  }
  return (await response.json()) as DurabilityTrend;
}
