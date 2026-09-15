import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TimeSeriesChart from "./TimeSeriesChart";
import type { TimeSeriesResponse } from "../types";

// echarts needs a real canvas; mock the modular wrapper out for jsdom and
// keep the options it was handed so the chart contract can be asserted.
const { setOption } = vi.hoisted(() => ({ setOption: vi.fn() }));

vi.mock("../lib/echarts", () => ({
  echarts: {
    init: () => ({
      on: vi.fn(),
      getZr: () => ({ on: vi.fn() }),
      setOption,
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

/** The slice of the ECharts option this component's contract covers. */
interface AxisOption {
  splitLine?: { show?: boolean };
  axisLine?: { show?: boolean };
}

interface SeriesOption {
  markLine?: {
    data: { yAxis: number }[];
    lineStyle: { type: string };
    label: { formatter: string };
  };
}

interface ChartOption {
  xAxis: AxisOption[];
  yAxis: AxisOption[];
  series: SeriesOption[];
}

/** The option object of the most recent `setOption` call. */
function lastOption(): ChartOption {
  const calls = setOption.mock.calls;
  expect(calls.length).toBeGreaterThan(0);
  return calls[calls.length - 1][0] as ChartOption;
}

beforeEach(() => {
  setOption.mockClear();
});

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

  it("test_timeseries_chart_grid_lines_are_horizontal_only", () => {
    render(<TimeSeriesChart data={DATA} metricLabels={LABELS} />);

    const option = lastOption();
    // Morning Brief charts carry no axis lines and no vertical grid: the
    // horizontal Y rules are the only frame (#1118).
    for (const axis of option.xAxis) {
      expect(axis.splitLine?.show).toBe(false);
      expect(axis.axisLine?.show).toBe(false);
    }
    for (const axis of option.yAxis) {
      expect(axis.axisLine?.show).toBe(false);
      expect(axis.splitLine?.show).not.toBe(false);
    }
  });

  it("test_hr_ceiling_marks_the_heart_rate_grid", () => {
    render(
      <TimeSeriesChart data={DATA} metricLabels={LABELS} hrCeiling={150} />,
    );

    const option = lastOption();
    const [hr, pace] = option.series;
    // The prescribed cap is a dotted line on the HR grid, labelled with the
    // number it stands for...
    expect(hr.markLine?.data).toEqual([{ yAxis: 150 }]);
    expect(hr.markLine?.lineStyle.type).toBe("dashed");
    expect(hr.markLine?.label.formatter).toBe("上限 150");
    // ...and nowhere else: a pace grid has no heart-rate ceiling.
    expect(pace.markLine).toBeUndefined();
  });

  it("test_hr_ceiling_absent_without_prescription", () => {
    render(<TimeSeriesChart data={DATA} metricLabels={LABELS} />);

    for (const series of lastOption().series) {
      expect(series.markLine).toBeUndefined();
    }
  });
});
