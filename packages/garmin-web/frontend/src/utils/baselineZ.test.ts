import { describe, expect, it } from "vitest";
import type { MetricBaseline, WellnessBaselineDeviation } from "../types";
import {
  baselineZRows,
  zBandStyle,
  zBarStyle,
  zDirection,
  zDotStyle,
  type ZRow,
} from "./baselineZ";

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

describe("zDirection", () => {
  it("test_z_direction_follows_the_metric_polarity", () => {
    // Ground contact time is worse when high: a positive z points the bad way.
    expect(zDirection(1.2, true)).toBe("unfavorable");
    expect(zDirection(-1.2, true)).toBe("favorable");
    // Cadence is worse when low, so the same signs read the other way round.
    expect(zDirection(1.2, false)).toBe("favorable");
    expect(zDirection(-1.2, false)).toBe("unfavorable");
    // No reading, no direction.
    expect(zDirection(null, true)).toBe("neutral");
    expect(zDirection(0, true)).toBe("neutral");
  });
});

describe("zBarStyle", () => {
  it("test_z_bar_style_takes_any_oriented_row", () => {
    // Any row that knows how far out it is and which way that is can be drawn
    // by the same helper — the wellness panel is not a special case (#1252).
    expect(zBarStyle({ z: 1.5, direction: "unfavorable" })).toEqual({
      left: "50%",
      width: "25%",
    });
    expect(zBarStyle({ z: 1.5, direction: "favorable" })).toEqual({
      left: "25%",
      width: "25%",
    });
  });


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
    const offScale: ZRow = {
      key: "rhr",
      label: "安静時心拍",
      z: -4,
      adverse: false,
      outside: true,
      direction: "favorable",
    };
    expect(zBarStyle(offScale)).toEqual({ left: "0%", width: "50%" });

    // No reading draws no bar.
    const unread: ZRow = {
      key: "hrv",
      label: "HRV",
      z: null,
      adverse: false,
      outside: false,
      direction: "neutral",
    };
    expect(zBarStyle(unread).width).toBe("0%");
  });
});

describe("zBandStyle / zDotStyle", () => {
  it("test_z_band_is_the_middle_two_thirds", () => {
    // The track is ±3σ and the band is ±2σ, so the band is fixed geometry the
    // dot can be read against (#1270).
    expect(zBandStyle()).toEqual({ left: "16.67%", width: "66.67%" });
  });

  it("test_z_dot_sits_at_the_reading", () => {
    // 0.58σ on the unfavourable side: just right of centre, inside the band.
    expect(zDotStyle({ z: 0.58, direction: "unfavorable" })).toEqual({
      left: "59.67%",
    });
    expect(zDotStyle({ z: 2.1, direction: "favorable" })).toEqual({
      left: "15%",
    });
    // Beyond the track it stops at the end rather than leaving it.
    expect(zDotStyle({ z: 4, direction: "unfavorable" })).toEqual({
      left: "100%",
    });
    // A reading exactly on the baseline sits on the centre line.
    expect(zDotStyle({ z: 0, direction: "neutral" })).toEqual({ left: "50%" });
    // No reading, no mark.
    expect(zDotStyle({ z: null, direction: "neutral" })).toBeNull();
  });
});
