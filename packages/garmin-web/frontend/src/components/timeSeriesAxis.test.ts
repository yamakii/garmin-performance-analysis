import { describe, expect, it } from "vitest";
import { axisRangeFor, axisUnitFor, threeTickAxis } from "./timeSeriesAxis";

describe("threeTickAxis", () => {
  it("test_three_tick_axis_heart_rate", () => {
    expect(threeTickAxis(100, 160, 10)).toEqual({
      min: 100,
      max: 160,
      interval: 30,
    });
  });

  it("test_three_tick_axis_extends_odd_span", () => {
    expect(threeTickAxis(424, 610, 30)).toEqual({
      min: 420,
      max: 660,
      interval: 120,
    });
  });

  it("test_three_tick_axis_flat_series", () => {
    expect(threeTickAxis(150, 150, 10)).toEqual({
      min: 140,
      max: 160,
      interval: 10,
    });
  });
});

describe("axisUnitFor", () => {
  it("test_axis_unit_for_known_and_unknown", () => {
    expect(axisUnitFor("heart_rate", 0, 1)).toBe(10);
    expect(axisUnitFor("speed", 0, 1)).toBe(30);
    expect(axisUnitFor("unknown", 0, 37)).toBe(10);
    expect(axisUnitFor("unknown", 0, 3.7)).toBe(1);
  });
});

describe("axisRangeFor", () => {
  it("test_axis_range_ignores_stop_zeros_for_cadence", () => {
    // A run holds still at traffic lights: cadence samples drop to 0 while
    // stopped. Those stops must not stretch the axis around the ~180spm the
    // run was actually held at.
    const values = [
      ...Array.from({ length: 40 }, () => 180),
      ...Array.from({ length: 3 }, () => 0),
    ];

    const range = axisRangeFor("cadence", values);

    expect(range.lo).toBeGreaterThan(150);
    expect(range.hi).toBeLessThanOrEqual(200);
  });

  it("test_axis_range_ignores_single_spike_for_ground_contact_time", () => {
    // A lone sensor spike (~460ms) must not stretch the axis around the
    // ~270ms the run was actually held at.
    const values = [...Array.from({ length: 40 }, () => 270), 460];

    const range = axisRangeFor("ground_contact_time", values);

    expect(range.hi).toBeLessThan(400);
  });

  it("test_axis_range_keeps_full_span_for_heart_rate_and_elevation", () => {
    // Heart rate and elevation are not in ROBUST_RANGE_METRICS: the plain
    // min/max is the real data (warm-up ramp / terrain change), not noise.
    expect(axisRangeFor("heart_rate", [100, 145, 150, 148, 160])).toEqual({
      lo: 100,
      hi: 160,
    });
    expect(axisRangeFor("elevation", [-5, 0, 15])).toEqual({
      lo: -5,
      hi: 15,
    });
  });

  it("test_axis_range_heart_rate_includes_ceiling", () => {
    // The prescribed HR ceiling must always land inside the plotted range,
    // even when every sample stayed under it.
    const range = axisRangeFor("heart_rate", [120, 135, 145], 150);

    expect(range.hi).toBe(150);
  });

  it("test_axis_range_falls_back_with_too_little_data", () => {
    // Fewer than two finite values: nothing to compute percentiles from, so
    // axisRangeFor falls back to the plain min/max without raising.
    expect(axisRangeFor("cadence", [180])).toEqual({ lo: 180, hi: 180 });
  });
});
