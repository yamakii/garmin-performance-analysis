import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import SummaryReport from "./SummaryReport";

// Real-schema mock (Spike #198: summary core keys at 100% occurrence).
const baseData = {
  metadata: {
    activity_id: "9000000101",
    date: "2025-10-09",
    analyst: "summary-section-analyst",
    version: "1.0",
    timestamp: "2025-10-09T12:00:00+09:00",
  },
  star_rating: "★★★★☆ 4.3/5.0",
  summary: "有酸素ベースの安定したランでした。",
  key_strengths: ["心拍の安定（平均144bpm）", "ケイデンス維持"],
  improvement_areas: ["後半のペース低下", "ウォームアップ不足"],
  recommendations: "次回は HR 135-145 を維持してイージーランを実施しましょう。",
};

function section(data: Record<string, unknown>) {
  return { data, parse_error: false, raw: null };
}

describe("SummaryReport", () => {
  it("renders strengths, improvements and recommendations", () => {
    const { container } = render(
      <SummaryReport section={section(baseData)} />,
    );

    // Large star rating parsed from the star_rating string
    expect(screen.getByLabelText("評価 4.3 / 5.0")).toBeInTheDocument();
    expect(
      screen.getByText("有酸素ベースの安定したランでした。"),
    ).toBeInTheDocument();

    expect(screen.getByText("強み")).toBeInTheDocument();
    expect(screen.getByText("心拍の安定（平均144bpm）")).toBeInTheDocument();
    expect(screen.getByText("ケイデンス維持")).toBeInTheDocument();

    expect(screen.getByText("改善ポイント")).toBeInTheDocument();
    expect(screen.getByText("後半のペース低下")).toBeInTheDocument();

    // recommendations now live inside a collapsed <details> ("詳しい改善ポイント")
    expect(screen.getByText("詳しい改善ポイント")).toBeInTheDocument();
    const details = container.querySelector("details");
    expect(details).not.toBeNull();
    expect(
      screen.getByText(
        "次回は HR 135-145 を維持してイージーランを実施しましょう。",
      ),
    ).toBeInTheDocument();
  });

  it("highlights next_action when present", () => {
    const { unmount } = render(
      <SummaryReport
        section={section({
          ...baseData,
          next_action: "次回はHR 135-145でイージーランを実施",
          integrated_score: 4.1,
        })}
      />,
    );

    // next_action renders as a single lead heading, not a key-value row
    const leads = screen.getAllByText("次回はHR 135-145でイージーランを実施");
    expect(leads).toHaveLength(1);
    expect(screen.queryByText("next_action")).not.toBeInTheDocument();
    // integrated_score renders as a badge
    expect(screen.getByText("統合スコア 4.1")).toBeInTheDocument();
    unmount();

    // Absent next_action -> lead heading is not rendered
    render(<SummaryReport section={section(baseData)} />);
    expect(
      screen.queryByText("次回はHR 135-145でイージーランを実施"),
    ).not.toBeInTheDocument();
  });

  it("collapses recommendations into details", () => {
    const { container } = render(
      <SummaryReport
        section={section({
          ...baseData,
          next_action: "次回はZone 2を維持",
        })}
      />,
    );

    // recommendations are rendered inside a <details> element
    const details = container.querySelector("details");
    expect(details).not.toBeNull();
    expect(
      details?.textContent?.includes(
        "次回は HR 135-145 を維持してイージーランを実施しましょう。",
      ),
    ).toBe(true);

    // next_action appears exactly once (as the lead heading)
    expect(screen.getAllByText("次回はZone 2を維持")).toHaveLength(1);
  });

  it("renders next_run_target as a prescription card, not a key dump", () => {
    render(
      <SummaryReport
        section={section({
          ...baseData,
          next_run_target: {
            recommended_type: "aerobic_base",
            target_hr_low: 140,
            target_hr_high: 150,
            reference_pace_low_formatted: "6:52",
            reference_pace_high_formatted: "7:02",
            success_criterion: "Zone 1+2比率85%以上を維持",
            summary_ja: "次回は平均心拍140-150bpmを目安に",
          },
        })}
      />,
    );

    expect(screen.getByText("ベース走")).toBeInTheDocument();
    expect(screen.getByText("140–150 bpm")).toBeInTheDocument();
    // No raw english keys leak into the DOM
    expect(screen.queryByText("recommended_type")).not.toBeInTheDocument();
  });

  it("unknown fields fall back to key-value", () => {
    render(
      <SummaryReport
        section={section({
          ...baseData,
          training_type_assessment: "テンポ走としての完成度は高い水準です。",
          some_future_field: 42,
        })}
      />,
    );

    // Unknown keys (schema evolution without version bump) -> fallback list
    expect(screen.getByText("training_type_assessment")).toBeInTheDocument();
    expect(
      screen.getByText("テンポ走としての完成度は高い水準です。"),
    ).toBeInTheDocument();
    expect(screen.getByText("some_future_field")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();

    // metadata boilerplate is consumed, never dumped as key-value
    expect(screen.queryByText("metadata")).not.toBeInTheDocument();
  });
});
