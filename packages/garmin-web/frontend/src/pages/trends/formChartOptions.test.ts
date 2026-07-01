import { describe, expect, it } from "vitest";
import {
  buildDeltaChartOption,
  buildScoreChartOption,
} from "./formChartOptions";
import type { FormTrendPoint } from "../../api/trends";

function point(overrides: Partial<FormTrendPoint> = {}): FormTrendPoint {
  return {
    date: "2025-01-01",
    overall_score: 3,
    gct_delta: 0,
    vo_delta: 0,
    vr_delta: 0,
    ...overrides,
  };
}

type ValueAxis = { min?: number; max?: number; scale?: boolean };
type Series = { name?: string; data?: unknown[] };

describe("buildScoreChartOption", () => {
  it("test_buildScoreChartOption_fixes_1_to_5_axis", () => {
    const option = buildScoreChartOption([point()]);
    const yAxis = option.yAxis as ValueAxis;
    expect(yAxis.min).toBe(1);
    expect(yAxis.max).toBe(5);

    const series = option.series as Series[];
    expect(series).toHaveLength(1);
    expect(series[0].name).toBe("総合スコア");
  });

  it("test_buildScoreChartOption_maps_overall_score", () => {
    const option = buildScoreChartOption([point({ overall_score: 3.2 })]);
    const series = option.series as Series[];
    expect(series[0].data).toEqual([3.2]);
  });
});

describe("buildDeltaChartOption", () => {
  it("test_buildDeltaChartOption_uses_robust_bounds", () => {
    const data = [
      point({ vr_delta: -2 }),
      point({ vr_delta: 0 }),
      point({ vr_delta: 1 }),
      point({ vr_delta: 3 }),
      point({ vr_delta: 4 }),
      point({ vr_delta: 5 }),
      point({ vr_delta: 170 }),
    ];
    const option = buildDeltaChartOption(data);
    const yAxis = option.yAxis as ValueAxis;
    expect(yAxis.max).toBeDefined();
    expect(yAxis.max!).toBeLessThan(20);
  });

  it("test_buildDeltaChartOption_has_three_series", () => {
    const option = buildDeltaChartOption([point()]);
    const series = option.series as Series[];
    expect(series).toHaveLength(3);
    expect(series.map((s) => s.name)).toEqual(["GCT Δ%", "VO Δcm", "VR Δ%"]);
  });

  it("test_buildDeltaChartOption_falls_back_to_scale_when_empty", () => {
    const option = buildDeltaChartOption([]);
    const yAxis = option.yAxis as ValueAxis;
    expect(yAxis.scale).toBe(true);
    expect(yAxis.min).toBeUndefined();
    expect(yAxis.max).toBeUndefined();
  });
});
