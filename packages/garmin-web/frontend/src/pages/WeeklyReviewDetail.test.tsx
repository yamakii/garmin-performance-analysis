import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import WeeklyReviewDetail from "./WeeklyReviewDetail";
import type { WeeklyReviewData } from "../types";

/** Full review touching every meaning group + 総評. */
const fullReview: WeeklyReviewData = {
  this_week: { volume_km: 35.5, run_count: 4 },
  weight_tracking: { recent_median_kg: 79.6, bmi: 24.1 },
  recovery: "回復は良好です。",
  verdict: [
    { date: "2026-06-16", session: "Easy Run", rating: "◎", comment: "good" },
  ],
  goal_alignment: "目標に整合しています。",
  periodization: { a_race: "フルマラソン", expected_phase: "Base" },
  weekly_ramp: "緩やかに増加しています。",
  recommendations: ["月曜は休養に充てる"],
  garmin_next_week: [{ date: "2026-06-22", title: "Easy Run", type: "easy" }],
  continuity_note: "前回からの継続性は良好です。",
  overall: "総じて順調です。",
};

function renderDetail(reviewData: WeeklyReviewData) {
  const versions = [
    {
      review_id: 1,
      user_id: "default",
      week_start_date: "2026-06-15",
      week_end_date: "2026-06-21",
      review_date: "2026-06-22",
      review_data: reviewData,
      created_at: null,
      agent_name: "weekly-review",
      agent_version: "1.0",
    },
  ];
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify(versions), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );
  return render(
    <MemoryRouter initialEntries={["/weekly-reviews/2026-06-15"]}>
      <Routes>
        <Route
          path="/weekly-reviews/:weekStart"
          element={<WeeklyReviewDetail />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("WeeklyReviewDetail", () => {
  it("WeeklyReviewDetail still shows 週次レビュー heading and 一覧へ link", async () => {
    renderDetail(fullReview);

    expect(
      await screen.findByRole("heading", { level: 1, name: "週次レビュー" }),
    ).toBeInTheDocument();
    const backLink = screen.getByRole("link", { name: "← 一覧へ" });
    expect(backLink).toHaveAttribute("href", "/weekly-reviews");
  });

  it("test_renders_garmin_next_week_table", async () => {
    renderDetail({
      garmin_next_week: [
        { date: "2026-06-22", title: "Easy Run", type: "easy" },
        { date: "2026-06-24", title: "Interval", type: "anaerobic" },
      ],
    });

    expect(
      await screen.findByRole("heading", {
        level: 2,
        name: "来週のGarminワークアウト",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("2026-06-22")).toBeInTheDocument();
    expect(screen.getByText("Easy Run")).toBeInTheDocument();
    expect(screen.getByText("easy")).toBeInTheDocument();
    expect(screen.getByText("2026-06-24")).toBeInTheDocument();
    expect(screen.getByText("Interval")).toBeInTheDocument();
    expect(screen.getByText("anaerobic")).toBeInTheDocument();
  });

  it("test_renders_intensity_distribution", async () => {
    renderDetail({
      this_week: {
        volume_km: 35.5,
        intensity_distribution: { easy_z1_z2: 4, long_run: 1 },
      },
    });

    expect(
      await screen.findByRole("heading", { level: 2, name: "実績サマリー" }),
    ).toBeInTheDocument();
    expect(screen.getByText("easy_z1_z2: 4")).toBeInTheDocument();
    expect(screen.getByText("long_run: 1")).toBeInTheDocument();
  });

  it("test_renders_weight_tracking_section", async () => {
    renderDetail({
      weight_tracking: {
        recent_median_kg: 79.6,
        bmi: 24.1,
        trend: "微減",
      },
    });

    expect(
      await screen.findByRole("heading", {
        level: 2,
        name: "体重トラッキング",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText(/79\.6/)).toBeInTheDocument();
    expect(screen.getByText(/24\.1/)).toBeInTheDocument();
    expect(screen.getByText("微減")).toBeInTheDocument();
  });

  it("test_renders_continuity_note", async () => {
    renderDetail({
      continuity_note: "前回からの継続性は良好です。",
    });

    expect(
      await screen.findByRole("heading", {
        level: 2,
        name: "前回からの継続性",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("前回からの継続性は良好です。"),
    ).toBeInTheDocument();
  });

  it("test_omits_absent_optional_sections", async () => {
    renderDetail({
      this_week: { volume_km: 35.5, run_count: 4 },
      overall: "順調です。",
    });

    // 実績サマリー is always present; the optional sections must not render.
    expect(
      await screen.findByRole("heading", { level: 2, name: "実績サマリー" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("来週のGarminワークアウト"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("体重トラッキング")).not.toBeInTheDocument();
    expect(screen.queryByText("リカバリー")).not.toBeInTheDocument();
    expect(screen.queryByText("前回からの継続性")).not.toBeInTheDocument();
    expect(screen.queryByText("週次ランプ")).not.toBeInTheDocument();
  });

  it("renders three group headings 今週の実績 / 評価 / 次アクション", async () => {
    renderDetail(fullReview);

    expect(
      await screen.findByRole("region", { name: "今週の実績" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "評価" })).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "次アクション" }),
    ).toBeInTheDocument();
  });

  it("places 実績サマリー under 今週の実績 group", async () => {
    renderDetail(fullReview);

    const group = await screen.findByRole("region", { name: "今週の実績" });
    expect(within(group).getByText("実績サマリー")).toBeInTheDocument();
  });

  it("places 対象週プラン評価 under 評価 group", async () => {
    renderDetail(fullReview);

    const group = await screen.findByRole("region", { name: "評価" });
    expect(within(group).getByText("対象週プラン評価")).toBeInTheDocument();
  });

  it("still hides 目標逆算フェーズ when periodization absent", async () => {
    renderDetail({ this_week: { volume_km: 30 } });

    expect(
      await screen.findByRole("heading", { level: 2, name: "実績サマリー" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("目標逆算フェーズ")).not.toBeInTheDocument();
  });

  it("omits 目標逆算フェーズ from nav when periodization absent", async () => {
    renderDetail({ this_week: { volume_km: 30 } });

    const nav = await screen.findByRole("navigation", {
      name: "セクション目次",
    });
    expect(within(nav).queryByText("目標逆算フェーズ")).not.toBeInTheDocument();
  });

  it("includes 実績サマリー and 総評 in nav when present", async () => {
    renderDetail(fullReview);

    const nav = await screen.findByRole("navigation", {
      name: "セクション目次",
    });
    const actuals = within(nav).getByRole("link", { name: "実績サマリー" });
    const overall = within(nav).getByRole("link", { name: "総評" });
    expect(actuals).toHaveAttribute("href", "#wr-actuals");
    expect(overall).toHaveAttribute("href", "#wr-overall");

    // The corresponding Section cards carry the matching anchor ids.
    expect(document.getElementById("wr-actuals")).not.toBeNull();
    expect(document.getElementById("wr-overall")).not.toBeNull();
  });

  it("renders 総評 last when present", async () => {
    renderDetail(fullReview);

    const overallHeading = await screen.findByRole("heading", {
      level: 2,
      name: "総評",
    });
    expect(overallHeading).toBeInTheDocument();
    // 総評 is standalone: not nested inside the 次アクション group region.
    expect(
      overallHeading.closest('section[aria-label="次アクション"]'),
    ).toBeNull();
    // ...and it is the last Section card heading in DOM order.
    const cardHeadings = screen.getAllByRole("heading", { level: 2 });
    expect(cardHeadings[cardHeadings.length - 1]).toHaveTextContent("総評");
  });
});
