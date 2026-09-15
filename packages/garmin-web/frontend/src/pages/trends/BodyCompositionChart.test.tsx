import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import BodyCompositionChart from "./BodyCompositionChart";
import type { BodyCompositionTrend } from "../../types";

// echarts requires a real canvas; mock the modular wrapper out for jsdom and
// keep the option it was handed so the chart contract can be asserted.
const { setOption } = vi.hoisted(() => ({ setOption: vi.fn() }));

vi.mock("../../lib/echarts", () => ({
  echarts: {
    init: () => ({
      setOption,
      resize: vi.fn(),
      dispose: vi.fn(),
    }),
  },
}));

/** The slice of the ECharts option this chart's contract covers. */
interface ChartOption {
  grid: { right?: number };
  legend?: unknown;
  xAxis: { axisLabel?: { hideOverlap?: boolean } };
  yAxis: { scale?: boolean };
  series: {
    type?: string;
    stack?: string;
    yAxisIndex?: number;
    markLine?: { data: { yAxis: number }[] };
  }[];
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

// Latest weight 78.847 must render via formatNumber as "78.8".
const TREND: BodyCompositionTrend = {
  weeks: 12,
  series: [
    { date: "2025-10-06", weight_kg: 80.0, fat_mass: 17.6, lean_mass: 62.4 },
    { date: "2025-10-07", weight_kg: 78.847, fat_mass: 16.4, lean_mass: 62.4 },
  ],
  change: {
    delta_weight: -1.2,
    delta_fat: -1.0,
    delta_lean: -0.2,
    lean_loss_ratio: 0.17,
    muscle_loss_warning: false,
  },
  lean_pwr: 4.0,
};

/** 12 weekly points: 80.0 -> 78.0kg, fat 21.0 -> 20.4kg. */
const TWELVE_WEEKS: BodyCompositionTrend = {
  weeks: 12,
  series: Array.from({ length: 12 }, (_, i) => {
    const weight = 80.0 - (2.0 * i) / 11;
    const fat = 21.0 - (0.6 * i) / 11;
    return {
      date: `2025-10-${String(i + 6).padStart(2, "0")}`,
      weight_kg: weight,
      fat_mass: fat,
      lean_mass: weight - fat,
    };
  }),
  change: {
    delta_weight: -2.0,
    delta_fat: -0.6,
    delta_lean: -1.4,
    lean_loss_ratio: 0.7,
    muscle_loss_warning: true,
  },
  lean_pwr: 4.0,
};

describe("BodyCompositionChart", () => {
  it("test_body_composition_readings_are_mono", () => {
    render(<BodyCompositionChart data={TREND} />);

    // The three readings are a definition list of mono numbers (#1120)…
    for (const label of ["体重", "体脂肪", "除脂肪"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    // …and 78.847 is rounded to one decimal by formatNumber -> "78.8".
    const weight = screen.getByText("78.8");
    expect(weight).toHaveClass("font-mono");
    // The raw, unformatted value must never reach the DOM.
    expect(screen.queryByText(/78\.847/)).not.toBeInTheDocument();
    // Each reading carries the period's change under it.
    expect(screen.getByText("今期 -1.2kg")).toBeInTheDocument();
  });

  it("test_body_composition_option_uses_scaled_lines", () => {
    render(<BodyCompositionChart data={TWELVE_WEEKS} />);

    const option = lastOption();
    // A 2kg drift on a 0-based stacked bar is invisible; scaled lines spend
    // the plot height on it instead (#1148).
    for (const series of option.series) {
      expect(series.type).toBe("line");
      expect(series.stack).toBeUndefined();
    }
    expect(option.yAxis.scale).toBe(true);
    // No legend box: it used to be drawn over the bars and the date labels,
    // and the readings above already carry the color key.
    expect(option.legend).toBeUndefined();
  });

  it("test_body_composition_option_single_delta_axis", () => {
    render(<BodyCompositionChart data={TWELVE_WEEKS} />);

    const option = lastOption();
    // One shared y-axis (not an array of two): every series reads its change
    // from the window's first reading, all to the same 0-anchored scale
    // (#1167).
    expect(Array.isArray(option.yAxis)).toBe(false);
    for (const series of option.series) {
      expect(
        series.yAxisIndex === undefined || series.yAxisIndex === 0,
      ).toBe(true);
    }
    // A hairline at 0 marks "no change yet".
    const markLines = option.series.flatMap(
      (series) => series.markLine?.data ?? [],
    );
    expect(markLines.some((mark) => mark.yAxis === 0)).toBe(true);
  });

  it("test_body_composition_last_label_fits", () => {
    render(<BodyCompositionChart data={TWELVE_WEEKS} />);

    const option = lastOption();
    // The centred last date label must not be cut off at the right edge:
    // either there is margin for it, or colliding labels are dropped.
    expect(
      (option.grid.right ?? 0) >= 16 ||
        option.xAxis.axisLabel?.hideOverlap === true,
    ).toBe(true);
  });

  it("test_body_composition_chart_height_160", () => {
    render(<BodyCompositionChart data={TREND} />);

    // The Morning Brief spec (§7) sizes this chart at 160, not the shared
    // 180px Performance charts use (#1167).
    const container = screen.getByRole("img");
    expect(container.style.height).toBe("160px");
  });
});
