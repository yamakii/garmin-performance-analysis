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
    render(<SummaryReport section={section(baseData)} />);

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

    expect(screen.getByText("推奨事項")).toBeInTheDocument();
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

    // next_action renders as an action callout, not a key-value row
    expect(screen.getByText("次のアクション")).toBeInTheDocument();
    expect(
      screen.getByText("次回はHR 135-145でイージーランを実施"),
    ).toBeInTheDocument();
    expect(screen.queryByText("next_action")).not.toBeInTheDocument();
    // integrated_score renders as a badge
    expect(screen.getByText("統合スコア 4.1")).toBeInTheDocument();
    unmount();

    // Absent next_action -> callout is not rendered
    render(<SummaryReport section={section(baseData)} />);
    expect(screen.queryByText("次のアクション")).not.toBeInTheDocument();
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
