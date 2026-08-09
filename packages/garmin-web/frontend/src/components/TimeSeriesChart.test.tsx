import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import TimeSeriesChart from "./TimeSeriesChart";
import type { TimeSeriesResponse } from "../types";

// echarts needs a real canvas; mock the modular wrapper out for jsdom.
vi.mock("../lib/echarts", () => ({
  echarts: {
    init: () => ({
      on: vi.fn(),
      getZr: () => ({ on: vi.fn() }),
      setOption: vi.fn(),
      resize: vi.fn(),
      dispose: vi.fn(),
      dispatchAction: vi.fn(),
    }),
  },
}));

const DATA: TimeSeriesResponse = {
  timestamps: [0, 1, 2],
  metrics: {
    heart_rate: [120, 130, 128],
    speed: [3.0, 3.1, 3.05],
  },
};

const LABELS = { heart_rate: "心拍", speed: "ペース" };

describe("TimeSeriesChart", () => {
  it("test_timeseries_chart_has_aria", () => {
    render(<TimeSeriesChart data={DATA} metricLabels={LABELS} />);

    // The canvas is opaque to assistive tech, so the container announces the
    // chart and names the metrics it stacks.
    expect(screen.getByRole("img")).toHaveAccessibleName(
      "心拍・ペースの時系列グラフ",
    );
  });

  it("test_timeseries_chart_aria_without_metrics", () => {
    render(
      <TimeSeriesChart
        data={{ timestamps: [], metrics: {} }}
        metricLabels={LABELS}
      />,
    );

    expect(screen.getByRole("img")).toHaveAccessibleName("時系列グラフ");
  });
});
