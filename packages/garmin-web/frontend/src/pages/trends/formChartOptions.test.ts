import { MarkAreaComponent } from "echarts/components";
import { describe, expect, it } from "vitest";
import {
  buildDeltaChartOption,
  buildScoreChartOption,
} from "./formChartOptions";
import { REGISTERED_ECHARTS_MODULES } from "../../lib/echarts";
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

type ValueAxis = {
  min?: number;
  max?: number;
  scale?: boolean;
  interval?: number;
};
type Grid = { top?: number; bottom?: number };
type Legend = { top?: number };
type MarkArea = { data?: unknown[] };
type MarkLine = { data?: { yAxis?: number }[] };
type Series = {
  name?: string;
  data?: unknown[];
  markArea?: MarkArea;
  markLine?: MarkLine;
};

describe("echarts registration", () => {
  it("test_markarea_component_registered", () => {
    // The score panel's quality bands are markAreas: without the component
    // registered they are configured, accepted and silently never painted.
    expect(REGISTERED_ECHARTS_MODULES).toContain(MarkAreaComponent);
  });
});

describe("buildScoreChartOption", () => {
  it("test_buildScoreChartOption_axis_has_headroom", () => {
    const option = buildScoreChartOption([point()]);
    const yAxis = option.yAxis as ValueAxis;
    expect(yAxis.min!).toBeLessThan(1);
    expect(yAxis.max!).toBeGreaterThan(5);
    expect(yAxis.interval).toBe(1);
  });

  it("test_buildScoreChartOption_band_and_threshold_lines", () => {
    // One faint band for the good zone, and the two quality marks as dotted
    // threshold lines (Morning Brief §Charts) instead of three stacked tints.
    const option = buildScoreChartOption([point()]);
    const series = option.series as Series[];
    expect(series[0].markArea?.data).toHaveLength(1);
    expect(series[0].markLine?.data?.map((d) => d.yAxis)).toEqual([3.5, 2]);
  });

  it("test_buildScoreChartOption_maps_overall_score", () => {
    const option = buildScoreChartOption([point({ overall_score: 3.2 })]);
    const series = option.series as Series[];
    expect(series[0].data).toEqual([3.2]);
  });
});

describe("buildDeltaChartOption", () => {
  it("test_buildDeltaChartOption_distinct_colors", () => {
    const option = buildDeltaChartOption([point()]);
    const colors = option.color as string[];
    expect(colors).toHaveLength(3);
    expect(new Set(colors).size).toBe(3);
  });

  it("test_buildDeltaChartOption_has_zero_baseline", () => {
    const option = buildDeltaChartOption([point()]);
    const series = option.series as Series[];
    const hasZeroBaseline = series.some((s) =>
      s.markLine?.data?.some((d) => d.yAxis === 0),
    );
    expect(hasZeroBaseline).toBe(true);
  });

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

  it("test_form_delta_legend_does_not_overlap", () => {
    // ECharts 6 puts a legend at the bottom by default. On a 180px panel that
    // is the same strip the date labels need, so the key has to move to the
    // top — and the grid has to leave room for it there (#1142).
    const option = buildDeltaChartOption([point()]);
    const legend = option.legend as Legend | undefined;
    const grid = option.grid as Grid;

    expect(grid).toBeDefined();
    if (legend !== undefined) {
      expect(legend.top).toBe(0);
      expect(grid.top!).toBeGreaterThanOrEqual(28);
    }
  });
});
