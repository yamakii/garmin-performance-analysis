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

function stubFetch(activities: typeof FIXTURE_ACTIVITIES) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify(activities), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );
}

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

    // 2 activity row cards in the single 2025-10 month group
    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(2);

    // Month grouping heading now carries the month plus its run-count /
    // total-distance summary (Issue #214), so match on the month prefix.
    expect(
      screen.getByRole("heading", { level: 2, name: /2025-10/ }),
    ).toBeInTheDocument();
    // Month summary: 2 runs totalling 5.66 + 8.01 = 13.7 km
    expect(screen.getByText(/2本 ・ 合計 13\.7 km/)).toBeInTheDocument();

    // Distance and pace formatting
    expect(screen.getByText("5.66 km")).toBeInTheDocument();
    expect(screen.getByText("6:26/km")).toBeInTheDocument();
    expect(screen.getByText("8.01 km")).toBeInTheDocument();
    expect(screen.getByText("6:02/km")).toBeInTheDocument();
  });

  it("renders each row as an anchor with correct href", async () => {
    stubFetch(FIXTURE_ACTIVITIES);

    render(
      <MemoryRouter>
        <ActivityList />
      </MemoryRouter>,
    );

    await screen.findByText("2025-10-09");

    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute("href", "/activities/9000000001");
    expect(links[1]).toHaveAttribute("href", "/activities/9000000002");
  });

  it("row link is keyboard focusable", async () => {
    stubFetch(FIXTURE_ACTIVITIES);

    render(
      <MemoryRouter>
        <ActivityList />
      </MemoryRouter>,
    );

    await screen.findByText("2025-10-09");

    // Anchors with href are natively focusable; getByRole("link") only
    // matches elements exposed in the accessibility tree as links.
    const link = screen.getAllByRole("link")[0];
    link.focus();
    expect(link).toHaveFocus();
  });

  it("keeps month grouping and summary intact", async () => {
    stubFetch(FIXTURE_ACTIVITIES);

    render(
      <MemoryRouter>
        <ActivityList />
      </MemoryRouter>,
    );

    await screen.findByText("2025-10-09");

    // Month heading preserved
    expect(
      screen.getByRole("heading", { level: 2, name: /2025-10/ }),
    ).toBeInTheDocument();
    // Run-count / total-distance summary preserved (Issue #214)
    expect(screen.getByText(/2本 ・ 合計 13\.7 km/)).toBeInTheDocument();
    // Rows still rendered as list items
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });
});
