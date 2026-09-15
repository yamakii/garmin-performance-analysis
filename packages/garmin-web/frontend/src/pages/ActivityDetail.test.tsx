import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "../test/utils";
import ActivityDetail, { secondsOverCeiling } from "./ActivityDetail";
import type {
  ActivityDetailResponse,
  SectionsResponse,
  SplitAnomaliesResponse,
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

const NO_SPLIT_ANOMALIES: SplitAnomaliesResponse = {
  activity_id: 123,
  total: 0,
  material: 0,
  splits: [],
};

function stubFetch(opts: {
  detail: ActivityDetailResponse;
  sections: SectionsResponse;
  track: TrackPoint[];
  timeSeries?: unknown;
  splitAnomalies?: SplitAnomaliesResponse;
  splitAnomaliesStatus?: number;
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
      } else if (url.includes("/split-anomalies")) {
        body = opts.splitAnomalies ?? NO_SPLIT_ANOMALIES;
        status = opts.splitAnomaliesStatus ?? 200;
      } else if (url.includes("/time-series")) {
        body = opts.timeSeries ?? { timestamps: [], metrics: {} };
      } else if (url.includes("/track")) {
        body = { points: opts.track };
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
    if (url.includes("/sections/versions")) {
      body = [];
    } else if (url.includes("/sections")) {
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

// --- Header (Morning Brief, #1118) ---

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

const SUMMARY_SECTIONS: SectionsResponse = {
  summary: {
    data: {
      star_rating: "★★★★☆ 4.3/5.0",
      summary:
        "処方どおりの22kmを走り切れた一本でした。後半も心拍は上限内に収まっています。",
      key_strengths: ["心拍の安定", "ケイデンス維持", "後半の粘り"],
      improvement_areas: ["序盤の突っ込み", "給水の遅れ"],
      next_action: "次回は最初の3kmを7:00/kmより遅く入りましょう。",
      prescription_verdict: {
        verdict: "✅",
        prescription_title: "ロング 22km",
        reasons: ["処方「ロング 22km」どおりに実施できています（平均HR 148bpm ≦ 上限 150bpm）。"],
      },
      vs_previous: {
        pace_s_per_km: { current: 348, previous: 358, delta: -10 },
        avg_hr: { current: 148, previous: 151, delta: -3 },
        gct_ms: { current: 262, previous: 258, delta: 4 },
        cadence_spm: { current: 172, previous: 174, delta: -2 },
        days_ago: 7,
      },
    },
    parse_error: false,
    raw: null,
  },
};

describe("ActivityDetail header", () => {
  it("test_activity_detail_header_order", async () => {
    stubFetch({
      detail: LONG_RUN_DETAIL,
      sections: SUMMARY_SECTIONS,
      track: [],
    });
    renderDetail();

    // The run names the page, and its rating sits in the same line.
    const heading = await screen.findByRole("heading", {
      level: 1,
      name: /Morning Run/,
    });
    const rating = screen.getByLabelText("評価 4.3 / 5.0");
    expect(heading).toContainElement(rating);
    expect(rating.querySelector(".text-star")).not.toBeNull();

    // The conclusion sentence reads directly under the headline...
    const lead = screen.getByText("処方どおりの22kmを走り切れた一本でした。");
    expect(
      heading.compareDocumentPosition(lead) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();

    // ...and the four numbers behind it follow as one row.
    const kpis = screen.getByRole("region", { name: "このランの数値" });
    for (const value of ["22.14", "2:08:25", "5:48", "148"]) {
      expect(within(kpis).getByText(value)).toBeInTheDocument();
    }
    expect(
      heading.compareDocumentPosition(kpis) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();

    // The deltas against the last comparable run are one mono line, not chips.
    expect(
      screen.getByText(
        "前回比（7日前）: ペース -10秒/km · HR -3bpm · GCT +4ms · ケイデンス -2spm",
      ),
    ).toBeInTheDocument();
  });

  it("test_activity_detail_header_shows_configured_threshold", async () => {
    stubFetch({
      detail: LONG_RUN_DETAIL,
      sections: SUMMARY_SECTIONS,
      track: [],
    });
    renderDetail();

    // The meta line carries the date, the prescription and the physiology
    // numbers the run is read against (migrated from HeroHeader).
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
    // Without a summary there is no rating and no conclusion line.
    expect(screen.queryByLabelText(/評価/)).not.toBeInTheDocument();
  });

  it("test_hr_ceiling_note", () => {
    // Two of the four samples sit above the prescribed cap, one second each.
    expect(
      secondsOverCeiling(
        {
          timestamps: [0, 1, 2, 3],
          metrics: { heart_rate: [140, 151, 152, 149] },
        },
        150,
      ),
    ).toBe(2);

    // No prescription, no series, or no heart rate in it -> nothing to state.
    expect(
      secondsOverCeiling(
        { timestamps: [0, 1], metrics: { heart_rate: [160, 160] } },
        null,
      ),
    ).toBeNull();
    expect(secondsOverCeiling(null, 150)).toBeNull();
    expect(
      secondsOverCeiling({ timestamps: [0, 1], metrics: { speed: [3, 3] } }, 150),
    ).toBeNull();
  });

  it("test_hr_ceiling_note_rendered_from_the_prescription", async () => {
    stubFetch({
      detail: LONG_RUN_DETAIL,
      sections: SUMMARY_SECTIONS,
      track: [],
      timeSeries: {
        timestamps: [0, 1, 2, 3],
        metrics: { heart_rate: [140, 151, 152, 149] },
      },
    });
    renderDetail();

    // The cap comes from the verdict's own sentence ("上限 150bpm"), so the
    // header and the prose quote one number.
    expect(await screen.findByText("上限 150 · 超過 00:02")).toBeInTheDocument();
  });
});

describe("ActivityDetail metric toggles", () => {
  it("test_activity_detail_default_toggles", async () => {
    stubFetch({ detail: BASE_DETAIL, sections: {}, track: [] });
    renderDetail();

    await screen.findByRole("navigation", { name: "セクション目次" });
    // The splits table names columns after the same metrics, so the toggles
    // are read inside their own section.
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
) {
  stubFetch({
    detail: { ...BASE_DETAIL, splits },
    sections,
    track: [],
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
    // the same 5:30-6:30 field as above.
    const rows = await renderSplits([
      splitRow(1, 390, 138),
      splitRow(2, 360, 142),
      splitRow(3, 345, 146),
      splitRow(4, 330, 150),
      splitRow(5, 375, 144),
      splitRow(6, 244, 120, 0.01),
    ]);
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

  it("test_splits_disclosure_over_ten", async () => {
    await renderSplits(LONG_SPLITS);

    // The first ten kilometres are visible; the rest (and the per-split
    // narrative) sit behind one text link.
    const preview = screen.getAllByRole("table")[0];
    expect(within(preview).getAllByRole("row").slice(1)).toHaveLength(10);
    const trigger = screen.getByText("全 23 スプリットと解説を表示");
    expect(trigger.closest("details")?.hasAttribute("open")).toBe(false);
  });

  it("keeps a short run in one table", async () => {
    await renderSplits(LONG_SPLITS.slice(0, 8));

    expect(screen.getAllByRole("table")).toHaveLength(1);
    expect(screen.queryByText(/スプリットと解説を表示/)).not.toBeInTheDocument();
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
          { run_id: 2, created_at: NEW_STAMP, section_types: ["summary"] },
          {
            run_id: 1,
            created_at: OLD_STAMP,
            section_types: ["summary", "split"],
          },
        ];
      } else if (url.includes("/sections")) {
        const pinned = url.includes("run_id=");
        body = {
          summary: {
            data: {
              star_rating: pinned ? "★★★☆☆ 3.0/5.0" : "★★★★☆ 4.2/5.0",
            },
            parse_error: false,
            raw: null,
          },
        };
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
