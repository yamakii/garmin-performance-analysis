import { describe, expect, it } from "vitest";
import { toDeltaSeries } from "./bodyCompositionDelta";
import type { BodyCompositionSeriesPoint } from "../../types";

function point(
  date: string,
  weight_kg: number | null,
  fat_mass: number | null,
  lean_mass: number | null,
): BodyCompositionSeriesPoint {
  return { date, weight_kg, fat_mass, lean_mass };
}

describe("toDeltaSeries", () => {
  it("test_to_delta_series", () => {
    const series = [
      point("2026-06-01", 80.0, 20.8, 59.2),
      point("2026-06-08", 79.2, null, 58.6),
      point("2026-06-15", 78.2, 20.4, 57.8),
    ];

    const deltas = toDeltaSeries(series);

    expect(deltas.weight).toEqual([0, -0.8, -1.8]);
    expect(deltas.fat).toEqual([0, null, -0.4]);
    expect(deltas.lean).toEqual([0, -0.6, -1.4]);
  });

  it("test_to_delta_series_leading_null", () => {
    const series = [
      point("2026-06-01", null, null, null),
      point("2026-06-08", 79.0, null, null),
      point("2026-06-15", 78.5, null, null),
    ];

    const deltas = toDeltaSeries(series);

    // The first non-null reading becomes the baseline (0), not index 0.
    expect(deltas.weight).toEqual([null, 0, -0.5]);
  });
});
