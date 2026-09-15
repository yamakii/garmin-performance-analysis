import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import VerdictLine from "../components/VerdictLine";
import ConditionCard from "../pages/trends/ConditionCard";
import type { RecoveryRecommendation, RecoveryStatus } from "../types";
import { homeVerdict } from "../utils/verdict";
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

      const verdict = homeVerdict(status, null);
      const home = render(
        <VerdictLine
          verdict={verdict.verdict}
          verdictTone={verdict.tone}
          rest={verdict.rest}
        />,
      );
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
        expected,
      );
      home.unmount();

      const card = render(<ConditionCard data={status} />);
      expect(screen.getByText(expected)).toBeInTheDocument();
      card.unmount();
    }
  });
});
