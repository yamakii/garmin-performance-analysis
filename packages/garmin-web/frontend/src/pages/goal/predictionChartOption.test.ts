import { describe, expect, it } from "vitest";
import { buildPredictionChartOption } from "./predictionChartOption";
import type { RacePredictionHistory, RacePredictionPoint } from "../../types";

const RACE_DATE = "2026-11-30";
const TARGET = 12000;

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
      point("2026-09-01", 12800),
      point("2026-09-08", 12500, 48.9),
      point("2026-09-15", 12300, 49.4),
    ],
    ...overrides,
  };
}

type CategoryAxis = { data?: string[] };
type MarkLine = { data?: { yAxis?: number; xAxis?: string }[] };
type Series = { name?: string; data?: unknown[]; markLine?: MarkLine };

describe("buildPredictionChartOption", () => {
  it("test_build_prediction_chart_option", () => {
    const option = buildPredictionChartOption(history())!;

    // Race day is the last category, so the markers have a slot to sit on.
    const xAxis = option.xAxis as CategoryAxis;
    expect(xAxis.data).toHaveLength(4);
    expect(xAxis.data![3]).toBe(RACE_DATE);

    const series = option.series as Series[];
    // The prediction line stops before race day.
    expect(series[0].data).toHaveLength(4);
    expect(series[0].data![3]).toBeNull();

    const markLine = series[0].markLine?.data ?? [];
    expect(markLine.map((mark) => mark.yAxis)).toContain(TARGET);
    expect(markLine.map((mark) => mark.xAxis)).toContain(RACE_DATE);

    // The required slope runs from the latest prediction to the target.
    expect(series[1].data![0]).toEqual(["2026-09-15", 12300]);
    expect(series[1].data![1]).toEqual([RACE_DATE, TARGET]);
  });

  it("test_build_prediction_chart_option_empty", () => {
    // Nothing to plot at all.
    expect(buildPredictionChartOption(history({ series: [] }))).toBeNull();

    // A goal without a race date: no extra category, no vertical marker, and
    // no slope line (there is no day to converge on).
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
    const xAxis = undated.xAxis as CategoryAxis;
    expect(xAxis.data).toEqual(["2026-09-01", "2026-09-08", "2026-09-15"]);

    const series = undated.series as Series[];
    expect(series).toHaveLength(1);
    expect(series[0].data).toHaveLength(3);
    const markLine = series[0].markLine?.data ?? [];
    expect(markLine.every((mark) => mark.xAxis === undefined)).toBe(true);
    expect(markLine.map((mark) => mark.yAxis)).toEqual([TARGET]);
  });
});
