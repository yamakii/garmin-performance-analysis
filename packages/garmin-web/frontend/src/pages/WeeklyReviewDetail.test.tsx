import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "../test/utils";
import WeeklyReviewDetail from "./WeeklyReviewDetail";
import type { WeeklyReviewData } from "../types";

/**
 * Accessible name of the actuals group for `fullReview`: the label states the
 * week the numbers come from (W-1 of the reviewed plan week), not 今週 (#931).
 */
const ACTUALS_GROUP = "実績（2026-06-08 〜 2026-06-14）";

/** Full review touching every meaning group + 総評. */
const fullReview: WeeklyReviewData = {
  // A saved review always records which week its actuals cover.
  actuals_week_start: "2026-06-08",
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

/** 80+ characters of HR narration, as the agent actually writes it (#1144). */
const LONG_HR_DISCIPLINE =
  "25km ロングを平均 HR145.7・上限 150bpm 以内で通し、HR ドリフトは終盤の 5km でも 3% 以内に収まっています。";

/** The expected phase is a sentence of reasoning, not a one-word label. */
const LONG_PHASE =
  "テーパー前の最終デロード。ロングを直近ピーク比 −35% に落とし、質練はゼロにします。";

/** 10 lines — past both the line and the character budget of `lines={3}`. */
const LONG_OVERALL = Array.from(
  { length: 10 },
  (_, i) => `${i + 1}行目の総評テキストです。`,
).join("\n");

/** An empty month grid: the week has no structured prescriptions (#983). */
const EMPTY_MONTH_ADHERENCE = {
  prescribed: 0,
  done: 0,
  replaced: 0,
  skipped: 0,
  pending: 0,
};

function monthPlan(prescriptions: unknown[] = []) {
  return {
    month: "2026-06",
    week_start_day: 0,
    weeks: [
      {
        week_start: "2026-06-15",
        week_end: "2026-06-21",
        in_month: true,
        ladder_step: null,
        review_exists: true,
        adherence: EMPTY_MONTH_ADHERENCE,
        days: [
          {
            date: "2026-06-16",
            in_month: true,
            prescriptions,
            activities: [],
          },
        ],
      },
    ],
    blocks: [],
    adherence: EMPTY_MONTH_ADHERENCE,
  };
}

function renderDetail(
  reviewData: WeeklyReviewData,
  prescriptions: unknown[] = [],
) {
  return renderVersions([reviewData], prescriptions);
}

/** Renders the page with one saved version per review payload (newest first). */
function renderVersions(
  reviewDataList: WeeklyReviewData[],
  prescriptions: unknown[] = [],
) {
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
  // A fresh Response per call: a Response body can only be read once, and the
  // page now fetches the month plan alongside the review versions.
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      const payload = url.includes("/api/plan/month")
        ? monthPlan(prescriptions)
        : versions;
      return Promise.resolve(
        new Response(JSON.stringify(payload), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }),
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

  it("test_renders_garmin_conflicts_table", async () => {
    renderDetail({
      ...fullReview,
      garmin_conflicts: [
        {
          date: "2026-06-20",
          garmin_title: "Anaerobic Base",
          reason: "ロング走の前日に高強度が入っています",
        },
      ],
    });

    // The conflicts replace the raw planned-workout table (#980).
    expect(
      await screen.findByRole("heading", {
        level: 3,
        name: "Garmin との衝突",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Anaerobic Base")).toBeInTheDocument();
    expect(
      screen.getByText("ロング走の前日に高強度が入っています"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "来週のGarminワークアウト" }),
    ).toBeNull();
  });

  it("test_renders_prescriptions_with_status_chips", async () => {
    renderDetail(fullReview, [
      {
        prescription_id: 11,
        session_type: "long",
        title: "ロング 22km",
        target_km: 22,
        target_minutes: null,
        hr_high: 150,
        status: "done",
      },
    ]);

    // The structured row replaces the prose verdict row for that day, keeping
    // the coach's rating and comment alongside the target and status.
    expect(await screen.findByText("ロング 22km")).toBeInTheDocument();
    expect(screen.getByText("22km ≤150")).toBeInTheDocument();
    expect(screen.getByText("実施")).toBeInTheDocument();
    // The 2026-06-16 verdict merged onto the prescription of that day.
    expect(screen.getByText("good")).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: "目標" }),
    ).toBeInTheDocument();
  });

  it("prefers prescription.rating/rationale over the stored verdict", async () => {
    renderDetail(fullReview, [
      {
        prescription_id: 12,
        session_type: "long",
        title: "ロング 22km",
        target_km: 22,
        target_minutes: null,
        hr_high: 150,
        rating: "✅",
        rationale: "ラダー2段目。HR 150 を超えないように。",
        status: "done",
      },
    ]);

    // The prescription row is canonical (#1021): its rating and comment win
    // over the same day's stored verdict ("◎" / "good").
    expect(
      await screen.findByText("ラダー2段目。HR 150 を超えないように。"),
    ).toBeInTheDocument();
    expect(screen.getByText("良好")).toBeInTheDocument();
    expect(screen.queryByText("good")).not.toBeInTheDocument();
  });

  it("test_renders_intensity_distribution", async () => {
    renderDetail({
      this_week: {
        volume_km: 35.5,
        intensity_distribution: { aerobic_base: 0.5, tempo: 0.25, foo_bar: 0.25 },
      },
    });

    expect(
      await screen.findByRole("heading", { level: 3, name: "実績サマリー" }),
    ).toBeInTheDocument();
    // Buckets read as Japanese shares, not "aerobic base: 0.5" (#1144)...
    expect(screen.getByText("有酸素ベース 50%")).toBeInTheDocument();
    expect(screen.getByText("テンポ 25%")).toBeInTheDocument();
    // ...and an unknown bucket still loses its underscores (#915).
    expect(screen.getByText("foo bar 25%")).toBeInTheDocument();
    expect(screen.queryByText(/aerobic_base|: 0\.5/)).not.toBeInTheDocument();
  });

  it("test_stat_tiles_rounded", async () => {
    renderDetail({ this_week: { volume_km: 42.53333333333333, run_count: 4 } });

    expect(
      await screen.findByRole("heading", { level: 3, name: "実績サマリー" }),
    ).toBeInTheDocument();
    // The raw payload carries float noise; a weekly total needs one decimal.
    expect(screen.getByText("42.5")).toBeInTheDocument();
    expect(screen.queryByText(/42\.53/)).not.toBeInTheDocument();
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

  it("renders three group headings 実績 / 評価 / 次アクション", async () => {
    renderDetail(fullReview);

    expect(
      await screen.findByRole("region", { name: ACTUALS_GROUP }),
    ).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "評価" })).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "次アクション" }),
    ).toBeInTheDocument();
  });

  it("test_weekly_group_headings", async () => {
    renderDetail(fullReview);

    // The groups are the page's h2s...
    for (const name of [ACTUALS_GROUP, "評価", "次アクション"]) {
      expect(
        await screen.findByRole("heading", { level: 2, name }),
      ).toBeInTheDocument();
    }

    // ...and every card inside a group is an h3 under it, so the outline
    // reflects the grouping instead of one flat run of h2 cards (#912).
    const group = screen.getByRole("region", { name: ACTUALS_GROUP });
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

  it("places 実績サマリー under the actuals group", async () => {
    renderDetail(fullReview);

    const group = await screen.findByRole("region", { name: ACTUALS_GROUP });
    expect(within(group).getByText("実績サマリー")).toBeInTheDocument();
  });

  it("test_actuals_group_title_shows_range", async () => {
    renderDetail({
      actuals_week_start: "2026-08-10",
      this_week: { volume_km: 35.5, run_count: 4 },
    });

    // The heading names the week the numbers came from...
    expect(
      await screen.findByRole("heading", {
        level: 2,
        name: "実績（2026-08-10 〜 2026-08-16）",
      }),
    ).toBeInTheDocument();
    // ...instead of claiming they are the week being viewed (#931).
    expect(screen.queryByText("今週の実績")).not.toBeInTheDocument();
  });

  it("test_actuals_group_title_fallback", async () => {
    // A review saved before the field existed still gets a truthful label.
    renderDetail({ this_week: { volume_km: 35.5, run_count: 4 } });

    expect(
      await screen.findByRole("heading", { level: 2, name: "実績" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("今週の実績")).not.toBeInTheDocument();
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
    expect(flag).toHaveAttribute("data-tone", "warn");
    expect(flag).toHaveClass("bg-warn-tint", "text-status-warn");
  });

  it("test_periodization_countdown_chips", async () => {
    renderDetail({
      periodization: { weeks_to_a_race: 12, expected_phase: "基礎構築" },
    });

    await screen.findByRole("heading", { level: 3, name: "目標逆算フェーズ" });

    expect(screen.getByText(/Aレースまで 12週/)).toBeInTheDocument();
    expect(screen.getByText(/基礎構築/)).toBeInTheDocument();

    // The five label rows are gone: the countdown is a chip and the phase is
    // the card's one paragraph (it carries a sentence, #1144).
    const card = document.getElementById("wr-periodization");
    expect(card?.querySelectorAll("p")).toHaveLength(1);
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
    expect(screen.getByText("✅").parentElement).toHaveAttribute("data-tone", "good");
    expect(screen.getByText("🟡").parentElement).toHaveAttribute("data-tone", "warn");
    expect(screen.getByText("🔴").parentElement).toHaveAttribute("data-tone", "bad");
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

  it("test_unknown_week_shows_empty_state", async () => {
    // A week nobody reviewed (or a mistyped URL): the API answers 200 [].
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("[]", {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    render(
      <MemoryRouter initialEntries={["/weekly-reviews/2020-01-01"]}>
        <Routes>
          <Route
            path="/weekly-reviews/:weekStart"
            element={<WeeklyReviewDetail />}
          />
        </Routes>
      </MemoryRouter>,
    );

    // Previously this rendered nothing at all — a white page (#914).
    expect(
      await screen.findByText("この週のレビューはありません"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "週次レビュー一覧へ" }),
    ).toHaveAttribute("href", "/weekly-reviews");
  });

  it("test_weekly_review_hr_discipline_wraps", async () => {
    renderDetail({
      this_week: { volume_km: 35.5, hr_discipline: LONG_HR_DISCIPLINE },
    });

    await screen.findByRole("heading", { level: 3, name: "実績サマリー" });

    // The sentence is prose, not a tag: as a `shrink-0` mono chip it kept one
    // line and ran 100px past the content width, widening the page (#1144).
    const text = screen.getByText(LONG_HR_DISCIPLINE);
    expect(text.tagName).toBe("P");
    expect(text).not.toHaveClass("shrink-0");
    expect(text).not.toHaveAttribute("data-tone");
  });

  it("test_weekly_review_expected_phase_wraps", async () => {
    renderDetail({ periodization: { expected_phase: LONG_PHASE } });

    await screen.findByRole("heading", { level: 3, name: "目標逆算フェーズ" });

    const text = screen.getByText(`想定 ${LONG_PHASE}`);
    expect(text.tagName).toBe("P");
    expect(text).not.toHaveClass("shrink-0");
    expect(text).not.toHaveAttribute("data-tone");
  });

  it("test_weekly_review_tables_have_scroll_wrapper", async () => {
    renderDetail(
      {
        ...fullReview,
        garmin_conflicts: [
          {
            date: "2026-06-20",
            garmin_title: "Anaerobic Base",
            reason: "ロング走の前日に高強度が入っています",
          },
        ],
      },
      [
        {
          prescription_id: 11,
          session_type: "rest",
          title: "完全休養（ロング翌日）",
          target_km: null,
          target_minutes: null,
          hr_high: null,
          status: "registered",
        },
      ],
    );

    await screen.findByRole("heading", { level: 3, name: "対象週プラン評価" });

    // On a 390px screen the comment column used to fall off the page with no
    // way to reach it: every table scrolls inside its own wrapper (#1144).
    const tables = document.querySelectorAll("table");
    expect(tables.length).toBeGreaterThan(0);
    for (const table of tables) {
      expect(table.parentElement).toHaveClass("overflow-x-auto");
      expect(table.className).toMatch(/min-w-\[/);
    }
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
