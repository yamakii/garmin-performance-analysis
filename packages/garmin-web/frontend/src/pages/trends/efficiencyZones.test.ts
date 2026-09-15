import { describe, expect, it } from "vitest";
import { aggregateZoneSharesByMonth } from "./efficiencyZones";
import type { EfficiencyTrendPoint } from "../../api/trends";

function run(
  date: string,
  shares: Partial<Record<1 | 2 | 3 | 4 | 5, number>>,
): EfficiencyTrendPoint {
  return {
    date,
    aerobic_efficiency: "good",
    primary_zone: "Zone 2",
    zone1_percentage: shares[1] ?? 0,
    zone2_percentage: shares[2] ?? 0,
    zone3_percentage: shares[3] ?? 0,
    zone4_percentage: shares[4] ?? 0,
    zone5_percentage: shares[5] ?? 0,
  };
}

describe("aggregateZoneSharesByMonth", () => {
  it("test_aggregate_zone_shares_by_month", () => {
    const points = [
      run("2026-08-02", { 2: 80, 3: 20 }),
      run("2026-08-20", { 2: 60, 3: 40 }),
      run("2026-09-13", { 1: 4, 2: 81, 3: 15 }),
    ];

    expect(aggregateZoneSharesByMonth(points, "2026-09-15")).toEqual([
      { month: "2026-08", shares: [0, 70, 30, 0, 0] },
      { month: "2026-09", shares: [4, 81, 15, 0, 0] },
    ]);
  });

  it("test_aggregate_zone_shares_window", () => {
    // One run a month from 2024-01 to 2026-09: only the trailing 12 months
    // survive, oldest first.
    const points: EfficiencyTrendPoint[] = [];
    for (let year = 2024; year <= 2026; year += 1) {
      for (let month = 1; month <= 12; month += 1) {
        if (year === 2026 && month > 9) {
          break;
        }
        points.push(
          run(`${year}-${String(month).padStart(2, "0")}-05`, { 2: 100 }),
        );
      }
    }

    const monthly = aggregateZoneSharesByMonth(points, "2026-09-15", 12);

    expect(monthly).toHaveLength(12);
    expect(monthly[0].month).toBe("2025-10");
    expect(monthly[11].month).toBe("2026-09");
  });

  it("test_aggregate_zone_shares_skips_empty_months", () => {
    // A month without a run is dropped, not drawn as a zero-height bar.
    const monthly = aggregateZoneSharesByMonth(
      [run("2026-07-04", { 2: 90, 3: 10 }), run("2026-09-13", { 2: 100 })],
      "2026-09-15",
    );

    expect(monthly.map((m) => m.month)).toEqual(["2026-07", "2026-09"]);
  });

  it("test_aggregate_zone_shares_reads_null_as_zero", () => {
    const point: EfficiencyTrendPoint = {
      date: "2026-09-13",
      aerobic_efficiency: null,
      primary_zone: null,
      zone1_percentage: null,
      zone2_percentage: 100,
      zone3_percentage: null,
      zone4_percentage: null,
      zone5_percentage: null,
    };

    expect(aggregateZoneSharesByMonth([point], "2026-09-15")).toEqual([
      { month: "2026-09", shares: [0, 100, 0, 0, 0] },
    ]);
  });
});
