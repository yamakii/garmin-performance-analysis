import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "../test/utils";
import Goal from "./Goal";

// echarts needs a real canvas; jsdom has none, so the prediction chart's
// renderer is stubbed. The section's presence (heading + labelled figure) is
// what this page asserts — the option itself is covered by
// goal/predictionChartOption.test.ts.
vi.mock("../lib/echarts", () => ({
  echarts: {
    init: () => ({
      setOption: vi.fn(),
      resize: vi.fn(),
      dispose: vi.fn(),
    }),
  },
}));

/** A race date comfortably in the future so the countdown is positive. */
const FUTURE_DATE = "2099-02-01";

const FIXTURE_READINESS = {
  current_vdot: 48.5,
  predicted_times: {
    race_5k: 1290,
    race_10k: 2670,
    half: 5910,
    full: 12360,
  },
  goal: {
    race_name: "さいたまマラソン",
    race_date: FUTURE_DATE,
    distance_km: 42.195,
    target_time_seconds: 16200,
  },
  progress: {
    predicted_time_seconds: 15300, // 4:15:00
    gap_seconds: -900, // 15min ahead of the 4:30:00 target
    pace_gap_sec_per_km: -21.3,
    weeks_remaining: 18,
    status: "ahead",
  },
};

const EMPTY_PROFILE = {
  current_focus: null,
  focus_notes: null,
  updated_at: null,
};

const A_RACE = {
  goal_id: 1,
  race_name: "さいたまマラソン",
  race_date: FUTURE_DATE,
  priority: "A",
  goal_type: "marathon",
  distance_km: 42.195,
  target_time_seconds: 16200,
  status: "active",
  notes: "メインターゲット",
};

const B_RACE = {
  goal_id: 2,
  race_name: "新潟ハーフ",
  race_date: null,
  priority: "B",
  goal_type: "half",
  distance_km: 21.0975,
  target_time_seconds: 7200,
  status: "active",
  notes: "調整レース",
};

const OTHER_RACE = {
  goal_id: 3,
  race_name: "谷川真理ハーフ",
  race_date: FUTURE_DATE,
  priority: "C",
  goal_type: "half",
  distance_km: 21.0975,
  target_time_seconds: 7500,
  status: "planned",
  notes: "練習レース",
};

const FIXTURE_GOAL = {
  profile: {
    current_focus: "サブ4達成に向けた持久力強化",
    focus_notes:
      "全体方針は積み上げ。【ボトルネック】後半の失速を抑える【ロング走】月2回 30km",
    updated_at: "2026-06-14 09:00:00",
  },
  goals: [A_RACE, B_RACE, OTHER_RACE],
  retrospectives: [
    {
      retro_id: 1,
      season_label: "2025秋シーズン",
      period_start: "2025-09-01",
      period_end: "2025-12-31",
      narrative: "故障なく走り込めた一方、後半の失速が課題でした。",
      key_learnings: "ロング走でのペース管理を重視する",
    },
  ],
};

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

/** What /api/race-prediction-history returns when a test says nothing: an
 *  athlete with no derivable series, so the chart section stays away. */
const EMPTY_PREDICTION = { goal: null, source: null, series: [] };

/**
 * Route by URL: /api/goal -> goal payload, /api/race-readiness -> readiness
 * payload (defaults to a 404 so the prediction stays hidden),
 * /api/race-prediction-history -> `prediction` (a number stands for an error
 * status; omitted means the empty series).
 */
function stubFetch(
  goalPayload: unknown,
  readiness?: unknown,
  prediction: unknown = EMPTY_PREDICTION,
) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/api/race-prediction-history")) {
        if (typeof prediction === "number") {
          return Promise.resolve(new Response(null, { status: prediction }));
        }
        return Promise.resolve(jsonResponse(prediction));
      }
      if (url.includes("/api/race-readiness")) {
        if (readiness === undefined) {
          return Promise.resolve(new Response(null, { status: 404 }));
        }
        return Promise.resolve(jsonResponse(readiness));
      }
      return Promise.resolve(jsonResponse(goalPayload));
    }),
  );
}

function renderGoal() {
  return render(
    <MemoryRouter>
      <Goal />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

// The pure formatters (formatTargetTime / daysUntil / formatGap) live in
// src/utils/race.ts; the verdict sentence in src/utils/verdict.ts. Both are
// covered by their own unit tests.

describe("Goal", () => {
  it("test_goal_verdict_line_opens_the_page", async () => {
    stubFetch(FIXTURE_GOAL, FIXTURE_READINESS);

    renderGoal();

    const heading = await screen.findByRole("heading", { level: 1 });
    // Target 4:30:00 against a 4:15:00 prediction, 15 minutes ahead.
    expect(heading.textContent).toContain(
      "目標 4:30:00 に対して予測 4:15:00。",
    );
    expect(heading.textContent).toContain("前倒し。差 −15:00。");
    // The lead carries the fitness the prediction rests on.
    expect(screen.getByText(/現在 VDOT 48\.5/)).toBeInTheDocument();
  });

  it("test_goal_ab_columns", async () => {
    stubFetch(
      {
        profile: EMPTY_PROFILE,
        goals: [A_RACE, B_RACE],
        retrospectives: [],
      },
      FIXTURE_READINESS,
    );

    const { container } = renderGoal();

    const band = await screen.findByLabelText("目標レース");
    const inBand = within(band);

    // Filled A tag, outlined B tag — the whole hierarchy of the band.
    expect(inBand.getByText("A").className).toContain("bg-ink");
    expect(inBand.getByText("B").className).toContain("border-ink");

    // Each column carries its own countdown and target; the B race has no
    // date, so it says so instead of showing a numeral.
    expect(inBand.getAllByText("目標")).toHaveLength(2);
    expect(inBand.getByText("4:30:00")).toBeInTheDocument();
    expect(inBand.getByText("2:00:00")).toBeInTheDocument();
    expect(inBand.getByText("日程未定")).toBeInTheDocument();
    expect(
      container.querySelector(".text-\\[64px\\]")?.textContent,
    ).toContain("日");

    // The prediction belongs to the A race only.
    expect(inBand.getAllByText(/^予測/)).toHaveLength(1);
    expect(inBand.getByText("予測 (VDOT 48.5)")).toBeInTheDocument();
    expect(inBand.getByText("4:15:00")).toBeInTheDocument();
    expect(inBand.getByText("−15:00")).toBeInTheDocument();

    // Neither featured race is repeated in the list below.
    expect(screen.getAllByText("さいたまマラソン", { exact: false })).toHaveLength(
      1,
    );
    expect(
      screen.getByText("A / B 以外のレースは登録されていません"),
    ).toBeInTheDocument();
  });

  it("test_goal_gap_color_follows_status", async () => {
    // Inside the backend's ±60 s band the line reads 順調, so the gap stays
    // ink even though the prediction trails the target (#1151).
    stubFetch(
      { profile: EMPTY_PROFILE, goals: [A_RACE], retrospectives: [] },
      {
        ...FIXTURE_READINESS,
        progress: {
          predicted_time_seconds: 16230, // 4:30:30 against a 4:30:00 target
          gap_seconds: 30,
          pace_gap_sec_per_km: 0.7,
          weeks_remaining: 18,
          status: "on_track",
        },
      },
    );

    const { unmount } = renderGoal();

    const onTrack = await screen.findByText("+0:30");
    expect(onTrack.className).not.toContain("text-status-warn");
    expect(onTrack.className).toContain("text-ink");
    unmount();

    // 遅れ is the one state worth a colour.
    stubFetch(
      { profile: EMPTY_PROFILE, goals: [A_RACE], retrospectives: [] },
      {
        ...FIXTURE_READINESS,
        progress: {
          predicted_time_seconds: 16800, // 4:40:00
          gap_seconds: 600,
          pace_gap_sec_per_km: 14.2,
          weeks_remaining: 18,
          status: "behind",
        },
      },
    );

    renderGoal();

    const behind = await screen.findByText("+10:00");
    expect(behind.className).toContain("text-status-warn");
    expect(behind.className).toContain("font-bold");
  });

  it("test_goal_focus_rows_and_disclosure", async () => {
    stubFetch({
      profile: {
        current_focus: "持久力強化",
        focus_notes:
          "【ボトルネック】脚の耐久性【ロング走】月2回 30km【ポイント練】週1回【補強】週2回【睡眠】7時間",
        updated_at: null,
      },
      goals: [],
      retrospectives: [],
    });

    renderGoal();

    expect(await screen.findByText("ボトルネック")).toBeInTheDocument();
    expect(screen.getByText("ロング走")).toBeInTheDocument();
    expect(screen.getByText("ポイント練")).toBeInTheDocument();

    // The fourth rule onwards folds away behind one trigger.
    const disclosure = screen.getByText("ルール(2件) 展開");
    expect(disclosure).toBeInTheDocument();
    expect(disclosure.closest("details")?.hasAttribute("open")).toBe(false);
    expect(screen.getByText("補強")).toBeInTheDocument();
    expect(screen.getByText("睡眠")).toBeInTheDocument();
  });

  it("test_goal_other_races_rows", async () => {
    stubFetch({
      profile: EMPTY_PROFILE,
      goals: [
        A_RACE,
        OTHER_RACE,
        { ...OTHER_RACE, goal_id: 4, race_name: "青梅マラソン" },
      ],
      retrospectives: [],
    });

    renderGoal();

    const name = await screen.findByText("谷川真理ハーフ");
    expect(name.className).toContain("font-bold");
    expect(screen.getByText("青梅マラソン")).toBeInTheDocument();

    // Date is mono, and the priority / status pair closes the row.
    const dates = screen.getAllByText(FUTURE_DATE);
    expect(dates[0].className).toContain("font-mono");
    expect(screen.getAllByText("C · 予定")).toHaveLength(2);

    // No cards: the list is ruled rows now.
    expect(document.querySelectorAll("article")).toHaveLength(0);
  });

  it("test_goal_retro_learning_disclosure", async () => {
    stubFetch({
      profile: EMPTY_PROFILE,
      goals: [],
      retrospectives: [
        {
          retro_id: 1,
          season_label: "2025秋シーズン",
          period_start: "2025-09-01",
          period_end: "2025-12-31",
          narrative: "故障なく走り込めました。",
          key_learnings: "ロング走でのペース管理を重視する",
        },
        {
          retro_id: 2,
          season_label: "2024秋シーズン",
          period_start: "2024-09-01",
          period_end: "2024-12-31",
          narrative: "距離を踏めませんでした。",
          key_learnings: "週2回の補強を継続する",
        },
      ],
    });

    renderGoal();

    // The latest season's learning is shown; the older one folds away.
    const learnings = await screen.findAllByText("学び:");
    expect(learnings).toHaveLength(2);
    expect(learnings[0].closest("details")).toBeNull();
    expect(learnings[1].closest("details")).not.toBeNull();
    expect(
      screen.getByText("ロング走でのペース管理を重視する"),
    ).toBeInTheDocument();

    const trigger = screen.getByText("学びを表示");
    expect(trigger.closest("details")?.hasAttribute("open")).toBe(false);
    expect(screen.getByText("週2回の補強を継続する")).toBeInTheDocument();
  });

  it("test_sections_order", async () => {
    stubFetch(FIXTURE_GOAL, FIXTURE_READINESS);

    const { container } = renderGoal();

    await screen.findByText("現フェーズ");

    const headings = Array.from(container.querySelectorAll("h1, h2")).map(
      (el) => el.textContent,
    );
    expect(headings.slice(1)).toEqual([
      "現フェーズ",
      "その他のレース",
      "昨季の振り返り",
    ]);
    expect(headings[0]).toContain("目標 4:30:00");
  });

  it("test_empty_goal_shows_cli_hint", async () => {
    stubFetch({
      profile: EMPTY_PROFILE,
      goals: [],
      retrospectives: [],
    });

    renderGoal();

    expect(
      await screen.findByText("現フェーズが登録されていません"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("目標レースが登録されていません"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("振り返りが登録されていません"),
    ).toBeInTheDocument();

    // All three empty sections point the user at the CLI command.
    expect(screen.getAllByText("/set-goal")).toHaveLength(3);

    // With no race at all the page still opens with a sentence.
    expect(
      (await screen.findByRole("heading", { level: 1 })).textContent,
    ).toContain("目標レース未登録。");
  });

  it("test_Goal_renders_notes_and_retrospectives", async () => {
    stubFetch(FIXTURE_GOAL);

    renderGoal();

    await screen.findByText("その他のレース");

    // Notes render for the featured races; the list rows carry the essentials.
    expect(screen.getByText("メインターゲット")).toBeInTheDocument();
    expect(screen.getByText("調整レース")).toBeInTheDocument();
    expect(screen.getByText("谷川真理ハーフ")).toBeInTheDocument();

    // Retrospective row.
    expect(screen.getByText("2025秋シーズン")).toBeInTheDocument();
    expect(
      screen.getByText("故障なく走り込めた一方、後半の失速が課題でした。"),
    ).toBeInTheDocument();
  });

  it("test_goal_prediction_chart_section", async () => {
    const prediction = {
      goal: {
        race_name: "さいたまマラソン",
        race_date: FUTURE_DATE,
        distance_km: 42.195,
        target_time_seconds: 16200,
      },
      source: "objective",
      series: [
        {
          date: "2026-09-01",
          vdot: 47.1,
          predicted_time_seconds: 16800,
          gap_seconds: 600,
        },
        {
          date: "2026-09-08",
          vdot: 47.8,
          predicted_time_seconds: 16500,
          gap_seconds: 300,
        },
        {
          date: "2026-09-15",
          vdot: 48.5,
          predicted_time_seconds: 16200,
          gap_seconds: 0,
        },
      ],
    };
    stubFetch(FIXTURE_GOAL, FIXTURE_READINESS, prediction);

    const { unmount } = renderGoal();

    expect(
      await screen.findByRole("heading", { level: 2, name: "予測の推移" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("img")).toHaveAccessibleName(
      "レース予測タイムの推移グラフ",
    );
    expect(screen.getByText("客観VDOT換算 · 直近1年")).toBeInTheDocument();
    unmount();

    // Nothing derivable: the section is absent rather than an empty frame.
    stubFetch(FIXTURE_GOAL, FIXTURE_READINESS, {
      goal: null,
      source: null,
      series: [],
    });
    const empty = renderGoal();
    await screen.findByText("現フェーズ");
    expect(screen.queryByText("予測の推移")).toBeNull();
    empty.unmount();

    // A failed fetch is supplementary too: the page renders and stays quiet.
    stubFetch(FIXTURE_GOAL, FIXTURE_READINESS, 500);
    renderGoal();
    await screen.findByText("現フェーズ");
    await waitFor(() =>
      expect(screen.getByText("その他のレース")).toBeInTheDocument(),
    );
    expect(screen.queryByText("予測の推移")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("test_goal_focus_updated_at_formatted", async () => {
    stubFetch({
      profile: {
        current_focus: "サブ4達成に向けた持久力強化",
        focus_notes: null,
        // DuckDB hands the timestamp over with microseconds attached.
        updated_at: "2026-09-15 00:38:46.745998",
      },
      goals: [],
      retrospectives: [],
    });

    renderGoal();

    expect(await screen.findByText("更新 2026-09-15 00:38")).toBeInTheDocument();
    expect(screen.queryByText(/745998/)).toBeNull();
  });

  it("test_Goal_focus_notes_fallback_without_brackets", async () => {
    stubFetch({
      profile: {
        current_focus: "回復力重視",
        focus_notes: "見出しの無い自由記述メモ。これを丸ごと1ブロックで出す。",
        updated_at: null,
      },
      goals: [],
      retrospectives: [],
    });

    renderGoal();

    // Whole free-text note is shown even without 【…】 headings.
    expect(
      await screen.findByText(
        "見出しの無い自由記述メモ。これを丸ごと1ブロックで出す。",
      ),
    ).toBeInTheDocument();
    // …and the preamble of a note that does have headings leads the rows.
    expect(screen.queryByText(/ルール\(/)).toBeNull();
  });
});
