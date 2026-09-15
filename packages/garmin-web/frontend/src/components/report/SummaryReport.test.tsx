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
  summary:
    "有酸素ベースの安定したランでした。平均心拍144bpmでZone2の中央に収まっています。",
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

/** Every `✓` / `!` marker rendered, in document order. */
function markers(): string[] {
  return Array.from(document.querySelectorAll('li > span[aria-hidden="true"]'))
    .map((node) => node.textContent ?? "")
    .filter((text) => text === "✓" || text === "!");
}

describe("SummaryReport", () => {
  it("test_summary_strengths_and_next_action", () => {
    render(
      <SummaryReport
        section={section({
          ...baseData,
          key_strengths: ["心拍の安定", "ケイデンス維持", "後半の粘り"],
          improvement_areas: ["序盤の突っ込み", "給水の遅れ"],
          next_action: "次回は最初の3kmを7:00/kmより遅く入りましょう。",
        })}
      />,
    );

    // Every strength and every improvement is listed, each behind its marker:
    // ink ✓ for what worked, warn ! for what did not.
    expect(markers()).toEqual(["✓", "✓", "✓", "!", "!"]);
    expect(screen.getByText("後半の粘り")).toBeInTheDocument();
    expect(screen.getByText("給水の遅れ")).toBeInTheDocument();
    // Five points is not a fold: the disclosure only appears past four per list.
    expect(
      screen.queryByText(/強み・改善点をすべて見る/),
    ).not.toBeInTheDocument();

    // The one thing to do next is the coach's note: bold, behind an ink rule,
    // and never folded away.
    const action = screen.getByText(
      "次回は最初の3kmを7:00/kmより遅く入りましょう。",
    );
    expect(action).toHaveClass("border-l-2");
    expect(action).toHaveClass("font-bold");
    expect(action.closest("details")).toBeNull();
  });

  it("test_summary_body_without_the_lead", () => {
    render(<SummaryReport section={section(baseData)} />);

    // The opening sentence is the page's conclusion line (rendered by the
    // header), so this section starts at what follows it.
    expect(
      screen.getByText(
        "平均心拍144bpmでZone2の中央に収まっています。",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("有酸素ベースの安定したランでした。"),
    ).not.toBeInTheDocument();
    // recommendations live inside their own collapsed <details>
    const recommendations = detailsFor("詳しい改善ポイント");
    expect(recommendations.hasAttribute("open")).toBe(false);
    expect(recommendations.textContent).toContain(
      "次回は HR 135-145 を維持してイージーランを実施しましょう。",
    );
  });

  it("test_long_lists_fold_past_four", () => {
    const strengths = [
      "心拍の安定（平均144bpm）",
      "ケイデンス維持",
      "接地時間の改善",
      "上下動比の安定",
      "終盤の再加速",
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

    // The disclosure names how many of each list it stands for.
    const all = detailsFor("強み・改善点をすべて見る(5 / 2)");
    expect(all.hasAttribute("open")).toBe(false);

    // The first four strengths read outside the fold; the fifth is inside it.
    for (const shown of strengths.slice(0, 4)) {
      expect(screen.getByText(shown).closest("details")).toBeNull();
    }
    expect(screen.getByText("終盤の再加速").closest("details")).toBe(all);
    // The short list is not folded at all.
    expect(screen.getByText("ウォームアップ不足").closest("details")).toBeNull();
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

    // Core content still renders as before.
    expect(screen.getByText("心拍の安定（平均144bpm）")).toBeInTheDocument();
    expect(screen.getByText("後半のペース低下")).toBeInTheDocument();

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

  it("renders the prescription verdict before the action it justifies", () => {
    const { unmount } = render(
      <SummaryReport section={section(prescriptionData)} />,
    );

    // The verdict reads as one line: marker + prescription title + the word
    // the rating stands for, with the first reason underneath. The marker is
    // `!` / `✓`, the same vocabulary as `Point` — never an emoji (#1188).
    const line = screen.getByText("処方「ロング 22km」・注意", {
      exact: false,
    });
    expect(line.textContent).toContain("!");
    expect(line.textContent).not.toMatch(/[✅🟡🔴]/u);
    expect(line.closest("details")).toBeNull();
    expect(
      screen.getByText("処方 22.0km に対し実施 17.0km（77%）で不足しています。"),
    ).toBeInTheDocument();

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
  });

  it("test_prescription_verdict_has_no_emoji", () => {
    // Every verdict mark maps to an ink ✓ (met) or a warn ! (not met), and no
    // verdict emoji reaches the DOM for any of the three ratings (#1188).
    for (const [verdict, marker, word] of [
      ["✅", "✓", "良好"],
      ["🟡", "!", "注意"],
      ["🔴", "!", "要改善"],
    ] as const) {
      const { unmount } = render(
        <SummaryReport
          section={section({
            ...baseData,
            prescription_verdict: {
              verdict,
              prescription_title: "ロング 22km",
              reasons: ["理由。"],
            },
          })}
        />,
      );

      const line = screen.getByText(`処方「ロング 22km」・${word}`, {
        exact: false,
      });
      expect(line.textContent).toContain(marker);
      expect(document.body.textContent).not.toMatch(/[✅🟡🔴]/u);
      unmount();
    }
  });

  it("leaves the previous-run deltas to the page header", () => {
    render(<SummaryReport section={section(prescriptionData)} />);

    // `vs_previous` is one mono line in the header (#1118); repeating it here
    // as chips would state the same comparison twice...
    expect(screen.queryByText(/前回比/)).not.toBeInTheDocument();
    // ...and it must not fall through to the raw key-value dump either.
    expect(screen.queryByText("vs previous")).not.toBeInTheDocument();
    expect(screen.queryByText("prescription verdict")).not.toBeInTheDocument();
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
    // The star rating belongs to the page headline, not to this section.
    expect(screen.queryByLabelText(/評価 4\.3/)).not.toBeInTheDocument();
  });
});
