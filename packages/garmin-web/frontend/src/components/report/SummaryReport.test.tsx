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

/** The <details> whose summary label is `title`. */
function detailsFor(title: string): HTMLDetailsElement {
  const details = screen.getByText(title).closest("details");
  expect(details).not.toBeNull();
  return details as HTMLDetailsElement;
}

describe("SummaryReport", () => {
  it("renders strengths, improvements and recommendations", () => {
    render(<SummaryReport section={section(baseData)} />);

    // Large star rating parsed from the star_rating string
    expect(screen.getByLabelText("評価 4.3 / 5.0")).toBeInTheDocument();
    expect(
      screen.getByText("有酸素ベースの安定したランでした。"),
    ).toBeInTheDocument();

    // Full lists live inside the "すべて見る" disclosure; the first item of
    // each also shows in the always-visible preview.
    const all = detailsFor("強み・改善点をすべて見る");
    expect(all.textContent).toContain("強み");
    expect(all.textContent).toContain("ケイデンス維持");
    expect(all.textContent).toContain("改善ポイント");
    expect(all.textContent).toContain("ウォームアップ不足");
    expect(screen.getAllByText("心拍の安定（平均144bpm）")).toHaveLength(2);
    expect(screen.getAllByText("後半のペース低下")).toHaveLength(2);

    // recommendations live inside their own collapsed <details>
    const recommendations = detailsFor("詳しい改善ポイント");
    expect(recommendations.textContent).toContain(
      "次回は HR 135-145 を維持してイージーランを実施しましょう。",
    );
  });

  it("test_summary_shows_lead_and_clamps_body", () => {
    const lead = "有酸素ベースの狙いどおりに走り切れた一本でした。";
    const body = [
      "平均心拍は144bpmでZone2の中央に収まり、終始安定した強度で走れています。",
      "ペースは6:26/kmで推移し、前半と後半の差は3秒に留まって崩れませんでした。",
      "接地時間269msは期待値をわずかに上回り、フォーム面でも良好な水準でした。",
      "気温18度・湿度62%という条件も走行には有利に働いたと考えられます。",
    ].join("");
    render(
      <SummaryReport section={section({ ...baseData, summary: lead + body })} />,
    );

    // The verdict sentence reads on its own, outside any fold.
    const leadNode = screen.getByText(lead);
    expect(leadNode.closest("details")).toBeNull();
    // The remaining prose is clamped with a reveal toggle, and the lead is
    // not repeated inside it.
    expect(
      screen.getByRole("button", { name: "続きを読む" }),
    ).toBeInTheDocument();
    expect(screen.getByText(body)).toBeInTheDocument();
    expect(screen.queryByText(lead + body)).not.toBeInTheDocument();
  });

  it("test_strengths_collapsed_with_count_chips", () => {
    const strengths = [
      "心拍の安定（平均144bpm）",
      "ケイデンス維持",
      "接地時間の改善",
      "上下動比の安定",
    ];
    render(
      <SummaryReport
        section={section({
          ...baseData,
          key_strengths: strengths,
          improvement_areas: ["後半のペース低下", "ウォームアップ不足"],
        })}
      />,
    );

    // Count chips carry the totals up front.
    expect(screen.getByText("✓ 強み 4")).toBeInTheDocument();
    expect(screen.getByText("! 改善 2")).toBeInTheDocument();

    // Only the first item of each list shows outside the disclosure.
    const all = detailsFor("強み・改善点をすべて見る");
    expect(all.hasAttribute("open")).toBe(false);
    for (const later of ["ケイデンス維持", "接地時間の改善", "上下動比の安定"]) {
      expect(screen.getByText(later).closest("details")).toBe(all);
    }
    expect(screen.getByText("ウォームアップ不足").closest("details")).toBe(all);

    // Expanding reveals every strength and improvement.
    expect(all.textContent).toContain("上下動比の安定");
    expect(all.textContent).toContain("ウォームアップ不足");
  });

  it("test_next_action_always_visible", () => {
    render(
      <SummaryReport
        section={section({
          ...baseData,
          next_action: "次回はHR 135-145でイージーランを実施",
        })}
      />,
    );

    // The one thing to do next is never folded away.
    const action = screen.getByText("次回はHR 135-145でイージーランを実施");
    expect(action.closest("details")).toBeNull();
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

  it("test_summary_report_integrated_score_precision", () => {
    // Raw float from the backend must render with clean precision (#493).
    render(
      <SummaryReport
        section={section({
          ...baseData,
          integrated_score: 4.2000000000001,
        })}
      />,
    );

    expect(screen.getByText("統合スコア 4.2")).toBeInTheDocument();
    expect(screen.queryByText(/4\.20000/)).not.toBeInTheDocument();
  });

  it("collapses recommendations into details", () => {
    render(
      <SummaryReport
        section={section({
          ...baseData,
          next_action: "次回はZone 2を維持",
        })}
      />,
    );

    // recommendations are rendered inside their own <details>
    const details = detailsFor("詳しい改善ポイント");
    expect(details.hasAttribute("open")).toBe(false);
    expect(
      details.textContent?.includes(
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

  it("test_summary_report_omits_plan_achievement", () => {
    // Summary without plan_achievement (Issue #782: plan-vs-actual UI removed).
    render(<SummaryReport section={section(baseData)} />);

    // Core sections still render as before.
    expect(
      screen.getByText("有酸素ベースの安定したランでした。"),
    ).toBeInTheDocument();
    expect(screen.getByText("強み")).toBeInTheDocument();
    expect(screen.getByText("改善ポイント")).toBeInTheDocument();

    // No dedicated plan-achievement card is rendered.
    expect(screen.queryByText("プラン達成度")).not.toBeInTheDocument();
    expect(screen.queryByText("plan_achievement")).not.toBeInTheDocument();
  });

  // --- Prescription vs actual layer (Issue #984) ---

  const prescriptionData = {
    ...baseData,
    next_action: "次回は9/20のカットバック週として14kmに留めましょう。",
    prescription_verdict: {
      verdict: "🟡",
      prescription_title: "ロング 22km",
      reasons: ["処方 22.0km に対し実施 17.0km（77%）で不足しています。"],
    },
    vs_previous: {
      pace_s_per_km: { current: 430, previous: 440, delta: -10 },
      avg_hr: { current: 142, previous: 145, delta: -3 },
      gct_ms: { current: 262, previous: 258, delta: 4 },
      cadence_spm: { current: 172, previous: 174, delta: -2 },
      previous_activity_id: 987,
      previous_date: "2026-09-06",
      days_ago: 7,
    },
  };

  it("renders prescription verdict line and delta chips", () => {
    const { unmount } = render(
      <SummaryReport section={section(prescriptionData)} />,
    );

    // The verdict reads as one line: mark + prescription title + the word the
    // mark stands for, with the first reason underneath.
    const line = screen.getByText("処方「ロング 22km」・注意", {
      exact: false,
    });
    expect(line.textContent).toContain("🟡");
    expect(line.closest("details")).toBeNull();
    expect(
      screen.getByText("処方 22.0km に対し実施 17.0km（77%）で不足しています。"),
    ).toBeInTheDocument();

    // Four signed delta chips against the last same-type run, with the gap.
    expect(screen.getByText("前回比（7日前）")).toBeInTheDocument();
    for (const [label, value] of [
      ["ペース", "-10 秒/km"],
      ["HR", "-3 bpm"],
      ["GCT", "+4 ms"],
      ["ケイデンス", "-2 spm"],
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
      expect(screen.getByText(value)).toBeInTheDocument();
    }

    // The verdict is read before the action it justifies.
    const action = screen.getByText(
      "次回は9/20のカットバック週として14kmに留めましょう。",
    );
    expect(
      line.compareDocumentPosition(action) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    unmount();

    // Legacy summaries (no prescription layer) render exactly as before.
    render(<SummaryReport section={section(baseData)} />);
    expect(screen.queryByText(/処方「/)).not.toBeInTheDocument();
    expect(screen.queryByText(/前回比/)).not.toBeInTheDocument();
  });

  it("FallbackFields does not duplicate the new keys", () => {
    render(<SummaryReport section={section(prescriptionData)} />);

    // Both keys have dedicated UI, so the key-value fallback must not repeat
    // them under their own labels (nor as humanized raw keys).
    expect(screen.queryByText("処方との比較")).not.toBeInTheDocument();
    expect(screen.queryByText("prescription verdict")).not.toBeInTheDocument();
    expect(screen.queryByText("vs previous")).not.toBeInTheDocument();
    // The verdict title appears once — in the dedicated line only.
    expect(screen.getAllByText(/ロング 22km/)).toHaveLength(1);
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

    // Unknown keys (schema evolution without version bump) -> fallback list,
    // humanized rather than shown as raw snake_case (#915).
    expect(screen.getByText("training type assessment")).toBeInTheDocument();
    expect(
      screen.getByText("テンポ走としての完成度は高い水準です。"),
    ).toBeInTheDocument();
    expect(screen.getByText("some future field")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();

    // metadata boilerplate is consumed, never dumped as key-value
    expect(screen.queryByText("metadata")).not.toBeInTheDocument();
  });
});
