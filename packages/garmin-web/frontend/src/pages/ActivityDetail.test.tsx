import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "../test/utils";
import ActivityDetail from "./ActivityDetail";
import type {
  ActivityDetailResponse,
  SectionsResponse,
  TrackPoint,
} from "../types";

// echarts requires a real canvas; mock the modular wrapper out for jsdom.
vi.mock("../lib/echarts", () => ({
  echarts: {
    init: () => ({
      setOption: vi.fn(),
      resize: vi.fn(),
      dispose: vi.fn(),
      dispatchAction: vi.fn(),
      on: vi.fn(),
      getZr: () => ({ on: vi.fn() }),
    }),
  },
}));

const BASE_DETAIL: ActivityDetailResponse = {
  activity: {
    activity_id: 123,
    activity_date: "2025-10-09",
    activity_name: "Morning Run",
    total_distance_km: 5.66,
    total_time_seconds: 2186,
    avg_pace_seconds_per_km: 386,
    avg_heart_rate: 144,
  },
  splits: [
    {
      activity_id: 123,
      split_index: 1,
      distance: 1.0,
      duration_seconds: 386,
      pace_seconds_per_km: 386,
      heart_rate: 144,
      cadence: 168,
      power: 250,
    },
  ],
  form_efficiency: null,
  hr_zones: [],
  performance_trends: null,
  form_evaluations: null,
  vo2_max: null,
  lactate_threshold: null,
};

function stubFetch(opts: {
  detail: ActivityDetailResponse;
  sections: SectionsResponse;
  track: TrackPoint[];
}) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      let body: unknown;
      if (url.includes("/sections")) {
        body = opts.sections;
      } else if (url.includes("/time-series")) {
        body = { timestamps: [], metrics: {} };
      } else if (url.includes("/track")) {
        body = { points: opts.track };
      } else {
        body = opts.detail;
      }
      return Promise.resolve(
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }),
  );
}

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={["/activities/123"]}>
      <Routes>
        <Route path="/activities/:id" element={<ActivityDetail />} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ActivityDetail in-page nav", () => {
  it("omits コース from nav when track is absent", async () => {
    stubFetch({ detail: BASE_DETAIL, sections: {}, track: [] });
    renderDetail();

    const nav = await screen.findByRole("navigation", {
      name: "セクション目次",
    });
    expect(within(nav).queryByText("コース")).not.toBeInTheDocument();
  });

  it("includes スプリット in nav when splits exist", async () => {
    stubFetch({ detail: BASE_DETAIL, sections: {}, track: [] });
    renderDetail();

    const nav = await screen.findByRole("navigation", {
      name: "セクション目次",
    });
    const link = within(nav).getByRole("link", { name: "スプリット" });
    expect(link).toHaveAttribute("href", "#section-splits");

    // The corresponding splits section carries the matching anchor id.
    expect(document.getElementById("section-splits")).not.toBeNull();
  });
});

/**
 * Fetch stub with per-endpoint failure injection. `failTimeSeries` /
 * `failTrack` give the number of leading requests to that endpoint that
 * respond with HTTP 500 (subsequent requests succeed).
 */
function stubFetchWithErrors(opts: {
  timeSeries?: unknown;
  track?: TrackPoint[];
  failTimeSeries?: number;
  failTrack?: number;
}) {
  let timeSeriesFailures = opts.failTimeSeries ?? 0;
  let trackFailures = opts.failTrack ?? 0;
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    let body: unknown;
    let status = 200;
    if (url.includes("/sections")) {
      body = {};
    } else if (url.includes("/time-series")) {
      if (timeSeriesFailures > 0) {
        timeSeriesFailures -= 1;
        status = 500;
        body = { detail: "boom" };
      } else {
        body = opts.timeSeries ?? { timestamps: [], metrics: {} };
      }
    } else if (url.includes("/track")) {
      if (trackFailures > 0) {
        trackFailures -= 1;
        status = 500;
        body = { detail: "boom" };
      } else {
        body = { points: opts.track ?? [] };
      }
    } else {
      body = BASE_DETAIL;
    }
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      }),
    );
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function timeSeriesCalls(
  fetchMock: ReturnType<typeof stubFetchWithErrors>,
): number {
  return fetchMock.mock.calls.filter(([input]) =>
    String(input).includes("/time-series"),
  ).length;
}

describe("ActivityDetail panel errors", () => {
  it('time-series fetch 失敗で role="alert" を表示する', async () => {
    stubFetchWithErrors({ failTimeSeries: 1 });
    renderDetail();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Failed to fetch time series: 500");
    // The chart area shows the error instead of the empty-state placeholder.
    expect(
      screen.queryByText("表示する指標を選択してください"),
    ).not.toBeInTheDocument();
  });

  it("track fetch 失敗でマップ領域にエラーを表示する", async () => {
    stubFetchWithErrors({ failTrack: 1 });
    renderDetail();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Failed to fetch track: 500");
    // The alert renders inside the course section, replacing the map.
    const course = document.getElementById("section-course");
    expect(course).not.toBeNull();
    expect(within(course as HTMLElement).getByRole("alert")).toBe(alert);
  });

  it("再試行ボタンで再フェッチする", async () => {
    const fetchMock = stubFetchWithErrors({
      failTimeSeries: 1,
      timeSeries: { timestamps: [0, 1], metrics: { heart_rate: [140, 141] } },
    });
    renderDetail();

    const alert = await screen.findByRole("alert");
    fireEvent.click(within(alert).getByRole("button", { name: "再試行" }));

    await waitFor(() => {
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
    expect(timeSeriesCalls(fetchMock)).toBe(2);
    // Second fetch succeeded with data: the chart renders (no placeholder).
    expect(
      screen.queryByText("表示する指標を選択してください"),
    ).not.toBeInTheDocument();
  });

  it("空データはエラー扱いしない", async () => {
    stubFetchWithErrors({ track: [] });
    renderDetail();

    await screen.findByRole("navigation", { name: "セクション目次" });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    // Empty track (successful fetch) keeps the course section omitted.
    expect(document.getElementById("section-course")).toBeNull();
  });
});
