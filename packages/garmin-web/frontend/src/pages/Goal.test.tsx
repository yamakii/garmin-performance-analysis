import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import Goal, { formatTargetTime } from "./Goal";

const FIXTURE_GOAL = {
  profile: {
    current_focus: "サブ4達成に向けた持久力強化",
    focus_notes: "週末ロング走を軸に有酸素ベースを底上げ",
    updated_at: "2026-06-14 09:00:00",
  },
  goals: [
    {
      goal_id: 1,
      race_name: "つくばマラソン",
      race_date: "2026-11-22",
      priority: "A",
      goal_type: "marathon",
      distance_km: 42.195,
      target_time_seconds: 16200,
      status: "active",
      notes: "メインターゲット",
    },
    {
      goal_id: 2,
      race_name: "ハーフマラソン大会",
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

describe("Goal", () => {
  it("renders profile, goals and retrospectives from API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(FIXTURE_GOAL), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    render(
      <MemoryRouter>
        <Goal />
      </MemoryRouter>,
    );

    // Profile focus
    expect(
      await screen.findByText("サブ4達成に向けた持久力強化"),
    ).toBeInTheDocument();

    // Race rows: names + human-readable target time
    expect(screen.getByText("つくばマラソン")).toBeInTheDocument();
    expect(screen.getByText("ハーフマラソン大会")).toBeInTheDocument();
    expect(screen.getByText("4:30:00")).toBeInTheDocument();
    expect(screen.getByText("2:00:00")).toBeInTheDocument();

    // Null race date renders as 未定
    expect(screen.getByText("未定")).toBeInTheDocument();

    // Retrospective
    expect(screen.getByText("2025秋シーズン")).toBeInTheDocument();
    expect(
      screen.getByText("故障なく走り込めた一方、後半の失速が課題でした。"),
    ).toBeInTheDocument();
  });
});
