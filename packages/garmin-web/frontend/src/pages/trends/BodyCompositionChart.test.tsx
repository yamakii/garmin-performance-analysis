import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import BodyCompositionChart from "./BodyCompositionChart";
import type { BodyCompositionTrend } from "../../types";

// echarts requires a real canvas; mock it out for jsdom.
vi.mock("echarts", () => ({
  init: () => ({
    setOption: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
  }),
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
  it("formats the latest weight via formatNumber (78.847 -> 78.8)", () => {
    render(<BodyCompositionChart data={TREND} />);

    // 78.847 is rounded to one decimal by formatNumber -> "78.8".
    expect(screen.getByText(/最新 78\.8kg/)).toBeInTheDocument();
    // The raw, unformatted value must never reach the DOM.
    expect(screen.queryByText(/78\.847/)).not.toBeInTheDocument();
    // Net weight-loss summary is rendered from the change block.
    expect(screen.getByText(/-1\.2kg/)).toBeInTheDocument();
  });
});
