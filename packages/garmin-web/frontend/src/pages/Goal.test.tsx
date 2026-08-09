import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "../test/utils";
import Goal from "./Goal";

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

/**
 * Route by URL: /api/goal -> goal payload, /api/race-readiness -> readiness
 * payload (defaults to a 404 so the prediction stays hidden).
 */
function stubFetch(goalPayload: unknown, readiness?: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
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

// The pure formatters (formatTargetTime / daysUntil / formatGap) now live in
// src/utils/race.ts and are covered by src/utils/race.test.ts.

describe("Goal", () => {
  it("test_featured_race_rendered_once", async () => {
    // One A race + one non-featured race: the A race is headlined by the hero
    // and must not appear a second time as a list card.
    stubFetch({
      profile: EMPTY_PROFILE,
      goals: [A_RACE, OTHER_RACE],
      retrospectives: [],
    });

    const { container } = renderGoal();

    await screen.findByText("目標レースまで");

    const matches = screen.getAllByText("さいたまマラソン");
    expect(matches).toHaveLength(1);

    const hero = container.querySelector("header");
    expect(hero).not.toBeNull();
    expect(hero?.contains(matches[0])).toBe(true);

    // The remaining race is the only one rendered as a card.
    const cards = Array.from(container.querySelectorAll("article"));
    expect(cards).toHaveLength(1);
    expect(cards[0].textContent).toContain("谷川真理ハーフ");
  });

  it("test_hero_shows_prediction_inline", async () => {
    // Predicted 3:45:00 against a 3:40:00 target => +5:00 behind.
    stubFetch(
      {
        profile: EMPTY_PROFILE,
        goals: [{ ...A_RACE, target_time_seconds: 13200 }],
        retrospectives: [],
      },
      {
        current_vdot: 50.2,
        predicted_times: { full: 13500 },
        goal: {
          race_name: "さいたまマラソン",
          race_date: FUTURE_DATE,
          distance_km: 42.195,
          target_time_seconds: 13200,
        },
        progress: {
          predicted_time_seconds: 13500,
          gap_seconds: 300,
          pace_gap_sec_per_km: 7.1,
          weeks_remaining: 18,
          status: "behind",
        },
      },
    );

    const { container } = renderGoal();

    await screen.findByText("目標レースまで");

    const hero = container.querySelector("header");
    expect(hero).not.toBeNull();
    const inHero = within(hero as HTMLElement);

    expect(inHero.getByText("3:45:00")).toBeInTheDocument(); // predicted
    expect(inHero.getByText("3:40:00")).toBeInTheDocument(); // target
    expect(inHero.getByText("+5:00")).toBeInTheDocument(); // gap to target
    expect(inHero.getByText("遅れ")).toBeInTheDocument(); // status badge
    expect(inHero.getByText("50.2")).toBeInTheDocument(); // current VDOT

    // The prediction lives in the hero only — no separate prediction section.
    expect(screen.queryByText("レース予測")).toBeNull();
  });

  it("test_race_list_excludes_featured", async () => {
    stubFetch({
      profile: EMPTY_PROFILE,
      goals: [
        A_RACE,
        B_RACE,
        OTHER_RACE,
        { ...OTHER_RACE, goal_id: 4, race_name: "青梅マラソン" },
      ],
      retrospectives: [],
    });

    const { container } = renderGoal();

    await screen.findByText("レース登録");

    const cards = Array.from(container.querySelectorAll("article"));
    expect(cards).toHaveLength(2);
    const cardText = cards.map((el) => el.textContent ?? "").join(" ");
    expect(cardText).toContain("谷川真理ハーフ");
    expect(cardText).toContain("青梅マラソン");
    expect(cardText).not.toContain("さいたまマラソン");
    expect(cardText).not.toContain("新潟ハーフ");
  });

  it("test_sections_order", async () => {
    stubFetch(FIXTURE_GOAL, FIXTURE_READINESS);

    const { container } = renderGoal();

    await screen.findByText("目標レースまで");

    const headings = Array.from(container.querySelectorAll("h1, h2")).map(
      (el) => el.textContent,
    );
    expect(headings).toEqual([
      "目標レースまで",
      "現フェーズ",
      "レース登録",
      "昨季の振り返り",
    ]);
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
  });

  it("test_Goal_renders_race_countdown", async () => {
    stubFetch(FIXTURE_GOAL);

    renderGoal();

    // Hero shows the A race name and the countdown scaffolding.
    expect(await screen.findByText("目標レースまで")).toBeInTheDocument();
    expect(screen.getAllByText("さいたまマラソン")).toHaveLength(1);
    expect(screen.getAllByText("あと").length).toBeGreaterThan(0);

    // Target time formatted via formatTargetTime is shown.
    expect(screen.getAllByText("4:30:00").length).toBeGreaterThan(0);

    // B race with null date shows the "日程未定" badge.
    expect(screen.getAllByText("日程未定").length).toBeGreaterThan(0);
  });

  it("test_Goal_renders_focus_accordion", async () => {
    stubFetch(FIXTURE_GOAL);

    renderGoal();

    // current_focus lead line.
    expect(
      await screen.findByText("サブ4達成に向けた持久力強化"),
    ).toBeInTheDocument();

    // focus_notes 【…】 headings become section card titles.
    expect(screen.getByText("ボトルネック")).toBeInTheDocument();
    expect(screen.getByText("ロング走")).toBeInTheDocument();
    expect(screen.getByText("後半の失速を抑える")).toBeInTheDocument();

    // Preamble before the first heading is shown as a lead paragraph.
    expect(screen.getByText("全体方針は積み上げ。")).toBeInTheDocument();
  });

  it("test_Goal_renders_notes_and_retrospectives", async () => {
    stubFetch(FIXTURE_GOAL);

    renderGoal();

    await screen.findByText("レース登録");

    // Notes render for the featured races (hero) and the listed race (card).
    expect(screen.getByText("メインターゲット")).toBeInTheDocument();
    expect(screen.getByText("調整レース")).toBeInTheDocument();
    expect(screen.getByText("練習レース")).toBeInTheDocument();

    // Retrospective timeline.
    expect(screen.getByText("2025秋シーズン")).toBeInTheDocument();
    expect(
      screen.getByText("故障なく走り込めた一方、後半の失速が課題でした。"),
    ).toBeInTheDocument();
  });

  it("test_Goal_second_a_race_keeps_list_emphasis", async () => {
    // Two priority-A races: the hero only headlines the first one, so the
    // second A race lands in the list and keeps its signal ring + left bar.
    stubFetch({
      profile: EMPTY_PROFILE,
      goals: [
        { ...A_RACE, notes: null },
        {
          goal_id: 5,
          race_name: "別大マラソン",
          race_date: FUTURE_DATE,
          priority: "A",
          goal_type: "marathon",
          distance_km: 42.195,
          target_time_seconds: 15600,
          status: "active",
          notes: null,
        },
      ],
      retrospectives: [],
    });

    const { container } = renderGoal();

    await screen.findByText("レース登録");

    const cards = Array.from(container.querySelectorAll("article"));
    expect(cards).toHaveLength(1);
    expect(cards[0].textContent).toContain("別大マラソン");
    expect(cards[0].className).toContain("ring-signal");
    expect(cards[0].querySelector(".bg-signal")).not.toBeNull();
  });

  it("test_goal_focus_sections_still_first_three_open", async () => {
    // Four titled sections: after the switch to the shared `Disclosure`, the
    // first three must still be expanded and the fourth collapsed.
    stubFetch({
      profile: {
        current_focus: "持久力強化",
        focus_notes:
          "【ボトルネック】脚の耐久性【ロング走】月2回 30km【ポイント練】週1回【補強】週2回",
        updated_at: null,
      },
      goals: [],
      retrospectives: [],
    });

    const { container } = renderGoal();

    expect(await screen.findByText("ボトルネック")).toBeInTheDocument();

    const sections = Array.from(container.querySelectorAll("details"));
    expect(sections).toHaveLength(4);
    expect(sections.map((section) => section.hasAttribute("open"))).toEqual([
      true,
      true,
      true,
      false,
    ]);
    expect(screen.getByText("補強")).toBeInTheDocument();
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
  });
});
