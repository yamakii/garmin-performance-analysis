import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TimeSeriesChart, {
  paceAxisBounds,
  timeSeriesHeight,
} from "./TimeSeriesChart";
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
  axisLabel?: {
    hideOverlap?: boolean;
    formatter?: (value: number) => string;
  };
  min?: number;
  max?: number;
  interval?: number;
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

  it("test_time_series_axes_show_three_labels", () => {
    render(
      <TimeSeriesChart
        data={{
          timestamps: [0, 1, 2],
          metrics: { heart_rate: [100, 130, 160], speed: [3.0, 3.1, 3.05] },
        }}
        metricLabels={LABELS}
      />,
    );

    const option = lastOption();
    // Every band shows exactly three labels (min, mid, max) on round
    // values, not ECharts' own tick choice (Issue #1170).
    for (const axis of option.yAxis) {
      expect(axis.axisLabel?.hideOverlap).toBe(true);
      expect(axis.min).toBeDefined();
      expect(axis.max).toBeDefined();
      expect(axis.interval).toBeDefined();
      expect((axis.max! - axis.min!) / axis.interval!).toBe(2);
    }
    const [hr] = option.yAxis;
    expect(hr).toMatchObject({ min: 100, max: 160, interval: 30 });
  });

  it("test_pace_axis_labels_on_half_minutes", () => {
    const speeds = [2.5, 2.0, 1.6, 2.2, 1.9, 2.1, 2.4, 1.8, 2.3, 2.0];
    render(
      <TimeSeriesChart
        data={{
          timestamps: speeds.map((_, i) => i),
          metrics: { heart_rate: speeds.map(() => 140), speed: speeds },
        }}
        metricLabels={LABELS}
      />,
    );

    const [, pace] = lastOption().yAxis;
    // Pace's unit is 30 seconds, so every labelled value lands on a whole
    // or half minute — never the 7:04-style ragged split (Issue #1170).
    expect(pace.min! % 30).toBe(0);
    expect(pace.interval! % 30).toBe(0);
    expect(pace.axisLabel?.formatter?.(420)).toBe("7:00");
  });

  it("test_hr_ceiling_inside_axis", () => {
    render(
      <TimeSeriesChart
        data={{
          timestamps: [0, 1, 2],
          metrics: { heart_rate: [120, 135, 145], speed: [3.0, 3.1, 3.05] },
        }}
        metricLabels={LABELS}
        hrCeiling={150}
      />,
    );

    const [hr] = lastOption().yAxis;
    // The dashed ceiling line must always land inside the plotted range.
    expect(hr.max!).toBeGreaterThanOrEqual(150);
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

  it("test_pace_axis_bounded_only_on_the_pace_grid", () => {
    // 8:20/km throughout, with one traffic-light stop at 16:40/km; heart
    // rate holds steady except one spike, so the two axes can be told
    // apart.
    const speeds = Array.from({ length: 40 }, () => 2.0);
    speeds[20] = 1.0;
    const heartRates = Array.from({ length: 40 }, () => 130);
    heartRates[25] = 220;
    render(
      <TimeSeriesChart
        data={{
          timestamps: speeds.map((_, i) => i),
          metrics: { heart_rate: heartRates, speed: speeds },
        }}
        metricLabels={LABELS}
      />,
    );

    const [hr, pace] = lastOption().yAxis;
    // The stop sits outside the plotted range, so the robust bounds keep
    // the running paces filling the whole grid (#1148)...
    expect(pace.max).toBeLessThan(700);
    expect(pace.min).toBeGreaterThan(300);
    // ...while heart rate keeps its plain min/max span, spike included:
    // only the pace band clips outliers via the robust range.
    expect(hr.max).toBeGreaterThanOrEqual(220);
  });
});

describe("timeSeriesHeight", () => {
  it("test_time_series_height", () => {
    // The default pair fits the Morning Brief's 260px (#1153)...
    expect(timeSeriesHeight(2)).toBe(260);
    expect(timeSeriesHeight(3)).toBe(360);
    // ...and every metric toggled on adds exactly one grid band, instead of
    // re-proportioning the grids already drawn.
    expect(timeSeriesHeight(3) - timeSeriesHeight(2)).toBe(
      timeSeriesHeight(4) - timeSeriesHeight(3),
    );
  });
});

describe("paceAxisBounds", () => {
  it("test_pace_axis_bounds_ignores_stop_spikes", () => {
    const paces = [
      ...Array.from({ length: 200 }, () => 500),
      ...Array.from({ length: 3 }, () => 1000),
    ];

    const bounds = paceAxisBounds(paces);

    // The three 16:40/km stops must not stretch the axis around the 8:20/km
    // the run was actually held at.
    expect(bounds).not.toBeNull();
    expect(bounds!.max).toBeLessThan(700);
    expect(bounds!.min).toBeGreaterThan(300);
  });

  it("test_pace_axis_bounds_insufficient_data", () => {
    // Nothing to bound: the axis falls back to `scale: true`.
    expect(paceAxisBounds([null, null])).toBeNull();
    expect(paceAxisBounds([500])).toBeNull();
  });
});
