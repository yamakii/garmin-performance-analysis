import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import VolumeBlock, { volumeSummaryLine } from "./VolumeBlock";
import type { VolumeTrendPoint } from "../../api/trends";

// echarts needs a real canvas; mock the modular wrapper out for jsdom.
vi.mock("../../lib/echarts", () => ({
  echarts: {
    init: () => ({
      setOption: vi.fn(),
      resize: vi.fn(),
      dispose: vi.fn(),
    }),
  },
}));

/** Twelve weeks ending 62.7 km, with the last four averaging 58.1 km. */
const WEEKS: VolumeTrendPoint[] = [
  40.0, 42.0, 45.0, 44.0, 48.0, 50.0, 46.0, 52.0, 52.0, 55.0, 62.7, 62.7,
].map((distance_km, index) => ({
  bucket: `2026-W${String(index + 1).padStart(2, "0")}`,
  distance_km,
  duration_seconds: Math.round(distance_km * 340),
  run_count: 5,
}));

describe("VolumeBlock", () => {
  it("test_volume_summary_line", () => {
    expect(volumeSummaryLine(WEEKS, "week")).toBe(
      "今週 62.7km · 4週平均 58.1",
    );
    expect(volumeSummaryLine(WEEKS, "month")).toBe(
      "今月 62.7km · 4ヶ月平均 58.1",
    );
    expect(volumeSummaryLine([], "week")).toBe("");
  });

  it("prints the summary line above the chart", () => {
    render(<VolumeBlock data={WEEKS} granularity="week" />);

    expect(
      screen.getByText(/今週 62\.7km · 4週平均 58\.1 · 5回/),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("走行量の棒グラフ")).toBeInTheDocument();
  });

  it("renders an empty state without a chart", () => {
    render(<VolumeBlock data={[]} granularity="week" />);

    expect(screen.getByText("データがありません")).toBeInTheDocument();
    expect(screen.queryByLabelText("走行量の棒グラフ")).toBeNull();
  });
});
