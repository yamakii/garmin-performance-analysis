import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import EfficiencyReport from "./EfficiencyReport";

const section = {
  data: { efficiency: "フォーム効率は良好。" },
  parse_error: false,
  raw: null,
};

// Raw DB floats carry ~13 decimal digits (#226).
const formEfficiency = {
  gct_average: 265.6500015258789,
  gct_rating: "良好",
  vo_average: 7.145000076293946,
  vo_rating: "やや大",
  vr_average: 9.696249961853027,
  vr_rating: "標準",
};

describe("EfficiencyReport", () => {
  it("rounds stat values", () => {
    render(<EfficiencyReport section={section} formEfficiency={formEfficiency} />);

    // GCT → integer ms, VO / VR → 1 decimal
    expect(screen.getByText("266")).toBeInTheDocument();
    expect(screen.getByText("7.1")).toBeInTheDocument();
    expect(screen.getByText("9.7")).toBeInTheDocument();

    // Raw long decimals must not appear
    expect(screen.queryByText(/265\.65000/)).not.toBeInTheDocument();
    expect(screen.queryByText(/7\.145000/)).not.toBeInTheDocument();
  });
});
