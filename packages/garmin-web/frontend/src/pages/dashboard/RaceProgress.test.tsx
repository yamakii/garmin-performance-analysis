import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { GoalRace, RaceReadiness } from "../../types";
import RaceProgress from "./RaceProgress";

/** ISO date `days` from today in local time, so countdowns stay deterministic. */
function isoDaysFromToday(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(
    date.getDate(),
  ).padStart(2, "0")}`;
}

const GOAL_A: GoalRace = {
  goal_id: 25,
  race_name: "さいたまマラソン",
  race_date: isoDaysFromToday(120),
  priority: "A",
  goal_type: "marathon",
  distance_km: 42.195,
  target_time_seconds: 16200,
  status: "active",
  notes: null,
};

const GOAL_B: GoalRace = {
  goal_id: 26,
  race_name: "新潟シティマラソン",
  race_date: isoDaysFromToday(30),
  priority: "B",
  goal_type: "marathon",
  distance_km: 42.195,
  target_time_seconds: 12600,
  status: "active",
  notes: null,
};

const READINESS: RaceReadiness = {
  current_vdot: 44.0,
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

function renderProgress(
  readiness: RaceReadiness | null = READINESS,
  goals: GoalRace[] | null = [GOAL_A, GOAL_B],
) {
  return render(
    <MemoryRouter>
      <RaceProgress readiness={readiness} goals={goals} />
    </MemoryRouter>,
  );
}

describe("RaceProgress", () => {
  it("test_race_progress_compact_single_row", () => {
    renderProgress();

    // Only the A race is counted down; the B tile and the four-metric
    // prediction grid moved to the Goal page (#895).
    expect(screen.getByText("さいたまマラソン")).toBeInTheDocument();
    expect(screen.getByText("あと")).toBeInTheDocument();
    expect(screen.getByText("120")).toBeInTheDocument();
    expect(screen.queryByText("新潟シティマラソン")).not.toBeInTheDocument();
    expect(screen.queryByText("目標との差")).not.toBeInTheDocument();
    expect(screen.queryByText("−57:46")).not.toBeInTheDocument();
  });

  it("test_race_progress_links_to_goal", () => {
    renderProgress();

    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute("href", "/goal");
    expect(screen.getByText("目標へ →")).toBeInTheDocument();
  });

  it("test_race_progress_link_exposes_content", () => {
    renderProgress();

    const link = screen.getByRole("link");
    // The old `aria-label="レースへの道"` replaced the strip's whole accessible
    // name, so link-by-link navigation heard the title and nothing else (#912).
    expect(link).not.toHaveAttribute("aria-label");
    const name = link.textContent ?? "";
    expect(name).toContain("あと");
    expect(name).toContain("120");
    expect(name).toContain("さいたまマラソン");
  });

  it("summarises VDOT, prediction and target on one line", () => {
    renderProgress();

    expect(screen.getByText("44.0")).toBeInTheDocument();
    expect(screen.getByText("3:32:14")).toBeInTheDocument();
    expect(screen.getByText("4:30:00")).toBeInTheDocument();
    expect(screen.getByText("前倒し")).toBeInTheDocument();
  });

  it("falls back to the nearest upcoming race without an A race", () => {
    renderProgress(READINESS, [GOAL_B]);

    expect(screen.getByText("新潟シティマラソン")).toBeInTheDocument();
    expect(screen.getByText("30")).toBeInTheDocument();
  });

  it("labels a missing or past race date instead of a countdown", () => {
    renderProgress(READINESS, [{ ...GOAL_A, race_date: null }]);
    expect(screen.getByText("日程未定")).toBeInTheDocument();

    renderProgress(READINESS, [{ ...GOAL_A, race_date: "2020-10-11" }]);
    expect(screen.getByText("開催済み")).toBeInTheDocument();
  });

  it("renders nothing when there are no goals and no VDOT", () => {
    const { container } = renderProgress(null, []);

    expect(container).toBeEmptyDOMElement();
  });

  it("still renders the prediction row without registered goals", () => {
    renderProgress(READINESS, []);

    expect(screen.getByText("44.0")).toBeInTheDocument();
  });
});
