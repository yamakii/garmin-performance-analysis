import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { GoalRace, RaceReadiness } from "../../types";
import RaceProgress from "./RaceProgress";

const GOAL_A: GoalRace = {
  goal_id: 25,
  race_name: "さいたまマラソン",
  race_date: null,
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
  race_date: "2020-10-11", // past date -> deterministic "開催済み"
  priority: "B",
  goal_type: "marathon",
  distance_km: 42.195,
  target_time_seconds: 16200,
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
  it("renders the A/B races with countdown states and target times", () => {
    renderProgress();

    expect(screen.getByText("さいたまマラソン")).toBeInTheDocument();
    expect(screen.getByText("新潟シティマラソン")).toBeInTheDocument();
    // A race has no date; B race date is in the past.
    expect(screen.getByText("日程未定")).toBeInTheDocument();
    expect(screen.getByText("開催済み")).toBeInTheDocument();
    expect(screen.getAllByText("4:30:00")).toHaveLength(2);
  });

  it("renders VDOT, prediction, gap and the status badge", () => {
    renderProgress();

    expect(screen.getByText("44.0")).toBeInTheDocument();
    expect(screen.getByText("3:32:14")).toBeInTheDocument();
    expect(screen.getByText("−57:46")).toBeInTheDocument();
    expect(screen.getByText("前倒し")).toBeInTheDocument();
  });

  it("links to the goal page", () => {
    renderProgress();

    expect(screen.getByRole("link", { name: "目標ページ →" })).toHaveAttribute(
      "href",
      "/goal",
    );
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
