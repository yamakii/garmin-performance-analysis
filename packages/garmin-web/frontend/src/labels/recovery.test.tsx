import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ConditionCard from "../pages/trends/ConditionCard";
import TodayHero from "../pages/dashboard/TodayHero";
import type { RecoveryRecommendation, RecoveryStatus } from "../types";
import { RECOMMENDATION_LABELS } from "./recovery";

function makeStatus(recommendation: RecoveryRecommendation): RecoveryStatus {
  return {
    date: "2026-08-09",
    recommendation,
    score: 72,
    reasons: ["HRVは基準内、睡眠スコアも良好です"],
    training_readiness: 72,
    body_battery_high: 88,
    sleep_score: 74,
  };
}

describe("recovery labels", () => {
  /**
   * The two surfaces that show a recommendation used to disagree about its
   * name ("イージー推奨" in the home hero, "イージー" on the condition page),
   * so the same morning read differently depending on where you looked (#915).
   */
  it("test_recovery_labels_single_source", () => {
    const recommendations: RecoveryRecommendation[] = [
      "quality",
      "moderate",
      "easy",
      "rest",
      "unknown",
    ];

    for (const recommendation of recommendations) {
      const status = makeStatus(recommendation);
      const expected = RECOMMENDATION_LABELS[recommendation];

      const hero = render(<TodayHero status={status} baseline={null} />);
      expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(
        expected,
      );
      hero.unmount();

      const card = render(<ConditionCard data={status} />);
      expect(screen.getByText(expected)).toBeInTheDocument();
      card.unmount();
    }
  });
});
