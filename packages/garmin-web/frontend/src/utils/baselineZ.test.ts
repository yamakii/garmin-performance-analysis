import { describe, expect, it } from "vitest";
import type { MetricBaseline, WellnessBaselineDeviation } from "../types";
import { baselineZRows, zBarStyle, type ZRow } from "./baselineZ";

function metric(
  name: MetricBaseline["metric"],
  overrides: Partial<MetricBaseline> = {},
): MetricBaseline {
  return {
    metric: name,
    mean: 50,
    std: 4,
    today: 50,
    z: 0,
    flag: "within",
    adverse: false,
    n: 30,
    ...overrides,
  };
}

function deviation(
  overrides: Partial<WellnessBaselineDeviation> = {},
): WellnessBaselineDeviation {
  return {
    date: "2026-09-13",
    hrv: metric("hrv"),
    rhr: metric("rhr"),
    readiness: metric("readiness"),
    overall_flag: false,
    ...overrides,
  };
}

function row(rows: ZRow[], key: ZRow["key"]): ZRow {
  const found = rows.find((candidate) => candidate.key === key);
  if (found == null) throw new Error(`missing row: ${key}`);
  return found;
}

describe("baselineZRows", () => {
  it("test_baseline_z_rows_direction", () => {
    const rows = baselineZRows(
      deviation({
        hrv: metric("hrv", { z: -0.4, flag: "within" }),
        rhr: metric("rhr", { z: 1.8, flag: "high", adverse: true }),
        readiness: metric("readiness", { z: 0.3 }),
      }),
    );

    expect(rows.map((r) => r.key)).toEqual(["hrv", "rhr", "readiness"]);

    // A low HRV is the bad direction, but not yet far enough to be 基準外.
    expect(row(rows, "hrv")).toMatchObject({
      direction: "unfavorable",
      outside: false,
      z: -0.4,
    });
    // A high resting HR is bad in the opposite sign, and |z| > 1.5.
    expect(row(rows, "rhr")).toMatchObject({
      direction: "unfavorable",
      outside: true,
      adverse: true,
    });
    // Readiness above the baseline is simply good news.
    expect(row(rows, "readiness").direction).toBe("favorable");
  });

  it("reports an insufficient baseline as no reading at all", () => {
    const rows = baselineZRows(
      deviation({
        hrv: metric("hrv", { z: 2.5, flag: "insufficient", mean: null }),
      }),
    );

    expect(row(rows, "hrv")).toMatchObject({
      z: null,
      outside: false,
      direction: "neutral",
    });
  });
});

describe("zBarStyle", () => {
  it("test_z_bar_style_clamps", () => {
    const rows = baselineZRows(
      deviation({
        rhr: metric("rhr", { z: 1.8, flag: "high", adverse: true }),
      }),
    );

    // Unfavourable: the bar grows right from the centre, |z| / 3 of the half.
    expect(zBarStyle(row(rows, "rhr"))).toEqual({
      left: "50%",
      width: "30%",
    });

    // Favourable and off the scale: clamped to the full left half.
    expect(
      zBarStyle({
        key: "rhr",
        label: "安静時心拍",
        z: -4,
        adverse: false,
        outside: true,
        direction: "favorable",
      }),
    ).toEqual({ left: "0%", width: "50%" });

    // No reading draws no bar.
    expect(
      zBarStyle({
        key: "hrv",
        label: "HRV",
        z: null,
        adverse: false,
        outside: false,
        direction: "neutral",
      }).width,
    ).toBe("0%");
  });
});
