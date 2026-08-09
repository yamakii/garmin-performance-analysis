import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "../test/utils";
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

/** 10 lines — past both the line and the character budget of `lines={3}`. */
const LONG_OVERALL = Array.from(
  { length: 10 },
  (_, i) => `${i + 1}行目の総評テキストです。`,
).join("\n");

function renderDetail(reviewData: WeeklyReviewData) {
  return renderVersions([reviewData]);
}

/** Renders the page with one saved version per review payload (newest first). */
function renderVersions(reviewDataList: WeeklyReviewData[]) {
  const versions = reviewDataList.map((reviewData, i) => ({
    review_id: i + 1,
    user_id: "default",
    week_start_date: "2026-06-15",
    week_end_date: "2026-06-21",
    review_date: "2026-06-22",
    review_data: reviewData,
    created_at: `2026-06-2${2 - i}T09:00:00`,
    agent_name: "weekly-review",
    agent_version: "1.0",
  }));
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
        level: 3,
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
      await screen.findByRole("heading", { level: 3, name: "実績サマリー" }),
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
        level: 3,
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
        level: 3,
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
      await screen.findByRole("heading", { level: 3, name: "実績サマリー" }),
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

  it("test_weekly_group_headings", async () => {
    renderDetail(fullReview);

    // The groups are the page's h2s...
    for (const name of ["今週の実績", "評価", "次アクション"]) {
      expect(
        await screen.findByRole("heading", { level: 2, name }),
      ).toBeInTheDocument();
    }

    // ...and every card inside a group is an h3 under it, so the outline
    // reflects the grouping instead of one flat run of h2 cards (#912).
    const group = screen.getByRole("region", { name: "今週の実績" });
    expect(
      within(group).getByRole("heading", { level: 3, name: "実績サマリー" }),
    ).toBeInTheDocument();
    expect(
      within(group).getByRole("heading", { level: 3, name: "体重トラッキング" }),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole("region", { name: "評価" })).getByRole("heading", {
        level: 3,
        name: "対象週プラン評価",
      }),
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
      await screen.findByRole("heading", { level: 3, name: "実績サマリー" }),
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

  it("test_actuals_rendered_as_stat_tiles", async () => {
    renderDetail({ this_week: { volume_km: 42.5, run_count: 4 } });

    await screen.findByRole("heading", { level: 3, name: "実績サマリー" });

    // Each figure is a <dd> inside the tile grid, with its unit as a suffix.
    const volume = screen.getByText("42.5");
    expect(volume.tagName).toBe("DD");
    expect(volume.closest("dl")).not.toBeNull();
    expect(volume.textContent).toBe("42.5km");

    const runs = screen.getByText("4");
    expect(runs.tagName).toBe("DD");
    expect(runs.textContent).toBe("4回");

    // The label is a tile caption now, not a "走行距離: 42.5 km" prose row.
    expect(screen.getByText("走行距離").tagName).toBe("DT");
    expect(screen.queryByText(/走行距離:/)).not.toBeInTheDocument();
  });

  it("test_weight_flag_renders_warn_chip", async () => {
    renderDetail({
      weight_tracking: { recent_median_kg: 79.6, flag: "増加傾向" },
    });

    await screen.findByRole("heading", { level: 3, name: "体重トラッキング" });

    const flag = screen.getByText("増加傾向");
    expect(flag).toHaveClass("bg-status-warn/10");
    expect(flag).toHaveClass("text-status-warn");
  });

  it("test_periodization_countdown_chips", async () => {
    renderDetail({
      periodization: { weeks_to_a_race: 12, expected_phase: "基礎構築" },
    });

    await screen.findByRole("heading", { level: 3, name: "目標逆算フェーズ" });

    expect(screen.getByText(/Aレースまで 12週/)).toBeInTheDocument();
    expect(screen.getByText(/基礎構築/)).toBeInTheDocument();

    // The five prose rows are gone: the card is chips only.
    const card = document.getElementById("wr-periodization");
    expect(card?.querySelectorAll("p")).toHaveLength(0);
    expect(screen.queryByText(/あるべきフェーズ/)).not.toBeInTheDocument();
    expect(screen.queryByText(/ギャップ/)).not.toBeInTheDocument();
  });

  it("test_verdict_ratings_as_badges", async () => {
    renderDetail({
      verdict: [
        { date: "2026-06-16", session: "Easy Run", rating: "✅" },
        { date: "2026-06-18", session: "Tempo", rating: "🟡" },
        { date: "2026-06-20", session: "Long Run", rating: "🔴" },
      ],
    });

    await screen.findByRole("heading", { level: 3, name: "対象週プラン評価" });

    // The mark now sits in its own decorative span inside the badge, so the
    // tone class lives one level up.
    expect(screen.getByText("✅").parentElement).toHaveClass("text-status-good");
    expect(screen.getByText("🟡").parentElement).toHaveClass("text-status-warn");
    expect(screen.getByText("🔴").parentElement).toHaveClass("text-status-bad");
  });

  it("test_verdict_emoji_has_text", async () => {
    renderDetail({
      verdict: [
        { date: "2026-06-16", session: "Easy Run", rating: "✅" },
        { date: "2026-06-18", session: "Tempo", rating: "🟡" },
        { date: "2026-06-20", session: "Long Run", rating: "🔴" },
      ],
    });

    await screen.findByRole("heading", { level: 3, name: "対象週プラン評価" });

    // Each mark is paired with the word it stands for, and the mark itself is
    // decorative — color and emoji alone never carry the verdict (#912).
    const bad = screen.getByText("要改善");
    expect(bad).toHaveTextContent("🔴");
    expect(within(bad).getByText("🔴")).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByText("良好")).toHaveTextContent("✅");
    expect(screen.getByText("注意")).toHaveTextContent("🟡");
  });

  it("test_prose_sections_clamped", async () => {
    renderDetail({ overall: LONG_OVERALL });

    await screen.findByRole("heading", { level: 2, name: "総評" });

    const toggle = screen.getByRole("button", { name: "続きを読む" });
    fireEvent.click(toggle);

    expect(screen.getByRole("button", { name: "閉じる" })).toBeInTheDocument();
    expect(screen.getByText(/10行目の総評テキストです。/)).toBeInTheDocument();
  });

  it("test_recommendations_first_visible_rest_collapsed", async () => {
    renderDetail({
      recommendations: [
        "月曜は休養に充てる",
        "水曜はテンポ走を20分",
        "日曜はロング走を90分",
      ],
    });

    await screen.findByRole("heading", { level: 3, name: "推奨アクション" });

    // The lead action stands on its own, outside the disclosure.
    expect(screen.getByText("月曜は休養に充てる").closest("details")).toBeNull();

    const details = screen.getByText("他の推奨 2件").closest("details");
    expect(details).not.toBeNull();
    expect(details!.hasAttribute("open")).toBe(false);
    expect(within(details!).getByText("水曜はテンポ走を20分")).toBeInTheDocument();
    expect(within(details!).getByText("日曜はロング走を90分")).toBeInTheDocument();

    // Opening it reveals every remaining action.
    fireEvent.click(details!.querySelector("summary")!);
    expect(details!.hasAttribute("open")).toBe(true);
  });

  it("test_version_select_and_sections_nav_unchanged", async () => {
    renderVersions([
      { ...fullReview, overall: "最新版の総評です。" },
      { ...fullReview, overall: "旧版の総評です。" },
    ]);

    const select = await screen.findByLabelText("版を選択:");
    expect(screen.getByText("全2版")).toBeInTheDocument();
    expect(screen.getByText("最新版の総評です。")).toBeInTheDocument();

    // The in-page nav still links every rendered Section card.
    const nav = screen.getByRole("navigation", { name: "セクション目次" });
    expect(
      within(nav).getByRole("link", { name: "実績サマリー" }),
    ).toHaveAttribute("href", "#wr-actuals");
    expect(within(nav).getByRole("link", { name: "総評" })).toHaveAttribute(
      "href",
      "#wr-overall",
    );

    // Switching versions still swaps the rendered payload.
    fireEvent.change(select, { target: { value: "1" } });
    expect(screen.getByText("旧版の総評です。")).toBeInTheDocument();
    expect(screen.queryByText("最新版の総評です。")).not.toBeInTheDocument();
  });
});
