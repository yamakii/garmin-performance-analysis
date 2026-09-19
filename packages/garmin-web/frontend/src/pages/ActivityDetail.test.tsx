import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "../test/utils";
import ActivityDetail, { BarCell, sceneMarkers } from "./ActivityDetail";
import type {
  ActivityDetailResponse,
  ActivitySummary,
  RunFlowData,
  RunFlowSegment,
  RunFlowStep,
  RunMoment,
  RunReport,
  SectionsResponse,
  SplitAnomaliesResponse,
  SplitRow,
  TrackPoint,
} from "../types";

/** Splits shorter than this are lap-press fragments (the report's rule). */
const FRAGMENT_KM = 0.4;

function round3(value: number): number {
  return Math.round(value * 1000) / 1000;
}

/**
 * The `flow` block the report ships for a plain run: one segment per real
 * split, the lap presses counted as fragments, all of it one step.
 */
function flowFor(
  splits: SplitRow[],
  overrides: Partial<RunFlowData> = {},
): RunFlowData {
  const segments: RunFlowSegment[] = [];
  let km = 0;
  let seconds = 0;
  let fragmentCount = 0;
  let fragmentKm = 0;
  for (const split of splits) {
    const distance = split.distance ?? 0;
    const duration = split.duration_seconds ?? 0;
    const startKm = round3(km);
    const startS = seconds;
    km += distance;
    seconds += duration;
    if (distance >= FRAGMENT_KM) {
      segments.push({
        split_from: split.split_index,
        split_to: split.split_index,
        step_id: "s1",
        start_km: startKm,
        end_km: round3(km),
        start_s: startS,
        end_s: seconds,
        pace_s_per_km: split.pace_seconds_per_km,
        avg_hr: split.heart_rate,
        max_hr: split.heart_rate,
      });
    } else {
      fragmentCount += 1;
      fragmentKm += distance;
    }
  }
  return {
    axis: "distance",
    total_km: round3(km),
    total_s: seconds,
    segments,
    steps: [
      flowStep("s1", ["本編", "本編"], [1, splits.length], {
        distance_km: round3(km),
        duration_s: seconds,
      }),
    ],
    fragments: { count: fragmentCount, distance_km: round3(fragmentKm) },
    ...overrides,
  };
}

function flowStep(
  id: string,
  labels: [string, string],
  laps: [number, number],
  overrides: Partial<RunFlowStep> = {},
): RunFlowStep {
  return {
    id,
    role: "run",
    label_ja: labels[0],
    short_ja: labels[1],
    rep_no: null,
    split_from: laps[0],
    split_to: laps[1],
    start_km: 0,
    end_km: 0,
    start_s: 0,
    end_s: 0,
    distance_km: 0,
    duration_s: 0,
    pace_s_per_km: null,
    avg_hr: null,
    max_hr: null,
    is_long: true,
    ...overrides,
  };
}

/** A scene: the laps behind it, and where they were on the road. */
function momentOf(
  id: string,
  kind: string,
  laps: [number, number],
  overrides: Partial<RunMoment> = {},
): RunMoment {
  return {
    id,
    kind,
    unit: "km",
    label_ja: `${laps[0]}–${laps[1]} km`,
    step_id: "s1",
    rep_no: null,
    km_from: laps[0] - 1,
    km_to: laps[1],
    t_from_s: (laps[0] - 1) * 380,
    t_to_s: laps[1] * 380,
    split_from: laps[0],
    split_to: laps[1],
    facts: {},
    ...overrides,
  };
}

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
  hr_zones: [],
  performance_trends: null,
  form_evaluations: null,
  vo2_max: null,
  lactate_threshold: null,
};

/** A run with no prescription, no flagged signal and no scenes. */
const BASE_REPORT: RunReport = {
  activity_id: 123,
  activity_date: "2025-10-09",
  intensity_category: "easy",
  headline: { plan_label: "処方なし", flag_count: 0, flag_labels: [] },
  plan: null,
  signals: [],
  zones: [],
  moments: [],
  flow: flowFor(BASE_DETAIL.splits),
  recurrence: [],
  phases: [],
  conditions: {
    temp_c: null,
    humidity_pct: null,
    wind_mps: null,
    terrain: null,
    elevation_gain_m: null,
  },
  vs_previous: null,
  next_run_target: null,
  next_session: null,
};

const NO_SPLIT_ANOMALIES: SplitAnomaliesResponse = {
  activity_id: 123,
  total: 0,
  material: 0,
  splits: [],
};

/** `/api/activities` (the list) as opposed to `/api/activities/123`. */
const ACTIVITY_LIST_URL = /\/api\/activities(\?|$)/;

function stubFetch(opts: {
  detail: ActivityDetailResponse;
  sections: SectionsResponse;
  track: TrackPoint[];
  report?: RunReport;
  timeSeries?: unknown;
  splitAnomalies?: SplitAnomaliesResponse;
  splitAnomaliesStatus?: number;
  /** The list the "前回比" head reads the comparison run's distance from. */
  activities?: ActivitySummary[];
}) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      let body: unknown;
      let status = 200;
      if (url.includes("/sections/versions")) {
        body = [];
      } else if (url.includes("/sections")) {
        body = opts.sections;
      } else if (url.includes("/report")) {
        body = opts.report ?? BASE_REPORT;
      } else if (url.includes("/split-anomalies")) {
        body = opts.splitAnomalies ?? NO_SPLIT_ANOMALIES;
        status = opts.splitAnomaliesStatus ?? 200;
      } else if (url.includes("/time-series")) {
        body = opts.timeSeries ?? { timestamps: [], metrics: {} };
      } else if (url.includes("/track")) {
        body = { points: opts.track };
      } else if (ACTIVITY_LIST_URL.test(url)) {
        body = opts.activities ?? [];
      } else {
        body = opts.detail;
      }
      return Promise.resolve(
        new Response(JSON.stringify(body), {
          status,
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
  it("test_nav_follows_the_rendered_blocks", async () => {
    stubFetch({ detail: BASE_DETAIL, sections: {}, track: [] });
    renderDetail();

    // The nav is the page's own order of questions, and it lists only what
    // actually rendered: this run has no plan and no judged signal.
    const nav = await screen.findByRole("navigation", {
      name: "セクション目次",
    });
    expect(
      within(nav)
        .getAllByRole("link")
        .map((link) => link.textContent),
    ).toEqual(["コーチの総評", "ランの流れ", "記録"]);
    expect(document.getElementById("section-record")).not.toBeNull();
  });

  it("test_nav_lists_plan_and_signals_when_served", async () => {
    stubFetch({
      detail: BASE_DETAIL,
      sections: {},
      track: [],
      report: {
        ...BASE_REPORT,
        plan: {
          verdict: "✅",
          title: "イージー 6km",
          checks: [
            {
              axis: "intensity",
              target: "easy",
              actual: "easy",
              status: "on_plan",
              on_plan: true,
            },
          ],
          hr_ceiling: null,
        },
        signals: [
          {
            family: "form",
            metric: "gct",
            label_ja: "接地時間",
            unit: "ms",
            today: 260,
            expected: 256,
            normal_low: 248,
            normal_high: 262,
            z: 0.4,
            status: "within",
            adverse: false,
            streak: 0,
            reason: null,
          },
        ],
      },
    });
    renderDetail();

    const nav = await screen.findByRole("navigation", {
      name: "セクション目次",
    });
    const link = within(nav).getByRole("link", { name: "計画との照合" });
    expect(link).toHaveAttribute("href", "#section-plan");
    expect(
      within(nav).getByRole("link", { name: "いつもと比べて" }),
    ).toHaveAttribute("href", "#section-signals");
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
    if (url.includes("/sections/versions")) {
      body = [];
    } else if (url.includes("/sections")) {
      body = {};
    } else if (url.includes("/report")) {
      body = BASE_REPORT;
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
    } else if (ACTIVITY_LIST_URL.test(url)) {
      body = [];
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

describe("ActivityDetail back link", () => {
  it("test_activity_detail_back_link_targets_activities", async () => {
    stubFetch({ detail: BASE_DETAIL, sections: {}, track: [] });
    renderDetail();

    // The report is reached from the activity list, so the back link must
    // return there rather than to the home dashboard.
    const back = await screen.findByRole("link", {
      name: "← 一覧へ",
    });
    expect(back).toHaveAttribute("href", "/activities");
  });
});

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
    // The alert renders inside the course block, replacing the map.
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
    // Empty track (successful fetch) keeps the course block omitted.
    expect(document.getElementById("section-course")).toBeNull();
  });
});

// --- Header (#1252) ---

const LONG_RUN_DETAIL: ActivityDetailResponse = {
  ...BASE_DETAIL,
  activity: {
    activity_id: 123,
    activity_date: "2025-10-09",
    activity_name: "Morning Run",
    total_distance_km: 22.14,
    total_time_seconds: 7705,
    avg_pace_seconds_per_km: 348,
    avg_heart_rate: 148,
  },
  // Garmin %LTHR zones on the configured LTHR 170: zone 5 opens at 100% of it.
  hr_zones: [
    { zone_number: 1, zone_low_boundary: 110, zone_high_boundary: 135 },
    { zone_number: 2, zone_low_boundary: 136, zone_high_boundary: 150 },
    { zone_number: 3, zone_low_boundary: 151, zone_high_boundary: 161 },
    { zone_number: 4, zone_low_boundary: 162, zone_high_boundary: 169 },
    { zone_number: 5, zone_low_boundary: 170, zone_high_boundary: 220 },
  ].map((zone) => ({
    ...zone,
    activity_id: 123,
    time_in_zone_seconds: 0,
    zone_percentage: 0,
  })),
  vo2_max: { value: 50.1, date: "2025-10-09" },
  // Garmin's auto-detected estimate, which disagrees with the configured 170.
  lactate_threshold: {
    heart_rate: 164,
    speed_mps: 3.0278,
    date_hr: "2026-07-11",
  },
};

const LONG_RUN_REPORT: RunReport = {
  ...BASE_REPORT,
  headline: { plan_label: "処方どおり", flag_count: 0, flag_labels: [] },
  plan: {
    verdict: "✅",
    title: "ロング 22km",
    checks: [
      {
        axis: "intensity",
        target: "long_run",
        actual: "long_run",
        status: "on_plan",
        on_plan: true,
      },
      {
        axis: "hr_ceiling",
        target: "≦150bpm",
        actual: "148bpm",
        status: "on_plan",
        on_plan: true,
      },
    ],
    hr_ceiling: { bpm: 150, seconds_over: 321, pct_over: 12.4 },
  },
  vs_previous: {
    pace_s_per_km: { current: 348, previous: 358, delta: -10 },
    avg_hr: { current: 148, previous: 151, delta: -3 },
    gct_ms: { current: 262, previous: 258, delta: 4 },
    cadence_spm: { current: 172, previous: 174, delta: -2 },
    days_ago: 7,
  },
};

/** A legacy summary section whose prose never states the ceiling. */
const SUMMARY_SECTIONS: SectionsResponse = {
  summary: {
    data: {
      star_rating: "★★★★☆ 4.3/5.0",
      summary:
        "処方どおりの22kmを走り切れた一本でした。後半も心拍は上限内に収まっています。",
      next_action: "次回は最初の3kmを7:00/kmより遅く入りましょう。",
    },
    parse_error: false,
    raw: null,
  },
};

describe("ActivityDetail header", () => {
  it("test_header_shows_verdict_line_without_stars", async () => {
    stubFetch({
      detail: LONG_RUN_DETAIL,
      sections: SUMMARY_SECTIONS,
      track: [],
      report: LONG_RUN_REPORT,
    });
    renderDetail();

    // The run names the page; how the day's plan went is the line under it.
    const heading = await screen.findByRole("heading", {
      level: 1,
      name: /Morning Run/,
    });
    expect(heading).toBeInTheDocument();
    expect(screen.getByText("処方どおり")).toBeInTheDocument();
    expect(screen.getByText(/特記なし/)).toBeInTheDocument();

    // A run is not a score: no stars anywhere on the default page (#1247).
    expect(screen.queryByLabelText(/^評価/)).not.toBeInTheDocument();

    // The four numbers the page is opened for follow as one row.
    const kpis = screen.getByRole("region", { name: "このランの数値" });
    for (const value of ["22.14", "2:08:25", "5:48", "148"]) {
      expect(within(kpis).getByText(value)).toBeInTheDocument();
    }

    // The deltas against the last comparable run are one mono line, not chips.
    expect(
      screen.getByText(
        "前回比（7日前）: ペース -10秒/km · HR -3bpm · GCT +4ms · ケイデンス -2spm",
      ),
    ).toBeInTheDocument();
  });

  it("test_header_flag_is_warn_toned", async () => {
    stubFetch({
      detail: LONG_RUN_DETAIL,
      sections: {},
      track: [],
      report: {
        ...LONG_RUN_REPORT,
        headline: {
          plan_label: "処方どおり",
          flag_count: 1,
          flag_labels: ["接地時間が長め"],
        },
      },
    });
    renderDetail();

    // The plan label stays ink; only the exception takes colour.
    const flags = await screen.findByText("注意 1件: 接地時間が長め");
    expect(flags).toHaveClass("text-status-warn");
    expect(screen.queryByText(/特記なし/)).not.toBeInTheDocument();
  });

  it("test_hr_note_comes_from_report", async () => {
    stubFetch({
      detail: LONG_RUN_DETAIL,
      sections: SUMMARY_SECTIONS,
      track: [],
      report: LONG_RUN_REPORT,
      timeSeries: {
        timestamps: [0, 1, 2, 3],
        metrics: { heart_rate: [140, 151, 152, 149] },
      },
    });
    renderDetail();

    // The cap and the time above it are served by the report, which reads the
    // seconds off the HR zones — no regex over the analyst's prose (which
    // never mentions 150 here) and no scan of the time series (#1252).
    expect(await screen.findByText("上限 150 · 超過 5:21")).toBeInTheDocument();
    const summaryProse = SUMMARY_SECTIONS.summary.data?.summary as string;
    expect(summaryProse).not.toContain("150");
  });

  it("test_activity_kpi_row_uses_large_values", async () => {
    stubFetch({
      detail: {
        ...LONG_RUN_DETAIL,
        activity: { ...LONG_RUN_DETAIL.activity, total_distance_km: 25.07 },
      },
      sections: SUMMARY_SECTIONS,
      track: [],
      report: LONG_RUN_REPORT,
    });
    renderDetail();

    // These four are what the page is opened for, so they take the KPI size
    // the brief reserves for a page's own numbers (#1153).
    expect(await screen.findByText("25.07")).toHaveClass("text-[40px]");
  });

  it("test_activity_title_is_36px", async () => {
    stubFetch({
      detail: LONG_RUN_DETAIL,
      sections: SUMMARY_SECTIONS,
      track: [],
      report: LONG_RUN_REPORT,
    });
    renderDetail();

    // The run's name is a heading, not a verdict: it stays at 36px instead of
    // growing into the home page's 40px on a wide screen (#1153).
    const heading = await screen.findByRole("heading", {
      level: 1,
      name: /Morning Run/,
    });
    expect(heading.className).toContain("text-[36px]");
    expect(heading.className).not.toContain("md:text-[40px]");
  });

  it("test_verdict_line_is_smaller_than_title", async () => {
    stubFetch({
      detail: LONG_RUN_DETAIL,
      sections: SUMMARY_SECTIONS,
      track: [],
      report: LONG_RUN_REPORT,
    });
    renderDetail();

    // The run names the page and stays its largest text; the verdict reads at
    // 20px under it. Shipped the other way round, the verdict (40px) shouted
    // over the title (36px) it was judging (#1270).
    const heading = await screen.findByRole("heading", {
      level: 1,
      name: /Morning Run/,
    });
    const verdict = screen.getByText("処方どおり").parentElement as HTMLElement;
    expect(heading.className).toContain("text-[36px]");
    expect(verdict.className).toContain("text-xl");
    expect(verdict.className).not.toMatch(/text-\[(36|40)px\]/);
  });

  it("test_verdict_remainder_is_regular_weight", async () => {
    stubFetch({
      detail: LONG_RUN_DETAIL,
      sections: SUMMARY_SECTIONS,
      track: [],
      report: LONG_RUN_REPORT,
    });
    renderDetail();

    // Only the judgement is bold; what it amounts to is said in plain weight.
    const rest = await screen.findByText(/特記なし/);
    expect(rest).toHaveClass("font-normal", "text-ink-soft");
  });

  it("test_meta_line_includes_start_time", async () => {
    const dated = {
      ...LONG_RUN_DETAIL,
      activity: {
        ...LONG_RUN_DETAIL.activity,
        activity_date: "2026-09-13",
        start_time_local: "2026-09-13 13:45:19",
      },
    };
    stubFetch({
      detail: dated,
      sections: SUMMARY_SECTIONS,
      track: [],
      report: LONG_RUN_REPORT,
    });
    const { unmount } = renderDetail();

    // A 13:45 start and a 06:00 start are different runs in the same day's
    // heat, so the hour sits next to the date (#1153).
    const meta = await screen.findByText(/^2026-09-13 SUN · 13:45 · /);
    expect(meta).toHaveTextContent("処方「ロング 22km」");
    unmount();

    // A run with no recorded start omits the time rather than padding it.
    stubFetch({
      detail: {
        ...dated,
        activity: { ...dated.activity, start_time_local: null },
      },
      sections: SUMMARY_SECTIONS,
      track: [],
      report: LONG_RUN_REPORT,
    });
    renderDetail();

    expect(
      await screen.findByText(/^2026-09-13 SUN · 処方「ロング 22km」/),
    ).toBeInTheDocument();
  });

  it("test_vs_previous_line_with_distance", async () => {
    const report: RunReport = {
      ...LONG_RUN_REPORT,
      vs_previous: {
        pace_s_per_km: { current: 423, previous: 348, delta: 75.1 },
        days_ago: 5,
        previous_activity_id: 456,
      },
    };
    const previous: ActivitySummary = {
      activity_id: 456,
      activity_date: "2025-10-04",
      activity_name: "Evening Run",
      total_distance_km: 5.07,
      total_time_seconds: 1958,
      avg_pace_seconds_per_km: 348,
      avg_heart_rate: 151,
      plan_label: null,
      flag_labels: [],
      story_lead: null,
    };
    stubFetch({
      detail: LONG_RUN_DETAIL,
      sections: {},
      track: [],
      report,
      activities: [previous],
    });
    const { unmount } = renderDetail();

    // The same pace delta means different things against a 5km and a 22km, so
    // the comparison run is named by its distance as well as its age (#1153).
    expect(
      await screen.findByText("前回比（5日前・5.07km）: ペース +75.1秒/km"),
    ).toBeInTheDocument();
    unmount();

    // A comparison run outside the list keeps the line, minus the distance.
    stubFetch({
      detail: LONG_RUN_DETAIL,
      sections: {},
      track: [],
      report,
      activities: [],
    });
    renderDetail();

    expect(
      await screen.findByText("前回比（5日前）: ペース +75.1秒/km"),
    ).toBeInTheDocument();
  });

  it("test_activity_detail_header_shows_configured_threshold", async () => {
    stubFetch({
      detail: LONG_RUN_DETAIL,
      sections: SUMMARY_SECTIONS,
      track: [],
      report: LONG_RUN_REPORT,
    });
    renderDetail();

    // The meta line carries the date, the prescription and the physiology
    // numbers the run is read against.
    const meta = await screen.findByText(/2025-10-09 THU/);
    expect(meta).toHaveTextContent("処方「ロング 22km」");
    expect(meta).toHaveTextContent("VO2max 50.1");
    // The threshold shown is the configured one (zone 5 lower bound), never
    // Garmin's auto-detected estimate, which disagrees with it (#1098).
    expect(meta).toHaveTextContent("乳酸閾値（設定値）170 bpm");
    expect(meta).not.toHaveTextContent("164");
    expect(screen.queryByText(/推定/)).not.toBeInTheDocument();
  });

  it("test_activity_detail_header_degrades_without_physiology", async () => {
    stubFetch({
      detail: {
        ...LONG_RUN_DETAIL,
        activity: { ...LONG_RUN_DETAIL.activity, activity_name: null },
        // No zone 5 -> no configured threshold to show.
        hr_zones: LONG_RUN_DETAIL.hr_zones.slice(0, 4),
        vo2_max: null,
      },
      sections: {},
      track: [],
    });
    renderDetail();

    expect(
      await screen.findByRole("heading", { level: 1, name: "アクティビティ" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/乳酸閾値/)).not.toBeInTheDocument();
    expect(screen.queryByText(/VO2max/)).not.toBeInTheDocument();
    // Without an analysis there is no review to show, and the page says so
    // instead of leaving a hole.
    expect(
      screen.getByText("このランの総評はまだありません"),
    ).toBeInTheDocument();
  });
});

describe("ActivityDetail metric toggles", () => {
  it("test_activity_detail_default_toggles", async () => {
    stubFetch({ detail: BASE_DETAIL, sections: {}, track: [] });
    renderDetail();

    await screen.findByRole("navigation", { name: "セクション目次" });
    // The splits table names columns after the same metrics, so the toggles
    // are read inside their own block.
    const chart = within(
      document.getElementById("section-timeseries") as HTMLElement,
    );

    // Heart rate and pace are on by default and read as filled chips.
    expect(chart.getByText("心拍数")).toHaveClass("bg-ink");
    expect(chart.getByText("ペース")).toHaveClass("bg-ink");
    // The other primary toggles are offered, but off.
    expect(chart.getByText("ケイデンス")).not.toHaveClass("bg-ink");
    expect(chart.getByText("接地時間")).not.toHaveClass("bg-ink");

    // The four secondary series stay behind a "+" link until asked for.
    for (const label of ["パワー", "高度", "上下動", "上下動比"]) {
      expect(chart.queryByText(label)).not.toBeInTheDocument();
    }
    fireEvent.click(
      chart.getByRole("button", {
        name: "+ パワー / 高度 / 上下動 / 上下動比",
      }),
    );
    for (const label of ["パワー", "高度", "上下動", "上下動比"]) {
      expect(chart.getByText(label)).toBeInTheDocument();
    }
  });
});

/** Split row helper: 1 km unless `distance` says otherwise. */
function splitRow(
  split_index: number,
  pace_seconds_per_km: number,
  heart_rate: number,
  distance = 1.0,
) {
  return {
    activity_id: 123,
    split_index,
    distance,
    duration_seconds: Math.round(pace_seconds_per_km * distance),
    pace_seconds_per_km,
    heart_rate,
    cadence: 168,
    power: 250,
  };
}

/** The inline bar of a cell (aria-hidden span), or null when it has none. */
function barOf(cell: HTMLElement): HTMLElement | null {
  return cell.querySelector<HTMLElement>('span[aria-hidden="true"]');
}

function barWidth(cell: HTMLElement): number {
  const bar = barOf(cell);
  expect(bar).not.toBeNull();
  return Number.parseFloat((bar as HTMLElement).style.width);
}

async function renderSplits(
  splits: ReturnType<typeof splitRow>[],
  sections: SectionsResponse = {},
  anomalies?: { response?: SplitAnomaliesResponse; status?: number },
  report: RunReport = BASE_REPORT,
  // The record block lists what the report drew, so the flow has to describe
  // the splits under test unless a case deliberately overrides it (#1269).
  flow: RunFlowData | null = flowFor(splits),
) {
  stubFetch({
    detail: { ...BASE_DETAIL, splits },
    sections,
    track: [],
    report: { ...report, flow },
    splitAnomalies: anomalies?.response,
    splitAnomaliesStatus: anomalies?.status,
  });
  renderDetail();
  await screen.findByRole("navigation", { name: "セクション目次" });
  // Row 0 of each table is the header; the body rows follow in split order.
  return screen
    .getAllByRole("table")
    .flatMap((table) => within(table).getAllByRole("row").slice(1));
}

describe("ActivityDetail splits table bars", () => {
  it("test_splits_table_scrollable_and_scoped", async () => {
    await renderSplits([splitRow(1, 390, 138), splitRow(2, 360, 142)]);

    // Six numeric columns do not fit a ~360px screen, so the table scrolls
    // inside its own wrapper instead of pushing the page sideways (#912).
    const table = screen.getAllByRole("table")[0];
    expect(table.parentElement).toHaveClass("overflow-x-auto");

    // Every header cell declares the column it labels, so a screen reader can
    // announce "ペース 6:30/km" per cell instead of a bare number.
    const headers = within(table).getAllByRole("columnheader");
    expect(headers).toHaveLength(6);
    for (const header of headers) {
      expect(header).toHaveAttribute("scope", "col");
    }
  });

  it("test_split_table_inline_bars", async () => {
    // 5:30 (fastest) .. 6:30 (slowest), HR rising with the pace.
    const rows = await renderSplits([
      splitRow(1, 390, 138),
      splitRow(2, 360, 142),
      splitRow(3, 345, 146),
      splitRow(4, 330, 150),
      splitRow(5, 375, 144),
    ]);
    expect(rows).toHaveLength(5);

    const paceCell = (row: HTMLElement) =>
      within(row).getAllByRole("cell")[2];
    const hrCell = (row: HTMLElement) => within(row).getAllByRole("cell")[3];

    // Every pace cell is backed by a bar.
    for (const row of rows) {
      expect(barOf(paceCell(row))).not.toBeNull();
      expect(barOf(hrCell(row))).not.toBeNull();
    }

    // Pace is inverted: the fastest split (5:30, row 4) has the longest bar
    // and the slowest (6:30, row 1) the shortest.
    const paceWidths = rows.map((row) => barWidth(paceCell(row)));
    expect(Math.max(...paceWidths)).toBe(paceWidths[3]);
    expect(Math.min(...paceWidths)).toBe(paceWidths[0]);

    // Heart rate is not inverted: the highest HR gets the longest bar.
    const hrWidths = rows.map((row) => barWidth(hrCell(row)));
    expect(Math.max(...hrWidths)).toBe(hrWidths[3]);
    expect(Math.min(...hrWidths)).toBe(hrWidths[0]);
  });

  it("test_split_table_fragment_no_bar", async () => {
    // A 10 m manual-lap fragment at an artifact pace (4:04/km) is mixed into
    // the same 5:30-6:30 field as above. Without a report to say which splits
    // were drawn (an old or failed report), every row is listed — and the
    // fragment still draws no bar.
    const rows = await renderSplits(
      [
        splitRow(1, 390, 138),
        splitRow(2, 360, 142),
        splitRow(3, 345, 146),
        splitRow(4, 330, 150),
        splitRow(5, 375, 144),
        splitRow(6, 244, 120, 0.01),
      ],
      {},
      undefined,
      BASE_REPORT,
      null,
    );
    expect(rows).toHaveLength(6);

    // The fragment row shows its numbers but draws no bar at all.
    const fragmentCells = within(rows[5]).getAllByRole("cell");
    expect(fragmentCells[2]).toHaveTextContent("4:04/km");
    expect(barOf(fragmentCells[2])).toBeNull();
    expect(barOf(fragmentCells[3])).toBeNull();

    // The fragment is excluded from the normalization, so the real rows are
    // still spread over 330-390 s/km (12% floor .. 100%) rather than being
    // squashed toward the artifact's 244 s/km.
    const widths = rows
      .slice(0, 5)
      .map((row) => barWidth(within(row).getAllByRole("cell")[2]));
    expect(widths).toEqual([12, 56, 78, 100, 34]);
  });

  it("test_split_bar_positioned_in_inner_box", () => {
    render(
      <table>
        <tbody>
          <tr>
            <BarCell widthPct={100} color="#1f6f6b" flagged={false}>
              6:30/km
            </BarCell>
          </tr>
        </tbody>
      </table>,
    );

    const cell = screen.getByRole("cell");
    const bar = barOf(cell) as HTMLElement;
    expect(bar).not.toBeNull();

    // A full-width bar must stop at the cell's padding, so the box it is
    // positioned against is the inner div, not the padded cell itself (#1145):
    // otherwise the pace and HR bars touch and read as one band.
    const positioned = bar.parentElement as HTMLElement;
    expect(positioned.tagName).toBe("DIV");
    expect(positioned).toHaveClass("relative");
    expect(cell).not.toHaveClass("relative");
    expect(cell).toHaveClass("px-2");
    expect(barWidth(cell)).toBe(100);
  });
});

describe("ActivityDetail splits table reading aids", () => {
  /** 23 one-kilometre splits, as a long run produces. */
  const LONG_SPLITS = Array.from({ length: 23 }, (_, index) =>
    splitRow(index + 1, 380 + (index % 5), 140 + (index % 6)),
  );

  it("test_flagged_split_rows_highlighted", async () => {
    const rows = await renderSplits(
      LONG_SPLITS,
      {},
      {
        response: {
          activity_id: 123,
          total: 2,
          material: 1,
          splits: [
            {
              split_index: 20,
              anomalies: 2,
              material: 1,
              severity_high: 0,
              max_z: 3.9,
              metrics: ["gct"],
            },
          ],
        },
      },
    );

    // The note lands with the response, so waiting for it settles the query.
    expect(await screen.findByText("注意 1本")).toBeInTheDocument();

    // The kilometre the detector actually flagged is tinted, so the table can
    // be scanned for exceptions instead of read end to end (#1132).
    const flagged = rows.find(
      (row) => within(row).getAllByRole("cell")[0].textContent === "20",
    );
    expect(flagged).toHaveClass("bg-warn-tint");
    // Hovering names the metric that moved rather than just "something here".
    expect(flagged).toHaveAttribute("title", expect.stringContaining("gct"));

    // Its neighbours stay plain.
    const plain = rows.find(
      (row) => within(row).getAllByRole("cell")[0].textContent === "21",
    );
    expect(plain).not.toHaveClass("bg-warn-tint");
    expect(plain).not.toHaveAttribute("title");
  });

  it("test_flagged_splits_degrade_on_error", async () => {
    const rows = await renderSplits(LONG_SPLITS, {}, { status: 500 });

    // The lookup really was attempted (and rejected) before we assert absence.
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([input]) =>
          String(input).includes("/split-anomalies"),
        ),
      ).toBe(true),
    );

    // The highlight is an aid, not the content: a failed lookup leaves the
    // table plain and stays silent instead of raising an error panel.
    for (const row of rows) {
      expect(row).not.toHaveClass("bg-warn-tint");
    }
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText(/注意 \d+本/)).not.toBeInTheDocument();

    // The rest of the page still renders.
    expect(screen.getByRole("navigation", { name: "セクション目次" }))
      .toBeInTheDocument();
    expect(rows.length).toBeGreaterThan(0);
  });

  it("test_record_block_disclosure_counts_listed_rows", async () => {
    const splits = [
      ...Array.from({ length: 25 }, (_, index) =>
        splitRow(index + 1, 380 + (index % 5), 140 + (index % 6)),
      ),
      splitRow(26, 244, 120, 0.03),
    ];
    await renderSplits(splits);

    // The first ten kilometres are visible; the label of the fold counts the
    // rows it actually holds, in listed rows — the 26th lap is a fragment and
    // is not one of them, and "26 km" would be wrong twice over (#1269).
    const preview = screen.getAllByRole("table")[0];
    expect(within(preview).getAllByRole("row").slice(1)).toHaveLength(10);
    const trigger = screen.getByText("残り 15 スプリット（11〜25 本目）を表示");
    expect(trigger.closest("details")?.hasAttribute("open")).toBe(false);
  });

  it("test_record_block_lists_only_drawn_splits_for_steady_runs", async () => {
    const rows = await renderSplits([
      splitRow(1, 390, 138),
      splitRow(2, 360, 142),
      splitRow(3, 345, 146),
      splitRow(4, 330, 150),
      splitRow(5, 375, 144),
      splitRow(6, 244, 120, 0.03),
      splitRow(7, 250, 118, 0.03),
    ]);

    // The table is the chart's own list of splits: a lap press whose pace is
    // a measurement artifact gets no row, and one mono line says so rather
    // than leaving the reader to find the missing lap numbers.
    expect(rows).toHaveLength(5);
    expect(
      screen.getByText(
        "端数スプリット 2 本（計 0.06 km）は、図と表から除いています。距離の位置には数えています。",
      ),
    ).toBeInTheDocument();
  });

  it("test_record_block_shows_steps_table_for_multi_step_runs", async () => {
    // 4/20: two threshold reps, the first recorded as 1.0 + 0.11 km.
    const splits = [
      splitRow(1, 420, 120),
      splitRow(2, 420, 128),
      splitRow(3, 324, 168),
      splitRow(4, 324, 172, 0.11),
      splitRow(5, 667, 150, 0.18),
      splitRow(6, 324, 170),
      splitRow(7, 324, 173, 0.11),
      splitRow(8, 420, 135),
      splitRow(9, 420, 128),
    ];
    const steps: RunFlowStep[] = [
      flowStep("s1", ["ウォームアップ", "アップ"], [1, 2], {
        distance_km: 2,
        duration_s: 840,
        pace_s_per_km: 420,
        avg_hr: 124,
        max_hr: 132,
      }),
      flowStep("s2", ["1本目", "1本目"], [3, 4], {
        distance_km: 1.11,
        duration_s: 360,
        pace_s_per_km: 324,
        avg_hr: 170,
        max_hr: 175,
      }),
      flowStep("s3", ["レスト1", "R"], [5, 5], {
        distance_km: 0.18,
        duration_s: 120,
        pace_s_per_km: 667,
        avg_hr: 150,
        max_hr: 168,
      }),
      flowStep("s4", ["2本目", "2本目"], [6, 7], {
        distance_km: 1.11,
        duration_s: 360,
        pace_s_per_km: 324,
        avg_hr: 171,
        max_hr: 176,
      }),
      flowStep("s5", ["クールダウン", "ダウン"], [8, 9], {
        distance_km: 2,
        duration_s: 840,
        pace_s_per_km: 420,
        avg_hr: 131,
        max_hr: 140,
      }),
    ];
    await renderSplits(splits, {}, undefined, BASE_REPORT, {
      ...flowFor(splits),
      axis: "time",
      steps,
    });

    // The reader asks "how did the reps go", not "what did lap 6 do": the
    // steps are the record, and the raw laps sit behind a disclosure (#1269).
    const table = screen.getAllByRole("table")[0];
    const stepRows = within(table).getAllByRole("row").slice(1);
    expect(
      stepRows.map((row) => within(row).getAllByRole("cell")[0].textContent),
    ).toEqual(["ウォームアップ", "1本目", "レスト1", "2本目", "クールダウン"]);
    const repCells = within(stepRows[1]).getAllByRole("cell");
    expect(repCells[1]).toHaveTextContent("1.11");
    expect(repCells[2]).toHaveTextContent("6:00");

    const trigger = screen.getByText("記録されたスプリット 9 本を表示");
    expect(trigger.closest("details")?.hasAttribute("open")).toBe(false);
    const raw = screen.getAllByRole("table")[1];
    expect(
      within(raw).getByRole("columnheader", { name: "区間" }),
    ).toBeInTheDocument();
    expect(within(raw).getAllByRole("row").slice(1)).toHaveLength(9);
  });

  it("keeps a short run in one table", async () => {
    await renderSplits(LONG_SPLITS.slice(0, 8));

    expect(screen.getAllByRole("table")).toHaveLength(1);
    expect(screen.queryByText(/残り .+ スプリット/)).not.toBeInTheDocument();
  });

  it("test_splits_scene_column_only_with_two_scenes", async () => {
    const splits = LONG_SPLITS.slice(0, 5);
    const oneScene: RunReport = {
      ...BASE_REPORT,
      moments: [momentOf("m1", "steady", [1, 5])],
    };
    await renderSplits(splits, {}, undefined, oneScene);
    // A column repeating the same marker on every row costs width and says
    // nothing, so a one-scene run has none.
    expect(
      within(screen.getAllByRole("table")[0]).queryByRole("columnheader", {
        name: "場面",
      }),
    ).not.toBeInTheDocument();

    cleanup();
    vi.unstubAllGlobals();
    const rows = await renderSplits(splits, {}, undefined, {
      ...BASE_REPORT,
      moments: [
        momentOf("m1", "start", [1, 1]),
        momentOf("m2", "climb", [2, 2]),
        momentOf("m3", "surge", [4, 4]),
        momentOf("m4", "strong_finish", [5, 5]),
      ],
    });

    const table = screen.getAllByRole("table")[0];
    expect(
      within(table).getByRole("columnheader", { name: "場面" }),
    ).toBeInTheDocument();
    // The marker on a row is the number the flow list gave its scene.
    expect(within(rows[1]).getAllByRole("cell")[6]).toHaveTextContent("②");
    expect(within(rows[2]).getAllByRole("cell")[6]).toHaveTextContent("");
  });

  it("test_splits_scene_column_matches_lap_numbers", async () => {
    const splits = LONG_SPLITS.slice(0, 6);
    const rows = await renderSplits(splits, {}, undefined, {
      ...BASE_REPORT,
      moments: [
        momentOf("m1", "start", [1, 1]),
        // Laps 4 and 5 — not "kilometre 4 to 5", which is lap 5 alone on a
        // run with a manual lap press (#1268).
        momentOf("m2", "surge", [4, 5]),
      ],
    });

    const marker = (row: HTMLElement) =>
      within(row).getAllByRole("cell")[6].textContent;
    expect(rows.map(marker)).toEqual(["①", "", "", "②", "②", ""]);
  });
});

describe("sceneMarkers", () => {
  it("test_scene_markers_cover_the_laps_of_a_scene", () => {
    const markers = sceneMarkers([
      momentOf("m1", "climb", [2, 4]),
      momentOf("m2", "fade", [7, 7]),
    ]);

    expect([...markers.entries()]).toEqual([
      [2, "①"],
      [3, "①"],
      [4, "①"],
      [7, "②"],
    ]);
  });

  it("gives a walk break the laps it actually walked", () => {
    // Three stops, not one slab from the first to the last (#1269).
    const markers = sceneMarkers([
      momentOf("m1", "walk_break", [14, 22], {
        facts: { split_list: [14, 20, 22] },
      }),
    ]);

    expect([...markers.keys()]).toEqual([14, 20, 22]);
  });
});

describe("ActivityDetail legacy analysis", () => {
  it("test_legacy_sections_behind_disclosure", async () => {
    stubFetch({
      detail: LONG_RUN_DETAIL,
      sections: {
        ...SUMMARY_SECTIONS,
        efficiency: {
          data: { evaluation: "接地時間は安定していました。" },
          parse_error: false,
          raw: null,
        },
        phase: {
          data: { warmup: "入りは丁寧でした。" },
          parse_error: false,
          raw: null,
        },
      },
      track: [],
      report: LONG_RUN_REPORT,
    });
    renderDetail();

    // The five graded sections are kept and readable, but they are no longer
    // what the page says: they sit folded away under one line (#1247).
    const trigger = await screen.findByText("以前の分析（旧形式）");
    const details = trigger.closest("details");
    expect(details?.hasAttribute("open")).toBe(false);
    expect(
      within(details as HTMLElement).getAllByText("接地時間は安定していました。")
        .length,
    ).toBeGreaterThan(0);
    expect(
      within(details as HTMLElement).getByText("入りは丁寧でした。"),
    ).toBeInTheDocument();
  });

  it("omits the disclosure when nothing legacy was saved", async () => {
    stubFetch({
      detail: LONG_RUN_DETAIL,
      sections: {
        run_note: {
          data: {
            story: "ロング前日の一本でした。狙いどおりに収まっています。",
            good_points: [
              { text: "心拍が終始ゾーン2でした。", evidence: "signals.hr_drift" },
            ],
            growth_points: [],
            next_challenge: "次回も150bpmを超えないように入りましょう。",
            timeline: [{ moment_id: "m1", text: "抑えて入れました。" }],
            notes: [],
          },
          parse_error: false,
          raw: null,
        },
      },
      track: [],
      report: LONG_RUN_REPORT,
    });
    renderDetail();

    expect(
      await screen.findByText("ロング前日の一本でした。狙いどおりに収まっています。"),
    ).toBeInTheDocument();
    expect(screen.queryByText("以前の分析（旧形式）")).not.toBeInTheDocument();
  });
});

describe("ActivityDetail version selector", () => {
  const OLD_STAMP = "2025-10-09 12:00:00";
  const NEW_STAMP = "2025-10-09 13:00:00";

  /** Stub returning 2 analysis batches; sections vary by the created_at pin. */
  function stubVersionedFetch() {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      let body: unknown;
      if (url.includes("/sections/versions")) {
        body = [
          { run_id: 2, created_at: NEW_STAMP, section_types: ["run_note"] },
          {
            run_id: 1,
            created_at: OLD_STAMP,
            section_types: ["summary", "split"],
          },
        ];
      } else if (url.includes("/sections")) {
        const pinned = url.includes("run_id=");
        body = {
          run_note: {
            data: {
              story: pinned ? "旧版の総評です。" : "最新版の総評です。",
              good_points: [
                { text: "心拍が安定していました。", evidence: "signals.hr_drift" },
              ],
              growth_points: [],
              next_challenge: "次回も同じ入りで。",
              timeline: [],
              notes: [],
            },
            parse_error: false,
            raw: null,
          },
        };
      } else if (url.includes("/report")) {
        body = BASE_REPORT;
      } else if (url.includes("/time-series")) {
        body = { timestamps: [], metrics: {} };
      } else if (url.includes("/track")) {
        body = { points: [] };
      } else {
        body = BASE_DETAIL;
      }
      return Promise.resolve(
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  it("test_version_select_has_focus_ring", async () => {
    stubVersionedFetch();
    renderDetail();

    const select = await screen.findByLabelText("版を選択:");

    // Keyboard focus must stay visible: the old style removed the UA outline
    // and offered only a border tint in exchange (#912).
    const classes = select.className.split(" ");
    expect(select.className).toContain("focus-visible:ring-2");
    expect(classes).not.toContain("focus:outline-none");
    expect(classes).not.toContain("outline-none");
  });

  it("バージョンセレクタが2版を表示し切替できる", async () => {
    const fetchMock = stubVersionedFetch();
    renderDetail();

    // Selector shows both versions with the total-count badge.
    const select = (await screen.findByLabelText(
      "版を選択:",
    )) as HTMLSelectElement;
    expect(within(select).getAllByRole("option")).toHaveLength(2);
    expect(screen.getByText("全2版")).toBeInTheDocument();

    // Switching to the older run re-fetches sections with the run_id pin.
    fireEvent.change(select, { target: { value: "1" } });

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([input]) =>
          String(input).includes("/sections?run_id=1"),
        ),
      ).toBe(true);
    });
  });
});
