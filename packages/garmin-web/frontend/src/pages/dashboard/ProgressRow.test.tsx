import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { ActivitySummary, GoalRace, RaceReadiness } from "../../types";
import { toIsoDate } from "../../utils/format";
import ProgressRow from "./ProgressRow";

/** A race `days` from today, so the countdown does not depend on the clock. */
function raceDateIn(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return toIsoDate(date);
}

function goal(overrides: Partial<GoalRace> = {}): GoalRace {
  return {
    goal_id: 25,
    race_name: "さいたまマラソン",
    race_date: raceDateIn(60),
    priority: "A",
    goal_type: "marathon",
    distance_km: 42.195,
    target_time_seconds: 16200,
    status: "active",
    notes: null,
    ...overrides,
  };
}

const READINESS: RaceReadiness = {
  current_vdot: 44,
  predicted_times: { full: 12734 },
  goal: {
    race_name: "さいたまマラソン",
    race_date: null,
    distance_km: 42.195,
    target_time_seconds: 16200,
  },
  progress: {
    predicted_time_seconds: 12734,
    gap_seconds: -3466,
    pace_gap_sec_per_km: -82.1,
    weeks_remaining: null,
    status: "ahead",
  },
};

const ACTIVITY: ActivitySummary = {
  activity_id: 2001,
  activity_date: "2026-09-13",
  activity_name: "ロングラン",
  total_distance_km: 21.43,
  total_time_seconds: 8100,
  avg_pace_seconds_per_km: 378,
  avg_heart_rate: 146,
};

function renderRow(props: Partial<Parameters<typeof ProgressRow>[0]> = {}) {
  return render(
    <MemoryRouter>
      <ProgressRow
        readiness={READINESS}
        goals={[goal(), goal({ goal_id: 26, priority: "B" })]}
        activities={[ACTIVITY]}
        {...props}
      />
    </MemoryRouter>,
  );
}

describe("ProgressRow", () => {
  it("test_progress_row_race_and_last_run", () => {
    renderRow();

    // Left: the featured (A) race, its countdown and the prediction.
    expect(screen.getByText("さいたまマラソン · A")).toBeInTheDocument();
    expect(screen.getByText(/^60/)).toHaveTextContent("60日");
    expect(screen.getByText(/予測 3:32:14/, { selector: "p" })).toHaveTextContent(
      "予測 3:32:14 · 目標 4:30:00 · −57:46",
    );
    expect(screen.getByRole("link", { name: /さいたまマラソン/ })).toHaveAttribute(
      "href",
      "/goal",
    );

    // Right: the last run only, linked to its detail page.
    expect(
      screen.getByText("前回 · 09/13 SUN · ロングラン"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /21.4/ })).toHaveAttribute(
      "href",
      "/activities/2001",
    );
    expect(screen.getByText("6:18/km · 146bpm")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "すべてのラン →" }),
    ).toHaveAttribute("href", "/activities");
  });

  it("falls back to 日程未定 / 開催済み and the VDOT-only column", () => {
    const { rerender } = renderRow({ goals: [goal({ race_date: null })] });
    expect(screen.getByText("日程未定")).toBeInTheDocument();

    rerender(
      <MemoryRouter>
        <ProgressRow
          readiness={READINESS}
          goals={[goal({ race_date: raceDateIn(-3) })]}
          activities={[ACTIVITY]}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText("開催済み")).toBeInTheDocument();

    // No race at all: the column states the VDOT rather than disappearing.
    rerender(
      <MemoryRouter>
        <ProgressRow readiness={READINESS} goals={[]} activities={[ACTIVITY]} />
      </MemoryRouter>,
    );
    expect(screen.getByText("VDOT")).toBeInTheDocument();
    expect(screen.getByText("44.0")).toBeInTheDocument();
  });

  it("degrades to the empty states when nothing has been recorded", () => {
    renderRow({ readiness: null, goals: [], activities: [] });

    expect(screen.getByText("アクティビティがありません")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "進捗" }),
    ).toBeInTheDocument();
  });
});
