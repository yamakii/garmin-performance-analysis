import { describe, expect, it } from "vitest";
import { axisUnitFor, threeTickAxis } from "./timeSeriesAxis";

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
