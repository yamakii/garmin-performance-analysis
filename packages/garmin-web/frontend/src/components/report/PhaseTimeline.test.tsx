import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import PhaseTimeline from "./PhaseTimeline";

const baseData = {
  metadata: {
    activity_id: "9000000101",
    date: "2025-10-09",
    analyst: "phase-section-analyst",
    version: "1.0",
    timestamp: "2025-10-09T12:00:00+09:00",
  },
  warmup_evaluation: "心拍 130bpm 台で適切なウォームアップでした。",
  run_evaluation: "メインランは 6:26/km で安定していました。",
  cooldown_evaluation: "最後の 0.6km で心拍を落とせています。",
  evaluation_criteria: "aerobic_base 基準（HR Zone 2 中心）で評価しています。",
};

function section(data: Record<string, unknown>) {
  return { data, parse_error: false, raw: null };
}

describe("PhaseTimeline", () => {
  it("renders warmup, run and cooldown phases with criteria", () => {
    render(<PhaseTimeline section={section(baseData)} />);

    expect(screen.getByText("ウォームアップ")).toBeInTheDocument();
    expect(screen.getByText("メインラン")).toBeInTheDocument();
    expect(screen.getByText("クールダウン")).toBeInTheDocument();
    expect(screen.getByText("評価基準")).toBeInTheDocument();
    expect(
      screen.getByText("メインランは 6:26/km で安定していました。"),
    ).toBeInTheDocument();
    // recovery is interval-only and absent from this payload
    expect(screen.queryByText("リカバリー")).not.toBeInTheDocument();
  });

  it("renders recovery phase only when present", () => {
    render(
      <PhaseTimeline
        section={section({
          ...baseData,
          recovery_evaluation: "レスト区間で心拍が十分に回復しています。",
        })}
      />,
    );

    expect(screen.getByText("リカバリー")).toBeInTheDocument();
    expect(
      screen.getByText("レスト区間で心拍が十分に回復しています。"),
    ).toBeInTheDocument();
  });
});
