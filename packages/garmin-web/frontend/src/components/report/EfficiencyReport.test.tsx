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
  speed_actual_mps: null,
  speed_expected_mps: null,
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

  it("test_power_not_in_star_row", () => {
    const withPower = {
      ...formEvaluations,
      power_avg_w: 234.7,
      power_wkg: 2.95,
      power_efficiency_rating: "同等",
      speed_actual_mps: 3.15,
      speed_expected_mps: 3.1,
    };
    render(<EfficiencyReport section={section} formEvaluations={withPower} />);

    // GCT/VO/VR remain three form-metric tiles; power is no longer among them.
    const tiles = screen.getAllByText(
      /^(接地時間|上下動|上下動比|パワー)$/,
    );
    expect(tiles).toHaveLength(3);
    expect(screen.queryByText("パワー")).not.toBeInTheDocument();
  });

  it("test_power_baseline_descriptor_rendered", () => {
    const withPower = {
      ...formEvaluations,
      power_avg_w: 234.7,
      power_wkg: 2.95,
      power_efficiency_rating: "同等",
      speed_actual_mps: 3.15,
      speed_expected_mps: 3.1,
    };
    render(<EfficiencyReport section={section} formEvaluations={withPower} />);

    // Descriptor subsection: label headline + power + actual-vs-expected speed.
    expect(
      screen.getByText("パワー効率（自己ベースライン比）"),
    ).toBeInTheDocument();
    expect(screen.getByText("同等")).toBeInTheDocument();
    expect(screen.getByText(/235\s*W\s*\/\s*2\.95\s*W\/kg/)).toBeInTheDocument();
    expect(
      screen.getByText(/実測\s*3\.15\s*m\/s.*期待\s*3\.10\s*m\/s/),
    ).toBeInTheDocument();
  });

  it("test_power_descriptor_hidden_when_null", () => {
    render(
      <EfficiencyReport section={section} formEvaluations={formEvaluations} />,
    );

    expect(
      screen.queryByText("パワー効率（自己ベースライン比）"),
    ).not.toBeInTheDocument();
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

  it("test_efficiency_prose_behind_disclosure", () => {
    render(
      <EfficiencyReport
        section={{
          data: {
            efficiency: "フォーム効率は良好。(★★★★☆ 4.0/5.0)",
            evaluation:
              "心拍効率は良好です。平均144bpmでZone2中心の負荷に収まりました。",
            form_trend: "直近5本と比べて接地時間が2%短縮しています。",
          },
          parse_error: false,
          raw: null,
        }}
        formEvaluations={formEvaluations}
      />,
    );

    // The three prose fields sit inside a collapsed disclosure...
    const details = screen.getByText("分析の詳細").closest("details");
    expect(details).not.toBeNull();
    expect(details?.hasAttribute("open")).toBe(false);
    expect(details?.textContent).toContain("フォームトレンド");
    expect(details?.textContent).toContain(
      "直近5本と比べて接地時間が2%短縮しています。",
    );

    // ...while the evaluation's first sentence leads outside the fold.
    const lead = screen.getByText("心拍効率は良好です。");
    expect(lead.closest("details")).toBeNull();

    // Tiles stay in the open: they are the headline of this card.
    expect(screen.getByText("接地時間").closest("details")).toBeNull();
    expect(screen.getByText("269").closest("details")).toBeNull();
  });

  it("test_efficiency_star_badge_from_suffix", () => {
    render(
      <EfficiencyReport
        section={{
          data: { efficiency: "フォーム効率は良好。(★★★★☆ 4.0/5.0)" },
          parse_error: false,
          raw: null,
        }}
        formEvaluations={null}
      />,
    );

    // The rating is lifted out of the prose into a heading badge...
    const badge = screen.getByText("★ 4.0");
    expect(badge).toBeInTheDocument();
    expect(screen.getByText("効率分析").parentElement).toContainElement(badge);

    // ...and no longer trails the sentence.
    expect(screen.getByText("フォーム効率は良好。")).toBeInTheDocument();
    expect(screen.queryByText(/4\.0\/5\.0/)).not.toBeInTheDocument();
  });
});
