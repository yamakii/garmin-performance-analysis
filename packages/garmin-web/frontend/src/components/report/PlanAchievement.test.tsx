import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import PlanAchievement from "./PlanAchievement";

// Real-schema mock (Issue #598: structured plan_achievement object).
const fullData = {
  workout_type: "easy",
  description_ja: "イージーラン",
  targets: { hr: "121-148bpm", pace: "6:55-8:14/km" },
  actuals: { hr: "143bpm", pace: "8:23/km" },
  hr_achieved: true,
  pace_achieved: false,
  evaluation: "心拍数はプラン目標範囲内に収まったが、ペースは目標より遅かった。",
};

describe("PlanAchievement", () => {
  it("test_renders_targets_vs_actuals", () => {
    render(<PlanAchievement data={fullData} />);

    // Japanese badge (not the raw english workout_type)
    expect(screen.getByText("イージーラン")).toBeInTheDocument();
    // Target and actual HR both shown
    expect(screen.getByText("目標 121-148bpm")).toBeInTheDocument();
    expect(screen.getByText("実績 143bpm")).toBeInTheDocument();
    // Target and actual pace both shown
    expect(screen.getByText("目標 6:55-8:14/km")).toBeInTheDocument();
    expect(screen.getByText("実績 8:23/km")).toBeInTheDocument();

    // Raw english keys must never reach the DOM
    expect(screen.queryByText("workout_type")).not.toBeInTheDocument();
    expect(screen.queryByText("targets")).not.toBeInTheDocument();
    expect(screen.queryByText("actuals")).not.toBeInTheDocument();
    expect(screen.queryByText("hr_achieved")).not.toBeInTheDocument();
  });

  it("test_renders_achievement_marks", () => {
    render(<PlanAchievement data={fullData} />);

    // hr_achieved=true → ✓, pace_achieved=false → ✗
    expect(screen.getByText("✓")).toBeInTheDocument();
    expect(screen.getByText("✗")).toBeInTheDocument();
  });

  it("test_renders_evaluation_text", () => {
    render(<PlanAchievement data={fullData} />);
    expect(screen.getByText(fullData.evaluation)).toBeInTheDocument();
  });

  it("test_returns_null_for_non_object", () => {
    const { container } = render(
      <PlanAchievement data={"イージーラン" as unknown as Record<string, unknown>} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
