import { describe, expect, it } from "vitest";
import { robustAxisBounds } from "./robustBounds";

describe("robustAxisBounds", () => {
  it("test_robustAxisBounds_clips_extreme_outlier", () => {
    const bounds = robustAxisBounds([-5, -2, 0, 1, 3, 4, 5, 170]);
    expect(bounds).not.toBeNull();
    expect(bounds!.max).toBeLessThan(20);
  });

  it("test_robustAxisBounds_ignores_nulls", () => {
    const bounds = robustAxisBounds([null, 1, 2, null, 3]);
    expect(bounds).not.toBeNull();
    expect(bounds!.min).toBeLessThanOrEqual(1);
    expect(bounds!.max).toBeGreaterThanOrEqual(3);
    expect(bounds!.min).toBeGreaterThan(0);
    expect(bounds!.max).toBeLessThan(4);
  });

  it("test_robustAxisBounds_empty_returns_null", () => {
    expect(robustAxisBounds([])).toBeNull();
  });

  it("test_robustAxisBounds_all_null_returns_null", () => {
    expect(robustAxisBounds([null, undefined, NaN])).toBeNull();
  });

  it("test_robustAxisBounds_constant_series_nonzero_span", () => {
    const bounds = robustAxisBounds([4, 4, 4, 4]);
    expect(bounds).not.toBeNull();
    expect(bounds!.min).toBeLessThan(bounds!.max);
  });

  it("test_robustAxisBounds_normal_range_preserved", () => {
    const values = [-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5];
    const bounds = robustAxisBounds(values);
    expect(bounds).not.toBeNull();
    for (const v of values) {
      expect(v).toBeGreaterThanOrEqual(bounds!.min);
      expect(v).toBeLessThanOrEqual(bounds!.max);
    }
  });
});
