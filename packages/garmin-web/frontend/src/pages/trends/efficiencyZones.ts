import type { EfficiencyTrendPoint } from "../../api/trends";

/** One month's mean HR-zone split, in zone order (Z1..Z5), as percentages. */
export interface MonthlyZoneShare {
  /** "YYYY-MM". */
  month: string;
  /** Mean share per zone; the five add up to ~100. */
  shares: [number, number, number, number, number];
}

const ZONE_KEYS = [
  "zone1_percentage",
  "zone2_percentage",
  "zone3_percentage",
  "zone4_percentage",
  "zone5_percentage",
] as const;

/** Default window: the trailing 12 calendar months, today's month included. */
export const DEFAULT_ZONE_MONTHS = 12;

/** "2026-09-15" → "2026-09". */
function monthOf(date: string): string {
  return date.slice(0, 7);
}

/** The `months` calendar months ending with `today`'s month, oldest first. */
function windowMonths(today: string, months: number): string[] {
  const [year, month] = monthOf(today).split("-").map(Number);
  const result: string[] = [];
  for (let back = months - 1; back >= 0; back -= 1) {
    const date = new Date(Date.UTC(year, month - 1 - back, 1));
    const key = `${date.getUTCFullYear()}-${String(
      date.getUTCMonth() + 1,
    ).padStart(2, "0")}`;
    result.push(key);
  }
  return result;
}

/** One decimal: enough to see a zone shift, short enough for a tooltip. */
function round1(value: number): number {
  return Math.round(value * 10) / 10;
}

/**
 * Average the per-run HR-zone split into one bar per month.
 *
 * Plotting every run as its own stacked bar turned six years of history into a
 * barcode nobody could read (#1149): with ~1000 columns a two-pixel bar cannot
 * show that Zone 2 went from 60% to 81%. Averaging each calendar month and
 * keeping only the trailing `months` gives ~12 bars, which is what "推移" means
 * here. Months without a run are dropped rather than drawn as a gap, so the
 * axis only carries months that actually have a number behind them.
 *
 * Missing zone values read as zero — the source rows store absent zones as
 * null, not as an unknown share.
 */
export function aggregateZoneSharesByMonth(
  points: EfficiencyTrendPoint[],
  today: string,
  months: number = DEFAULT_ZONE_MONTHS,
): MonthlyZoneShare[] {
  const wanted = new Set(windowMonths(today, months));
  const sums = new Map<string, { totals: number[]; count: number }>();

  for (const point of points) {
    const month = monthOf(point.date);
    if (!wanted.has(month)) {
      continue;
    }
    const bucket = sums.get(month) ?? { totals: [0, 0, 0, 0, 0], count: 0 };
    ZONE_KEYS.forEach((key, index) => {
      bucket.totals[index] += point[key] ?? 0;
    });
    bucket.count += 1;
    sums.set(month, bucket);
  }

  return [...sums.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([month, { totals, count }]) => ({
      month,
      shares: totals.map((total) => round1(total / count)) as [
        number,
        number,
        number,
        number,
        number,
      ],
    }));
}
