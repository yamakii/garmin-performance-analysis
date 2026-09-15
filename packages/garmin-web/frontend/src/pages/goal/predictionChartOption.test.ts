import { describe, expect, it } from "vitest";
import { buildPredictionChartOption } from "./predictionChartOption";
import type { RacePredictionHistory, RacePredictionPoint } from "../../types";

const RACE_DATE = "2027-02-14";
const TARGET = 16200;

function point(
  date: string,
  predicted: number,
  vdot = 48.2,
): RacePredictionPoint {
  return {
    date,
    vdot,
    predicted_time_seconds: predicted,
    gap_seconds: predicted - TARGET,
  };
}

function history(
  overrides: Partial<RacePredictionHistory> = {},
): RacePredictionHistory {
  return {
    goal: {
      race_name: "さいたまマラソン",
      race_date: RACE_DATE,
      distance_km: 42.195,
      target_time_seconds: TARGET,
    },
    source: "objective",
    series: [
      point("2026-09-01", 15000),
      point("2026-09-08", 14800, 48.9),
      point("2026-09-15", 14700, 49.4),
    ],
    ...overrides,
  };
}

type TimeAxis = { type?: string; min?: string; max?: string };
type ValueAxis = { splitNumber?: number };
type Grid = { top?: number; bottom?: number };
type MarkLine = { data?: { yAxis?: number; xAxis?: string }[] };
type Series = { name?: string; data?: unknown[]; markLine?: MarkLine };

describe("buildPredictionChartOption", () => {
  it("test_build_prediction_chart_option", () => {
    const option = buildPredictionChartOption(history())!;

    // A time axis running to race day: the five months between the last
    // fitness day and the race are drawn to scale (#1152).
    const xAxis = option.xAxis as TimeAxis;
    expect(xAxis.type).toBe("time");
    expect(xAxis.min).toBe("2026-09-01");
    expect(xAxis.max).toBe(RACE_DATE);

    const series = option.series as Series[];
    // The prediction is [day, seconds] pairs — no padding slot for race day.
    expect(series[0].data).toEqual([
      ["2026-09-01", 15000],
      ["2026-09-08", 14800],
      ["2026-09-15", 14700],
    ]);

    const markLine = series[0].markLine?.data ?? [];
    expect(markLine.map((mark) => mark.yAxis)).toContain(TARGET);
    expect(markLine.map((mark) => mark.xAxis)).toContain(RACE_DATE);

    // The required slope runs from the latest prediction to the target.
    expect(series[1].data).toEqual([
      ["2026-09-15", 14700],
      [RACE_DATE, TARGET],
    ]);
  });

  it("test_build_prediction_chart_option_race_day_in_range", () => {
    // Race day is itself the last fitness day: the axis ends there and the
    // slope line collapses onto that single day.
    const option = buildPredictionChartOption(
      history({
        goal: {
          race_name: "さいたまマラソン",
          race_date: "2026-09-15",
          distance_km: 42.195,
          target_time_seconds: TARGET,
        },
      }),
    )!;

    const xAxis = option.xAxis as TimeAxis;
    expect(xAxis.max).toBe("2026-09-15");

    const series = option.series as Series[];
    expect(series[1].data![1]).toEqual(["2026-09-15", TARGET]);
  });

  it("test_build_prediction_chart_option_empty", () => {
    // Nothing to plot at all.
    expect(buildPredictionChartOption(history({ series: [] }))).toBeNull();

    // A goal without a race date: the axis stops at the last fitness day, and
    // there is no vertical marker and no slope line (no day to converge on).
    const undated = buildPredictionChartOption(
      history({
        goal: {
          race_name: "さいたまマラソン",
          race_date: null,
          distance_km: 42.195,
          target_time_seconds: TARGET,
        },
      }),
    )!;
    const xAxis = undated.xAxis as TimeAxis;
    expect(xAxis.min).toBe("2026-09-01");
    expect(xAxis.max).toBe("2026-09-15");

    const series = undated.series as Series[];
    expect(series).toHaveLength(1);
    expect(series[0].data).toHaveLength(3);
    const markLine = series[0].markLine?.data ?? [];
    expect(markLine.every((mark) => mark.xAxis === undefined)).toBe(true);
    expect(markLine.map((mark) => mark.yAxis)).toEqual([TARGET]);
  });

  it("test_prediction_chart_option_grid", () => {
    const option = buildPredictionChartOption(history())!;

    // Without explicit margins ECharts' default grid leaves 35px of plot in
    // this 180px panel, and the hh:mm:ss labels pile up on each other (#1142).
    const grid = option.grid as Grid;
    expect(grid).toBeDefined();
    expect((grid.top ?? 0) + (grid.bottom ?? 0)).toBeLessThanOrEqual(60);

    // Time labels are the widest in the app; four of them is what fits.
    const yAxis = option.yAxis as ValueAxis;
    expect(yAxis.splitNumber).toBe(3);
  });
});
