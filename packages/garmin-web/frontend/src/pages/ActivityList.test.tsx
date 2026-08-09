import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "../test/utils";
import ActivityList, { presetToRange } from "./ActivityList";

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

/** 10 rows whose names exercise the text filter: 2 contain 閾値走, 1 contains ロング. */
const NAMED_ACTIVITIES = [
  "イージーラン",
  "閾値走 6km",
  "ロング走 18km",
  "リカバリージョグ",
  "朝の閾値走",
  "ペース走 10km",
  "イージーラン",
  "ビルドアップ走",
  "インターバル 400m",
  "ジョグ",
].map((activity_name, index) => ({
  activity_id: 9100000000 + index,
  activity_date: `2026-06-${String(index + 1).padStart(2, "0")}`,
  activity_name,
  total_distance_km: 10.0,
  total_time_seconds: 3600,
  avg_pace_seconds_per_km: 360.0,
  avg_heart_rate: 140,
}));

afterEach(() => {
  vi.unstubAllGlobals();
});

function stubFetch(activities: typeof FIXTURE_ACTIVITIES) {
  const fetchMock = vi.fn().mockImplementation(
    () =>
      new Response(JSON.stringify(activities), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** Exposes the current query string so URL sync is assertable. */
function LocationProbe() {
  const location = useLocation();
  return <span data-testid="location-search">{location.search}</span>;
}

function renderList(initialEntry = "/activities") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <ActivityList />
      <LocationProbe />
    </MemoryRouter>,
  );
}

function currentSearch(): URLSearchParams {
  return new URLSearchParams(
    screen.getByTestId("location-search").textContent ?? "",
  );
}

function searchBox(): HTMLInputElement {
  return screen.getByLabelText("アクティビティ名で検索") as HTMLInputElement;
}

function lastFetchUrl(fetchMock: ReturnType<typeof vi.fn>): string {
  return String(fetchMock.mock.calls[fetchMock.mock.calls.length - 1][0]);
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

describe("ActivityList filters (Issue #893)", () => {
  it("test_preset_to_range_counts_back_days", () => {
    const today = new Date(2026, 7, 9); // 2026-08-09, local time

    expect(presetToRange("4w", today)).toEqual({ from: "2026-07-12" });
    expect(presetToRange("3m", today)).toEqual({ from: "2026-05-09" });
    expect(presetToRange("1y", today)).toEqual({ from: "2025-08-09" });
    // "全期間" keeps the request unbounded.
    expect(presetToRange("all", today)).toEqual({});
  });

  it("test_range_preset_updates_url_and_query", async () => {
    const fetchMock = stubFetch(FIXTURE_ACTIVITIES);

    renderList();
    await screen.findByText("2025-10-09");

    // Default (no range param) keeps the historical unbounded request.
    expect(lastFetchUrl(fetchMock)).toBe("/api/activities");

    fireEvent.click(screen.getByRole("button", { name: "直近3ヶ月" }));

    await waitFor(() => {
      expect(currentSearch().get("range")).toBe("3m");
    });
    await waitFor(() => {
      expect(lastFetchUrl(fetchMock)).toBe(
        `/api/activities?from=${presetToRange("3m").from}`,
      );
    });
    expect(
      screen.getByRole("button", { name: "直近3ヶ月" }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("test_search_filters_by_name", async () => {
    stubFetch(NAMED_ACTIVITIES);

    renderList();
    await screen.findByText("閾値走 6km");
    expect(screen.getAllByRole("listitem")).toHaveLength(10);

    fireEvent.change(searchBox(), { target: { value: "閾値" } });

    await waitFor(() => {
      expect(screen.getAllByRole("listitem")).toHaveLength(2);
    });
    expect(screen.getByText("閾値走 6km")).toBeInTheDocument();
    expect(screen.getByText("朝の閾値走")).toBeInTheDocument();
    expect(screen.queryByText("ロング走 18km")).not.toBeInTheDocument();
    // The query is mirrored into the URL so the filtered view is shareable.
    expect(currentSearch().get("q")).toBe("閾値");
  });

  it("test_url_params_restore_state", async () => {
    const fetchMock = stubFetch(NAMED_ACTIVITIES);

    renderList("/activities?range=1y&q=ロング");
    await screen.findByText("ロング走 18km");

    // Preset restored from the URL...
    expect(screen.getByRole("button", { name: "直近1年" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "全期間" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    // ...and applied to the request.
    expect(lastFetchUrl(fetchMock)).toBe(
      `/api/activities?from=${presetToRange("1y").from}`,
    );

    // Text query restored into the box and already applied to the rows.
    expect(searchBox().value).toBe("ロング");
    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(1);
    expect(within(rows[0]).getByText("ロング走 18km")).toBeInTheDocument();
  });

  it("test_page_error_has_retry", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "db down" }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderList();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("読み込みに失敗しました");

    // A failed load is recoverable in place: the retry re-runs the request
    // instead of leaving a browser reload as the only way forward.
    const attempts = fetchMock.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "再試行" }));

    await waitFor(() => {
      expect(fetchMock.mock.calls.length).toBeGreaterThan(attempts);
    });
  });

  it("test_empty_filter_result_shows_empty_state", async () => {
    stubFetch(NAMED_ACTIVITIES);

    renderList();
    await screen.findByText("閾値走 6km");

    fireEvent.change(searchBox(), { target: { value: "存在しない名前" } });

    await screen.findByText("条件に一致するアクティビティがありません");
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);

    // The escape hatch clears every filter and brings the full list back.
    fireEvent.click(screen.getByRole("button", { name: "フィルタを解除" }));

    await waitFor(() => {
      expect(screen.getAllByRole("listitem")).toHaveLength(10);
    });
    expect(searchBox().value).toBe("");
    expect(currentSearch().get("q")).toBeNull();
  });
});
