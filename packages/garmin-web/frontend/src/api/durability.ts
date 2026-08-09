import type { DurabilityTrend } from "../types";
import { toIsoDate } from "../utils/format";

/** Default window: trailing 180 days of long runs. */
const DEFAULT_LOOKBACK_DAYS = 180;

/**
 * Fetch the long-run decoupling trend.
 *
 * The endpoint requires explicit start/end dates; when omitted we default to
 * the trailing {@link DEFAULT_LOOKBACK_DAYS} days so the dashboard shows recent
 * durability without the caller computing dates.
 *
 * Bounds are local calendar days. Deriving them from the UTC day (as this used
 * to) meant every JST morning before 09:00 asked for a window ending yesterday
 * and dropped that day's long run (#915).
 */
export async function fetchDurabilityTrend(
  lookbackDays = DEFAULT_LOOKBACK_DAYS,
  /** Injectable clock for tests. */
  now: Date = new Date(),
): Promise<DurabilityTrend> {
  const end = new Date(now);
  const start = new Date(end);
  start.setDate(start.getDate() - lookbackDays);

  const query = new URLSearchParams({
    start_date: toIsoDate(start),
    end_date: toIsoDate(end),
  });
  const response = await fetch(`/api/durability-trend?${query.toString()}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch durability trend: ${response.status}`);
  }
  return (await response.json()) as DurabilityTrend;
}
