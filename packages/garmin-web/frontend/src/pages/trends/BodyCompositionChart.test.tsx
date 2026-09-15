import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import BodyCompositionChart from "./BodyCompositionChart";
import type { BodyCompositionTrend } from "../../types";

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
});
