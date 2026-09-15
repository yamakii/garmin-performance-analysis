import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import VerdictLine from "../components/VerdictLine";
import type { RecoveryRecommendation, RecoveryStatus } from "../types";
import { conditionVerdict, homeVerdict } from "../utils/verdict";
import { RECOMMENDATION_LABELS, RECOVERY_STATE_LABELS } from "./recovery";

function makeStatus(recommendation: RecoveryRecommendation): RecoveryStatus {
  return {
    date: "2026-08-09",
    recommendation,
    score: 72,
    reasons: ["HRVは基準内、睡眠スコアも良好です"],
    training_readiness: 72,
    body_battery_high: 88,
    sleep_score: 74,
    sleep_seconds: 25920,
  };
}

describe("recovery labels", () => {
  /**
   * The two surfaces that show a recommendation used to disagree about its
   * name ("イージー推奨" in the home hero, "イージー" on the condition page),
   * so the same morning read differently depending on where you looked (#915).
   *
   * They now say different *sentences* on purpose — home says what to do,
   * `/condition` says how recovered the body is — but both sentences come from
   * the label maps here, so neither page can invent a third wording (#1120).
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

      const home = homeVerdict(status, null);
      expect(home.verdict).toBe(`${RECOMMENDATION_LABELS[recommendation]}。`);
      const rendered = render(
        <VerdictLine
          verdict={home.verdict}
          verdictTone={home.tone}
          rest={home.rest}
        />,
      );
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
        RECOMMENDATION_LABELS[recommendation],
      );
      rendered.unmount();

      const condition = conditionVerdict(status, null, null);
      expect(condition.verdict).toBe(
        `${RECOVERY_STATE_LABELS[recommendation]}。`,
      );
      // Same value, same tone, whichever sentence states it.
      expect(condition.tone).toBe(home.tone);
    }
  });
});
