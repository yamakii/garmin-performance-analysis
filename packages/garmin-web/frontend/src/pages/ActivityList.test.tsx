import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import ActivityList from "./ActivityList";

const FIXTURE_ACTIVITIES = [
  {
    activity_id: 9000000001,
    activity_date: "2025-10-09",
    activity_name: "Morning Run",
    total_distance_km: 5.66,
    total_time_seconds: 2186,
    avg_pace_seconds_per_km: 386.0,
    avg_heart_rate: 144,
  },
  {
    activity_id: 9000000002,
    activity_date: "2025-10-07",
    activity_name: "Easy Run",
    total_distance_km: 8.01,
    total_time_seconds: 2900,
    avg_pace_seconds_per_km: 362.0,
    avg_heart_rate: 138,
  },
];

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ActivityList", () => {
  it("renders rows from API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(FIXTURE_ACTIVITIES), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    render(
      <MemoryRouter>
        <ActivityList />
      </MemoryRouter>,
    );

    // Wait for the data rows to appear
    expect(await screen.findByText("2025-10-09")).toBeInTheDocument();
    expect(screen.getByText("2025-10-07")).toBeInTheDocument();

    // 2 data rows + 1 header row in the single 2025-10 month group
    const rows = screen.getAllByRole("row");
    expect(rows).toHaveLength(3);

    // Month grouping heading
    expect(
      screen.getByRole("heading", { level: 2, name: "2025-10" }),
    ).toBeInTheDocument();

    // Distance and pace formatting
    expect(screen.getByText("5.66 km")).toBeInTheDocument();
    expect(screen.getByText("6:26/km")).toBeInTheDocument();
    expect(screen.getByText("8.01 km")).toBeInTheDocument();
    expect(screen.getByText("6:02/km")).toBeInTheDocument();
  });
});
