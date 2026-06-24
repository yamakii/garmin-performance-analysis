import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ConditionCard from "./ConditionCard";
import type { RecoveryStatus } from "../../types";

const QUALITY: RecoveryStatus = {
  date: "2025-10-07",
  recommendation: "quality",
  score: 80,
  reasons: ["Training Readiness 80 が高くHRVも正常→質練OK"],
  training_readiness: 81,
  body_battery_high: 92,
  sleep_score: 78,
};

const UNKNOWN: RecoveryStatus = {
  date: null,
  recommendation: "unknown",
  score: null,
  reasons: ["データ無し・感覚優先"],
  training_readiness: null,
  body_battery_high: null,
  sleep_score: null,
};

describe("ConditionCard", () => {
  it("renders a green badge for a quality recommendation", () => {
    render(<ConditionCard data={QUALITY} />);

    const badge = screen.getByText("質練OK");
    expect(badge).toBeInTheDocument();
    // Quality recommendation -> emerald (green) badge family.
    expect(badge.className).toContain("emerald");
    // Rationale + the three condition markers are shown.
    expect(screen.getByText(QUALITY.reasons[0])).toBeInTheDocument();
    expect(screen.getByText("準備度")).toBeInTheDocument();
    expect(screen.getByText("81")).toBeInTheDocument();
  });

  it("falls back to データ無し when the recommendation is unknown", () => {
    render(<ConditionCard data={UNKNOWN} />);

    expect(screen.getByText("データ無し")).toBeInTheDocument();
    expect(
      screen.getByText(/データ無し・感覚優先で判断してください/),
    ).toBeInTheDocument();
    // The marker grid is hidden in the unknown fallback.
    expect(screen.queryByText("準備度")).not.toBeInTheDocument();
  });
});
