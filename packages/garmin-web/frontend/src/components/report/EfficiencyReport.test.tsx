import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import EfficiencyReport from "./EfficiencyReport";

const section = {
  data: { efficiency: "フォーム効率は良好。(★★★★★ 5.0/5.0)" },
  parse_error: false,
  raw: null,
};

// Raw DB floats carry ~13 decimal digits (#226). Columns mirror the
// form_evaluations table schema (#292).
const formEvaluations = {
  gct_ms_actual: 269.2083435058594,
  gct_ms_expected: 273.0294189453125,
  gct_delta_pct: -1.3995118141174316,
  gct_star_rating: "★★★★★",
  vo_cm_actual: 6.93916654586792,
  vo_cm_expected: 6.979050159454346,
  vo_delta_cm: -0.03988350182771683,
  vo_star_rating: "★★★★★",
  vr_pct_actual: 10.066666603088379,
  vr_pct_expected: 10.049034118652344,
  vr_delta_pct: 0.175467386841774,
  vr_star_rating: "★★★★★",
  power_avg_w: null,
  power_wkg: null,
  power_efficiency_rating: null,
};

describe("EfficiencyReport", () => {
  it("test_tiles_use_form_evaluations_star_rating", () => {
    render(
      <EfficiencyReport section={section} formEvaluations={formEvaluations} />,
    );

    // GCT tile renders the actual value rounded to integer ms.
    expect(screen.getByText("269")).toBeInTheDocument();
    // Star rating comes from form_evaluations and matches the prose.
    expect(screen.getAllByText("★★★★★").length).toBeGreaterThan(0);

    // Raw long decimals must not appear.
    expect(screen.queryByText(/269\.20834/)).not.toBeInTheDocument();
  });

  it("test_power_tile_shown_when_present", () => {
    const withPower = {
      ...formEvaluations,
      power_avg_w: 234.7,
      power_wkg: 2.95,
      power_efficiency_rating: "★★★★☆",
    };
    render(<EfficiencyReport section={section} formEvaluations={withPower} />);

    expect(screen.getByText("パワー")).toBeInTheDocument();
    expect(screen.getByText("235")).toBeInTheDocument();
    expect(screen.getByText("2.95 W/kg")).toBeInTheDocument();
    expect(screen.getByText("★★★★☆")).toBeInTheDocument();
  });

  it("test_power_tile_hidden_when_null", () => {
    render(
      <EfficiencyReport section={section} formEvaluations={formEvaluations} />,
    );

    expect(screen.queryByText("パワー")).not.toBeInTheDocument();
    expect(screen.queryByText(/W\/kg/)).not.toBeInTheDocument();
  });

  it("test_tiles_hidden_when_no_form_evaluations", () => {
    render(<EfficiencyReport section={section} formEvaluations={null} />);

    // No metric tiles when form_evaluations is absent.
    expect(screen.queryByText("接地時間")).not.toBeInTheDocument();
    expect(screen.queryByText("パワー")).not.toBeInTheDocument();
    // Prose still renders.
    expect(screen.getByText("フォーム効率")).toBeInTheDocument();
    expect(screen.getByText(/フォーム効率は良好。/)).toBeInTheDocument();
  });
});
