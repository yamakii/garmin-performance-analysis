import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ObjectiveFitnessBlock from "./ObjectiveFitnessBlock";
import type { ObjectiveFitnessTrend } from "../../api/trends";

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

const DATA: ObjectiveFitnessTrend = {
  objective_curve: [
    { date: "2026-04-01", vdot: 34.5, source_distance_km: 5.0 },
    { date: "2026-05-01", vdot: 35.2, source_distance_km: 5.0 },
  ],
  garmin_vo2max: [
    { date: "2026-04-01", value: 44.6 },
    { date: "2026-05-01", value: 45.1 },
  ],
  optimism_gap: {
    garmin_vdot: 44.6,
    objective_vdot: 35.2,
    gap_vdot: 9.4,
    gap_pace_sec_per_km: 63,
  },
};

const EMPTY_DATA: ObjectiveFitnessTrend = {
  objective_curve: [],
  garmin_vo2max: [],
  optimism_gap: null,
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ObjectiveFitnessBlock", () => {
  it("test_objective_fitness_block_renders_both_series", () => {
    render(<ObjectiveFitnessBlock data={DATA} />);

    // Both overlaid series labels appear in the descriptive caption.
    expect(screen.getByText("Garmin VO2max")).toBeInTheDocument();
    expect(screen.getByText("客観VDOT")).toBeInTheDocument();
    // The overlay chart is rendered.
    expect(
      screen.getByLabelText("実走VDOTとGarmin VO2maxの推移グラフ"),
    ).toBeInTheDocument();
  });

  it("test_objective_fitness_block_shows_gap", () => {
    render(<ObjectiveFitnessBlock data={DATA} />);

    // The optimism gap pace is surfaced in the annotation.
    expect(screen.getByText(/63 s\/km/)).toBeInTheDocument();
  });

  it("test_objective_fitness_block_empty_state", () => {
    render(<ObjectiveFitnessBlock data={EMPTY_DATA} />);

    // No crash; empty state shown and no chart rendered.
    expect(screen.getByText("データがありません")).toBeInTheDocument();
    expect(
      screen.queryByLabelText("実走VDOTとGarmin VO2maxの推移グラフ"),
    ).not.toBeInTheDocument();
  });
});
