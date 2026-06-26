import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import WeightEconomyChart from "../WeightEconomyChart";
import type {
  WeightEconomyCoupling,
  WeightEconomyModel,
} from "../../../types";

// echarts needs a real canvas; mock the modular wrapper out for jsdom.
vi.mock("../../../lib/echarts", () => ({
  echarts: {
    init: () => ({
      setOption: vi.fn(),
      resize: vi.fn(),
      dispose: vi.fn(),
    }),
  },
}));

const SERIES = [
  {
    activity_id: 1,
    run_date: "2025-10-06",
    weight_kg: 80.0,
    ef: 0.0176,
    weight_gap_days: 0,
  },
  {
    activity_id: 2,
    run_date: "2025-10-20",
    weight_kg: 78.8,
    ef: 0.0181,
    weight_gap_days: 1,
  },
];

function buildModel(overrides: Partial<WeightEconomyModel> = {}): WeightEconomyModel {
  return {
    n: 6,
    r_squared: 0.42,
    weight: { coef: -0.00044, p_value: 0.03, vif: 1.8 },
    days: { coef: 0.00001, p_value: 0.2, vif: 1.8 },
    fitness: null,
    delta_ef_per_5kg_loss: 0.0022,
    collinearity_flag: false,
    note: "association with effect-size estimate (no collinearity detected)",
    ...overrides,
  };
}

function buildData(
  model: WeightEconomyModel | null,
  series = SERIES,
): WeightEconomyCoupling {
  return {
    weeks: 52,
    n_matched: series.length,
    weight_spread_kg: 1.2,
    model,
    series,
    note: model?.note ?? "",
  };
}

describe("WeightEconomyChart", () => {
  it("renders the effect-size note when the model is present", () => {
    render(<WeightEconomyChart data={buildData(buildModel())} />);

    // delta_ef_per_5kg_loss 0.0022 surfaces as the effect-size note.
    expect(screen.getAllByText(/約5kg減/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/0\.0022/).length).toBeGreaterThan(0);
  });

  it("renders the collinearity (association, not causal) caveat", () => {
    const note = "association (causal coef not identified due to collinearity)";
    render(
      <WeightEconomyChart
        data={buildData(buildModel({ collinearity_flag: true, note }))}
      />,
    );

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(/因果係数ではありません/);
    expect(alert).toHaveTextContent(/collinearity/);
  });

  it("renders an empty state without crashing when model is null and series empty", () => {
    render(<WeightEconomyChart data={buildData(null, [])} />);

    expect(screen.getByText(/データがまだ不足/)).toBeInTheDocument();
    // No effect-size note and no chart when there is nothing to plot.
    expect(screen.queryByText(/約5kg減/)).not.toBeInTheDocument();
  });
});
