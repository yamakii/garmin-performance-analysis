import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import HeatAdjustedBlock from "./HeatAdjustedBlock";
import { fetchHeatAdjustedTrend } from "../../api/trends";
import type { HeatAdjustedTrend } from "../../api/trends";

// echarts requires a real canvas; mock the modular wrapper out for jsdom.
vi.mock("../../lib/echarts", () => ({
  echarts: {
    init: () => ({
      setOption: vi.fn(),
      resize: vi.fn(),
      dispose: vi.fn(),
    }),
  },
}));

const OK_TREND: HeatAdjustedTrend = {
  status: "ok",
  coefficients: { beta_heat: 0.35, ref_temp_c: 15.0, n: 12 },
  neutral_hr_slope: -0.02,
  points: [
    { date: "2025-07-01", temp_c: 28, raw_hr: 150, heat_cost: 4.55, neutral_hr: 145.45 },
    { date: "2025-07-15", temp_c: 32, raw_hr: 154, heat_cost: 5.95, neutral_hr: 148.05 },
  ],
};

const EMPTY_TREND: HeatAdjustedTrend = {
  status: "insufficient_data",
  coefficients: null,
  neutral_hr_slope: null,
  points: [],
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("fetchHeatAdjustedTrend", () => {
  it("test_fetch_heat_adjusted_builds_url", async () => {
    const json = vi.fn().mockResolvedValue(OK_TREND);
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue({ ok: true, json } as unknown as Response);

    await fetchHeatAdjustedTrend(365);

    expect(fetchMock).toHaveBeenCalledWith("/api/trends/heat-adjusted?days=365");
  });
});

describe("HeatAdjustedBlock", () => {
  it("test_heat_adjusted_block_renders_points", () => {
    render(<HeatAdjustedBlock data={OK_TREND} />);

    // Raw + neutral series labels appear in the descriptive caption.
    expect(screen.getByText("生HR")).toBeInTheDocument();
    expect(screen.getByText("気候中立HR")).toBeInTheDocument();
    // The fitted beta_heat coefficient is surfaced as a caption.
    expect(screen.getByText(/β_heat 0\.35 bpm\/°C/)).toBeInTheDocument();
    // The overlay chart is rendered.
    expect(
      screen.getByLabelText("生HRと気候中立HRの推移グラフ"),
    ).toBeInTheDocument();
  });

  it("test_heat_adjusted_block_empty_state", () => {
    render(<HeatAdjustedBlock data={EMPTY_TREND} />);

    expect(
      screen.getByText(/暑熱補正トレンドを算出するにはランが不足/),
    ).toBeInTheDocument();
    // No chart is rendered in the empty state.
    expect(
      screen.queryByLabelText("生HRと気候中立HRの推移グラフ"),
    ).not.toBeInTheDocument();
  });
});
