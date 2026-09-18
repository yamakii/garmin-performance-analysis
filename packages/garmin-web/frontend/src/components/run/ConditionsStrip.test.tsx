import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ConditionsStrip from "./ConditionsStrip";

describe("ConditionsStrip", () => {
  it("test_conditions_strip_reads_as_one_mono_line", () => {
    render(
      <ConditionsStrip
        conditions={{
          temp_c: 24.1,
          humidity_pct: 68,
          wind_mps: 2.1,
          terrain: "undulating",
          elevation_gain_m: 128.4,
        }}
      />,
    );

    expect(
      screen.getByText(
        "気温 24.1°C · 湿度 68% · 風 2.1m/s · 地形 起伏あり · 獲得標高 128m",
      ),
    ).toBeInTheDocument();
  });

  it("test_conditions_strip_omits_what_was_not_measured", () => {
    render(
      <ConditionsStrip
        conditions={{
          temp_c: 18.0,
          humidity_pct: null,
          wind_mps: null,
          terrain: null,
          elevation_gain_m: null,
        }}
      />,
    );

    // A missing reading is left out rather than printed as a dash.
    expect(screen.getByText("気温 18°C")).toBeInTheDocument();
  });

  it("test_conditions_strip_absent_without_a_reading", () => {
    // Nothing measured at all means no strip, not a row of dashes.
    const { container } = render(<ConditionsStrip conditions={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
