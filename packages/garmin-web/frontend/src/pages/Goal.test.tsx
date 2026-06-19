import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import Goal, { daysUntil, formatGap, formatTargetTime } from "./Goal";

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
    race_date: "2099-02-01",
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

/** A race date comfortably in the future so the countdown is positive. */
const FUTURE_DATE = "2099-02-01";

const FIXTURE_GOAL = {
  profile: {
    current_focus: "サブ4達成に向けた持久力強化",
    focus_notes:
      "全体方針は積み上げ。【ボトルネック】後半の失速を抑える【ロング走】月2回 30km",
    updated_at: "2026-06-14 09:00:00",
  },
  goals: [
    {
      goal_id: 1,
      race_name: "さいたまマラソン",
      race_date: FUTURE_DATE,
      priority: "A",
      goal_type: "marathon",
      distance_km: 42.195,
      target_time_seconds: 16200,
      status: "active",
      notes: "メインターゲット",
    },
    {
      goal_id: 2,
      race_name: "新潟ハーフ",
      race_date: null,
      priority: "B",
      goal_type: "half",
      distance_km: 21.0975,
      target_time_seconds: 7200,
      status: "active",
      notes: "調整レース",
    },
  ],
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
 * payload (defaults to a 404 so the supplementary card stays hidden).
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

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("formatTargetTime", () => {
  it("formats seconds as H:MM:SS", () => {
    expect(formatTargetTime(16200)).toBe("4:30:00");
    expect(formatTargetTime(7200)).toBe("2:00:00");
    expect(formatTargetTime(null)).toBe("-");
  });
});

describe("daysUntil", () => {
  it("returns whole days to a future date and null for missing/invalid", () => {
    const today = new Date(2026, 0, 1); // 2026-01-01 local
    expect(daysUntil("2026-01-11", today)).toBe(10);
    expect(daysUntil("2025-12-31", today)).toBe(-1);
    expect(daysUntil(null, today)).toBeNull();
    expect(daysUntil("not-a-date", today)).toBeNull();
  });
});

describe("formatGap", () => {
  it("formats signed gaps as ±M:SS / ±H:MM:SS", () => {
    expect(formatGap(-900)).toBe("−15:00");
    expect(formatGap(900)).toBe("+15:00");
    expect(formatGap(0)).toBe("±0:00");
    expect(formatGap(3661)).toBe("+1:01:01");
  });
});

describe("Goal", () => {
  it("test_Goal_renders_race_prediction_card", async () => {
    stubFetch(FIXTURE_GOAL, FIXTURE_READINESS);

    render(
      <MemoryRouter>
        <Goal />
      </MemoryRouter>,
    );

    // Section heading and goal race name.
    expect(await screen.findByText("レース予測")).toBeInTheDocument();

    // Predicted time formatted via formatTargetTime (15300 -> 4:15:00).
    expect(screen.getByText("4:15:00")).toBeInTheDocument();

    // VDOT value rendered.
    expect(screen.getByText("48.5")).toBeInTheDocument();

    // Gap and "ahead" status badge.
    expect(screen.getByText("−15:00")).toBeInTheDocument();
    expect(screen.getByText("前倒し")).toBeInTheDocument();
  });

  it("test_Goal_renders_race_countdown", async () => {
    stubFetch(FIXTURE_GOAL);

    render(
      <MemoryRouter>
        <Goal />
      </MemoryRouter>,
    );

    // Hero shows the A race name and the countdown scaffolding.
    expect(await screen.findByText("目標レースまで")).toBeInTheDocument();
    expect(screen.getAllByText("さいたまマラソン").length).toBeGreaterThan(0);
    expect(screen.getAllByText("あと").length).toBeGreaterThan(0);

    // Target time formatted via formatTargetTime is shown.
    expect(screen.getAllByText("4:30:00").length).toBeGreaterThan(0);

    // B race with null date shows the "日程未定" badge.
    expect(screen.getAllByText("日程未定").length).toBeGreaterThan(0);
  });

  it("test_Goal_renders_focus_accordion", async () => {
    stubFetch(FIXTURE_GOAL);

    render(
      <MemoryRouter>
        <Goal />
      </MemoryRouter>,
    );

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

  it("test_Goal_renders_race_cards_with_notes", async () => {
    stubFetch(FIXTURE_GOAL);

    render(
      <MemoryRouter>
        <Goal />
      </MemoryRouter>,
    );

    await screen.findByText("目標レース");

    // notes (previously hidden) are now rendered.
    expect(screen.getByText("メインターゲット")).toBeInTheDocument();
    expect(screen.getByText("調整レース")).toBeInTheDocument();

    // Retrospective timeline.
    expect(screen.getByText("2025秋シーズン")).toBeInTheDocument();
    expect(
      screen.getByText("故障なく走り込めた一方、後半の失速が課題でした。"),
    ).toBeInTheDocument();
  });

  it("test_Goal_empty_states", async () => {
    stubFetch({
      profile: { current_focus: null, focus_notes: null, updated_at: null },
      goals: [],
      retrospectives: [],
    });

    render(
      <MemoryRouter>
        <Goal />
      </MemoryRouter>,
    );

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

    render(
      <MemoryRouter>
        <Goal />
      </MemoryRouter>,
    );

    // Whole free-text note is shown even without 【…】 headings.
    expect(
      await screen.findByText(
        "見出しの無い自由記述メモ。これを丸ごと1ブロックで出す。",
      ),
    ).toBeInTheDocument();
  });
});
