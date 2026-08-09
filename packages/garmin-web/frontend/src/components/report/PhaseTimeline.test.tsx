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

/** Marked-up prose as the agents write it: measurements, then the verdict. */
const markedData = {
  ...baseData,
  warmup_evaluation:
    "**実際**: 心拍130bpm台で1kmを走りました。\n**評価**: 立ち上がりは適切でした。(★★★★☆ 4.0/5.0)",
  run_evaluation:
    "**実際**: 6:26/kmで3kmを維持しました。\n**評価**: 目標どおりの巡航です。(★★★☆☆ 3.5/5.0)",
  cooldown_evaluation:
    "**実際**: 最後の0.6kmで心拍が落ちました。\n**評価**: 締めくくりは理想的です。(★★★★★ 4.8/5.0)",
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

  it("test_phase_star_badges_on_nodes", () => {
    render(<PhaseTimeline section={section(markedData)} />);

    // Every node carries its score as a badge next to the phase label.
    expect(screen.getByText("★ 4.0")).toBeInTheDocument();
    expect(screen.getByText("★ 3.5")).toBeInTheDocument();
    expect(screen.getByText("★ 4.8")).toBeInTheDocument();
    expect(screen.getByText("ウォームアップ").parentElement).toContainElement(
      screen.getByText("★ 4.0"),
    );

    // The verdict is the default line; the measurements are a muted footnote.
    expect(screen.getByText("立ち上がりは適切でした。")).toBeInTheDocument();
    expect(
      screen.getByText("実際: 心拍130bpm台で1kmを走りました。"),
    ).toBeInTheDocument();

    // The rating no longer trails the prose, and the markers are consumed.
    expect(screen.queryByText(/4\.0\/5\.0/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\*\*評価\*\*/)).not.toBeInTheDocument();
  });

  it("test_phase_fallback_without_markers", () => {
    render(<PhaseTimeline section={section(baseData)} />);

    // Prose without 実際 / 評価 markers renders verbatim (no regression).
    expect(
      screen.getByText("心拍 130bpm 台で適切なウォームアップでした。"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("最後の 0.6km で心拍を落とせています。"),
    ).toBeInTheDocument();
    // Nothing is invented: no badge and no 実際 footnote for this payload.
    expect(screen.queryByText(/^★ /)).not.toBeInTheDocument();
    expect(screen.queryByText(/^実際: /)).not.toBeInTheDocument();
  });
});
