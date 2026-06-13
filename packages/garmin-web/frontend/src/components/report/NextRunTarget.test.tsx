import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import NextRunTarget from "./NextRunTarget";

// Real-schema mock (Issue #224: structured next_run_target object).
const fullData = {
  recommended_type: "aerobic_base",
  target_hr_low: 140,
  target_hr_high: 150,
  reference_pace_low_formatted: "6:52",
  reference_pace_high_formatted: "7:02",
  success_criterion: "Zone 1+2比率85%以上を維持し、平均心拍150bpm以下に収める",
  adjustment_tip: "心拍が150bpmを超えそうな場合はペースを5秒/km落とす",
  summary_ja:
    "次回は平均心拍140-150bpm（Zone 2中心）を目安に、参考ペース6:52-7:02/kmで",
};

describe("NextRunTarget", () => {
  it("renders prescription fields with labels", () => {
    render(<NextRunTarget data={fullData} />);

    // Lead summary
    expect(screen.getByText(fullData.summary_ja)).toBeInTheDocument();
    // Japanese training-type badge (not the raw english key)
    expect(screen.getByText("ベース走")).toBeInTheDocument();
    // Target HR / reference pace chips
    expect(screen.getByText("目標HR")).toBeInTheDocument();
    expect(screen.getByText("140–150 bpm")).toBeInTheDocument();
    expect(screen.getByText("参考ペース")).toBeInTheDocument();
    expect(screen.getByText("6:52–7:02 /km")).toBeInTheDocument();
    // Labeled success criterion / adjustment tip
    expect(screen.getByText("成功条件")).toBeInTheDocument();
    expect(screen.getByText(fullData.success_criterion)).toBeInTheDocument();
    expect(screen.getByText("調整ヒント")).toBeInTheDocument();
    expect(screen.getByText(fullData.adjustment_tip)).toBeInTheDocument();

    // Raw english keys must never reach the DOM
    expect(screen.queryByText("recommended_type")).not.toBeInTheDocument();
    expect(screen.queryByText("target_hr_low")).not.toBeInTheDocument();
    expect(screen.queryByText("success_criterion")).not.toBeInTheDocument();
  });

  it("hides missing fields", () => {
    // Only a type + a single HR bound; pace and tips absent.
    render(
      <NextRunTarget
        data={{
          recommended_type: "tempo",
          target_hr_low: 160,
        }}
      />,
    );

    // Known type label still resolves
    expect(screen.getByText("テンポ走")).toBeInTheDocument();
    // Single-bound HR renders as a single value
    expect(screen.getByText("目標HR")).toBeInTheDocument();
    expect(screen.getByText("160 bpm")).toBeInTheDocument();

    // Absent fields are not rendered (no crash)
    expect(screen.queryByText("参考ペース")).not.toBeInTheDocument();
    expect(screen.queryByText("成功条件")).not.toBeInTheDocument();
    expect(screen.queryByText("調整ヒント")).not.toBeInTheDocument();
  });

  it("shows unknown training types verbatim without crashing", () => {
    render(<NextRunTarget data={{ recommended_type: "fartlek" }} />);
    expect(screen.getByText("fartlek")).toBeInTheDocument();
  });
});
