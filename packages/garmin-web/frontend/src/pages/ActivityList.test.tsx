import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "../test/utils";
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
  it("ActivityList still shows アクティビティ一覧 heading", async () => {
    stubFetch(FIXTURE_ACTIVITIES);

    render(
      <MemoryRouter>
        <ActivityList />
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "アクティビティ一覧",
      }),
    ).toBeInTheDocument();
  });

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

    // Distance and pace values are now rendered split from their units
    // (Issue #649): the numeric value and the unit live in separate elements.
    expect(screen.getByText("5.66")).toBeInTheDocument();
    expect(screen.getByText("6:26")).toBeInTheDocument();
    expect(screen.getByText("8.01")).toBeInTheDocument();
    expect(screen.getByText("6:02")).toBeInTheDocument();
  });

  it("renders distance with km unit suffix", async () => {
    stubFetch(FIXTURE_ACTIVITIES);

    render(
      <MemoryRouter>
        <ActivityList />
      </MemoryRouter>,
    );

    await screen.findByText("2025-10-09");

    // The numeric distance value and the "km" unit are distinct elements.
    const value = screen.getByText("5.66");
    const unit = screen.getAllByText("km")[0];
    expect(value).toBeInTheDocument();
    expect(unit).toBeInTheDocument();
    expect(value).not.toBe(unit);
    expect(value.textContent).toBe("5.66");
  });

  it("renders pace with /km unit suffix", async () => {
    stubFetch(FIXTURE_ACTIVITIES);

    render(
      <MemoryRouter>
        <ActivityList />
      </MemoryRouter>,
    );

    await screen.findByText("2025-10-09");

    // Pace value (without unit) and the "/km" unit are distinct elements.
    const value = screen.getByText("6:26");
    const unit = screen.getAllByText("/km")[0];
    expect(value).toBeInTheDocument();
    expect(unit).toBeInTheDocument();
    expect(value).not.toBe(unit);
  });

  it("renders heart rate with bpm unit suffix", async () => {
    stubFetch(FIXTURE_ACTIVITIES);

    render(
      <MemoryRouter>
        <ActivityList />
      </MemoryRouter>,
    );

    await screen.findByText("2025-10-09");

    // Heart-rate value and the "bpm" unit are distinct elements; one per row.
    const value = screen.getByText("144");
    const units = screen.getAllByText("bpm");
    expect(value).toBeInTheDocument();
    expect(units).toHaveLength(2);
    expect(value).not.toBe(units[0]);
  });

  it("metrics are visually separated (distinct elements)", async () => {
    stubFetch(FIXTURE_ACTIVITIES);

    render(
      <MemoryRouter>
        <ActivityList />
      </MemoryRouter>,
    );

    await screen.findByText("2025-10-09");

    // Distance, pace and heart-rate for a row are individually addressable
    // DOM nodes (not a single merged text run), enabling visual separation.
    const distance = screen.getByText("5.66");
    const pace = screen.getByText("6:26");
    const heartRate = screen.getByText("144");
    expect(distance).not.toBe(pace);
    expect(pace).not.toBe(heartRate);
    expect(distance).not.toBe(heartRate);
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
