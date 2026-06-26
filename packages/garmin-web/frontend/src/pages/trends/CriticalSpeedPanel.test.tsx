import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import CriticalSpeedPanel from "./CriticalSpeedPanel";
import type { CriticalSpeedPoint } from "../../api/trends";

const DATA: CriticalSpeedPoint[] = [
  {
    quarter: "2026-Q2",
    cs_mps: 2.83,
    cs_pace_sec_per_km: 353.4,
    r_squared: 0.9998,
    n: 4,
    label: "threshold-anchored (no short/long max effort)",
  },
];

describe("CriticalSpeedPanel", () => {
  it("test_critical_speed_panel_shows_label_and_r2", () => {
    render(<CriticalSpeedPanel data={DATA} />);

    // threshold-anchored caveat is shown.
    expect(
      screen.getByText(/threshold-anchored/),
    ).toBeInTheDocument();
    // R^2 and CS pace are surfaced.
    expect(screen.getByText("0.9998")).toBeInTheDocument();
    expect(screen.getByText("5:53/km")).toBeInTheDocument();
    expect(screen.getByText("2026-Q2")).toBeInTheDocument();
    // D' must not be surfaced anywhere.
    expect(screen.queryByText(/D′/)).not.toBeInTheDocument();
    expect(screen.queryByText(/d_prime/i)).not.toBeInTheDocument();
  });

  it("test_critical_speed_panel_empty_state", () => {
    render(<CriticalSpeedPanel data={[]} />);

    // No crash; empty state shown and the caveat still rendered.
    expect(screen.getByText("データがありません")).toBeInTheDocument();
    expect(screen.getByText(/threshold-anchored/)).toBeInTheDocument();
  });
});
