import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { ActivitySummary } from "../../types";
import RecentRuns, { RECENT_RUNS_LIMIT } from "./RecentRuns";

function makeActivity(i: number): ActivitySummary {
  return {
    activity_id: 1000 + i,
    activity_date: `2026-06-${String(10 + i).padStart(2, "0")}`,
    activity_name: `ラン ${i}`,
    total_distance_km: 6.5,
    total_time_seconds: 2700,
    avg_pace_seconds_per_km: 415,
    avg_heart_rate: 145,
  };
}

function renderRuns(activities: ActivitySummary[] | null) {
  return render(
    <MemoryRouter>
      <RecentRuns activities={activities} />
    </MemoryRouter>,
  );
}

describe("RecentRuns", () => {
  it("caps the list at five rows", () => {
    renderRuns(Array.from({ length: 7 }, (_, i) => makeActivity(i)));

    expect(screen.getAllByRole("listitem")).toHaveLength(RECENT_RUNS_LIMIT);
    expect(screen.getByText("ラン 0")).toBeInTheDocument();
    expect(screen.queryByText("ラン 5")).not.toBeInTheDocument();
  });

  it("links each run to its detail page and offers the full list", () => {
    renderRuns([makeActivity(1)]);

    expect(screen.getByRole("link", { name: /ラン 1/ })).toHaveAttribute(
      "href",
      "/activities/1001",
    );
    expect(screen.getByRole("link", { name: "すべて見る →" })).toHaveAttribute(
      "href",
      "/activities",
    );
  });

  it("shows an empty message when there are no activities", () => {
    renderRuns([]);

    expect(screen.getByText("アクティビティがありません")).toBeInTheDocument();
  });
});
