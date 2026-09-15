import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "../test/utils";
import Performance from "./Performance";

// echarts requires a real canvas; mock the modular wrapper out for jsdom
vi.mock("../lib/echarts", () => ({
  echarts: {
    init: () => ({
      setOption: vi.fn(),
      resize: vi.fn(),
      dispose: vi.fn(),
    }),
  },
}));

const VOLUME_WEEK = [
  {
    bucket: "2025-09-22",
    distance_km: 15.0,
    duration_seconds: 5400,
    run_count: 2,
  },
  {
    bucket: "2025-09-29",
    distance_km: 8.0,
    duration_seconds: 2400,
    run_count: 1,
  },
];

const VOLUME_MONTH = [
  {
    bucket: "2025-09",
    distance_km: 90.0,
    duration_seconds: 32400,
    run_count: 12,
  },
  {
    bucket: "2025-10",
    distance_km: 120.0,
    duration_seconds: 43200,
    run_count: 16,
  },
];

const NARRATION_WEEK = {
  granularity: "week",
  period_start: "2025-10-06",
  period_end: "2025-10-12",
  analysis_data: { summary: "今週は距離を維持しながらHRを抑えられています。" },
  created_at: "2025-10-13T09:00:00",
};

const NARRATION_MONTH = {
  granularity: "month",
  period_start: "2025-10-01",
  period_end: "2025-10-31",
  analysis_data: { summary: "今月は月間走行量が前月から積み上がっています。" },
  created_at: "2025-11-01T09:00:00",
};

const PHYSIOLOGY = {
  vo2max: [
    { date: "2025-10-06", value: 49.6 },
    { date: "2025-10-13", value: 50.1 },
  ],
  lactate_threshold: [{ date: "2025-10-13", heart_rate: 168, speed_mps: 3.2 }],
};

const FORM = [
  {
    date: "2025-10-06",
    overall_score: 4.2,
    gct_delta: 2.5,
    vo_delta: 0.4,
    vr_delta: 0.3,
  },
];

const EFFICIENCY = [
  {
    date: "2025-10-06",
    aerobic_efficiency: "good",
    primary_zone: "Zone 2",
    zone1_percentage: 10.0,
    zone2_percentage: 60.0,
    zone3_percentage: 20.0,
    zone4_percentage: 8.0,
    zone5_percentage: 2.0,
  },
];

const HEAT_ADJUSTED = {
  status: "ok",
  coefficients: { beta_heat: 0.35, ref_temp_c: 15.0, n: 12 },
  neutral_hr_slope: -0.02,
  points: [
    {
      date: "2025-07-01",
      temp_c: 28,
      raw_hr: 150,
      heat_cost: 4.55,
      neutral_hr: 145.45,
    },
    {
      date: "2025-07-15",
      temp_c: 32,
      raw_hr: 154,
      heat_cost: 5.95,
      neutral_hr: 148.05,
    },
  ],
};

const CRITICAL_SPEED = [
  {
    quarter: "2025-Q4",
    cs_mps: 2.83,
    cs_pace_sec_per_km: 353.4,
    r_squared: 0.9998,
    n: 4,
    label: "threshold-anchored (no short/long max effort)",
  },
];

const OBJECTIVE_FITNESS = {
  // Six weeks apart, so the page can read a four-week VDOT delta (+0.7).
  objective_curve: [
    { date: "2025-09-01", vdot: 34.5, source_distance_km: 5.0 },
    { date: "2025-10-13", vdot: 35.2, source_distance_km: 5.0 },
  ],
  garmin_vo2max: [
    { date: "2025-09-01", value: 44.6 },
    { date: "2025-10-13", value: 45.1 },
  ],
  optimism_gap: {
    garmin_vdot: 44.6,
    objective_vdot: 35.2,
    gap_vdot: 9.4,
    gap_pace_sec_per_km: 63,
  },
};

const DURABILITY_WORSENING = {
  activities: [
    {
      activity_id: 9000005001,
      activity_date: "2025-10-05",
      distance_km: 18.0,
      decoupling_pct: 4.2,
      pace_fade_pct: 3.7,
      gct_fade_pct: 2.1,
      vo_fade_pct: 1.4,
      vr_fade_pct: 0.9,
    },
    {
      activity_id: 9000005002,
      activity_date: "2025-10-19",
      distance_km: 21.0,
      decoupling_pct: 6.3,
      pace_fade_pct: 5.1,
      gct_fade_pct: 5.8,
      vo_fade_pct: 3.2,
      vr_fade_pct: 2.6,
    },
  ],
  trend: {
    decoupling_slope_per_day: 0.15,
    data_points: 2,
    direction: "worsening",
    gct_fade_slope_per_day: 0.26,
    form_direction: "worsening",
  },
};

const DURABILITY_EMPTY = {
  activities: [],
  trend: {
    decoupling_slope_per_day: 0.0,
    data_points: 0,
    direction: "insufficient_data",
    gct_fade_slope_per_day: null,
    form_direction: "insufficient_data",
  },
};

const WEIGHT_ECONOMY = {
  weeks: 52,
  n_matched: 2,
  weight_spread_kg: 1.2,
  model: {
    n: 6,
    r_squared: 0.42,
    weight: { coef: -0.00044, p_value: 0.03, vif: 1.8 },
    days: { coef: 0.00001, p_value: 0.2, vif: 1.8 },
    fitness: null,
    delta_ef_per_5kg_loss: 0.0022,
    collinearity_flag: false,
    note: "association with effect-size estimate (no collinearity detected)",
  },
  // Seven weeks apart, so the page can read a four-week EF delta (+2.8%).
  series: [
    {
      activity_id: 1,
      run_date: "2025-09-01",
      weight_kg: 80.0,
      ef: 0.0176,
      weight_gap_days: 0,
    },
    {
      activity_id: 2,
      run_date: "2025-10-20",
      weight_kg: 78.8,
      ef: 0.0181,
      weight_gap_days: 1,
    },
  ],
  note: "association with effect-size estimate (no collinearity detected)",
};

/** The in-page table of contents: nav label -> block anchor id. The section
 *  headings are the same labels — one list drives nav and blocks alike. */
const SECTIONS = [
  { id: "volume", label: "走行量" },
  { id: "physiology", label: "生理指標" },
  { id: "efficiency", label: "効率推移" },
  { id: "critical-speed", label: "クリティカルスピード" },
  { id: "objective-fitness", label: "客観フィットネス" },
  { id: "heat-adjusted", label: "気候中立HR" },
  { id: "form", label: "フォームスコア" },
  { id: "durability", label: "耐久性" },
  { id: "weight-economy", label: "体重 × エコノミー" },
];

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function stubPerformanceFetch({
  durability = DURABILITY_WORSENING,
  // When set, any endpoint whose URL starts with this prefix never resolves,
  // simulating a slow block that must not block the rest of the page.
  slowPrefix,
  // No narration has been generated yet for this period.
  narration404 = false,
}: {
  durability?: unknown;
  slowPrefix?: string;
  narration404?: boolean;
} = {}): void {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      if (slowPrefix != null && url.startsWith(slowPrefix)) {
        return new Promise<Response>(() => {});
      }
      if (url.startsWith("/api/trends/narration/versions")) {
        if (narration404) {
          return Promise.resolve(jsonResponse({ detail: "not found" }, 404));
        }
        const latest = url.includes("granularity=month")
          ? NARRATION_MONTH
          : NARRATION_WEEK;
        // Two saved versions, newest first — the page's "解説 v2".
        return Promise.resolve(
          jsonResponse([
            latest,
            { ...latest, created_at: "2025-10-12T09:00:00" },
          ]),
        );
      }
      if (url.startsWith("/api/trends/narration")) {
        if (narration404) {
          return Promise.resolve(jsonResponse({ detail: "not found" }, 404));
        }
        return Promise.resolve(
          jsonResponse(
            url.includes("granularity=month") ? NARRATION_MONTH : NARRATION_WEEK,
          ),
        );
      }
      if (url.startsWith("/api/trends/volume")) {
        return Promise.resolve(
          jsonResponse(
            url.includes("granularity=month") ? VOLUME_MONTH : VOLUME_WEEK,
          ),
        );
      }
      if (url.startsWith("/api/trends/physiology")) {
        return Promise.resolve(jsonResponse(PHYSIOLOGY));
      }
      if (url.startsWith("/api/trends/form")) {
        return Promise.resolve(jsonResponse(FORM));
      }
      if (url.startsWith("/api/trends/critical-speed")) {
        return Promise.resolve(jsonResponse(CRITICAL_SPEED));
      }
      if (url.startsWith("/api/trends/efficiency")) {
        return Promise.resolve(jsonResponse(EFFICIENCY));
      }
      if (url.startsWith("/api/trends/heat-adjusted")) {
        return Promise.resolve(jsonResponse(HEAT_ADJUSTED));
      }
      if (url.startsWith("/api/trends/objective-fitness")) {
        return Promise.resolve(jsonResponse(OBJECTIVE_FITNESS));
      }
      if (url.startsWith("/api/durability-trend")) {
        return Promise.resolve(jsonResponse(durability));
      }
      if (url.startsWith("/api/weight-economy-coupling")) {
        return Promise.resolve(jsonResponse(WEIGHT_ECONOMY));
      }
      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    }),
  );
}

/** The page links its vitals cells to in-page anchors, so it needs a router. */
function renderPerformance() {
  return render(
    <MemoryRouter>
      <Performance />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Performance", () => {
  it("test_performance_page_single_column_and_segment", async () => {
    stubPerformanceFetch();

    const { container } = renderPerformance();

    // The verdict is the page's h1: the reader lands on the judgement.
    expect(await screen.findByText("速くなっている。")).toBeInTheDocument();
    // The tail is qualitative: the figures live in the VitalsRow below (#1190).
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "速くなっている。VDOT・EF ともに 4 週で上昇。",
    );
    // The coach's opening paragraph is the rationale under it, and the rest of
    // the write-up is folded away.
    // Twice: once as the verdict's lead, once inside the folded full text.
    expect(
      screen.getAllByText(/今週は距離を維持しながらHRを抑えられています/),
    ).toHaveLength(2);
    expect(screen.getByText("コーチ解説の全文")).toBeInTheDocument();
    expect(
      await screen.findByText(/週次トレンド · 10\/06 – 10\/12 · 解説 v2/),
    ).toBeInTheDocument();

    // Nine section blocks, one column: no two-up grid anywhere on the page.
    const headings = await screen.findAllByRole("heading", { level: 2 });
    expect(headings.map((h) => h.textContent)).toEqual(
      SECTIONS.map(({ label }) => label),
    );
    expect(container.innerHTML).not.toContain("md:grid-cols-2");

    // Content from the mocked payloads reaches the blocks.
    expect(screen.getByText(/VO2max 50\.1/)).toBeInTheDocument();
    expect(screen.getByText(/63 s\/km/)).toBeInTheDocument();
    expect(screen.getByText("心拍 悪化傾向")).toBeInTheDocument();

    // Condition-page blocks do not leak onto the performance page.
    expect(
      screen.queryByRole("heading", { level: 2, name: "訓練負荷 (ACWR)" }),
    ).toBeNull();

    // The week/month segment lives on the page, not inside the volume block.
    const segment = screen.getByRole("group", { name: "集計単位" });
    const monthButton = within(segment).getByRole("button", { name: "月" });
    expect(within(segment).getByRole("button", { name: "週" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    fireEvent.click(monthButton);

    // granularity="month" propagates to the narration (monthly fetch)...
    expect(
      await screen.findAllByText(
        /今月は月間走行量が前月から積み上がっています/,
      ),
    ).toHaveLength(2);
    expect(screen.getByText(/月次トレンド · 10\/01 – 10\/31/)).toBeInTheDocument();

    // ...and to the volume block (monthly buckets).
    expect(await screen.findByText(/今月 120\.0km/)).toBeInTheDocument();
    expect(monthButton).toHaveAttribute("aria-pressed", "true");
  });

  it("test_performance_vitals_row", async () => {
    stubPerformanceFetch();

    renderPerformance();

    const vitals = await screen.findByRole("region", { name: "客観指標" });
    for (const label of [
      "客観 VDOT",
      "効率 EF",
      "クリティカルスピード",
      "耐久性 デカップリング",
    ]) {
      expect(within(vitals).getByText(label)).toBeInTheDocument();
    }

    // The objective readings and their four-week moves.
    expect(await within(vitals).findByText("35.2")).toBeInTheDocument();
    expect(within(vitals).getByText("4週 +0.7")).toBeInTheDocument();
    expect(within(vitals).getByText("5:53")).toBeInTheDocument();

    // 6.3% decoupling misses the 3.5% target, so its note is the warn tone.
    expect(within(vitals).getByText("6.3")).toBeInTheDocument();
    const decouplingNote = within(vitals).getByText(/目標 3\.5% 未満を超過/);
    expect(decouplingNote.className).toContain("text-status-warn");
  });

  it("test_performance_has_section_nav", async () => {
    stubPerformanceFetch();

    const { container } = renderPerformance();

    const nav = screen.getByRole("navigation", { name: "セクション目次" });
    // Each entry links to one block...
    for (const { id, label } of SECTIONS) {
      expect(within(nav).getByRole("link", { name: label })).toHaveAttribute(
        "href",
        `#${id}`,
      );
    }

    // ...and every target anchor is actually rendered, so no entry is a dead
    // link (the anchors wrap the skeletons too, before the data lands).
    await screen.findByRole("heading", { level: 2, name: "走行量" });
    for (const { id } of SECTIONS) {
      expect(container.querySelector(`#${id}`)).not.toBeNull();
    }
  });

  it("test_performance_hides_narration_when_absent", async () => {
    stubPerformanceFetch({ narration404: true });

    renderPerformance();

    // The verdict still stands on its numbers; only the prose is missing.
    expect(await screen.findByText("速くなっている。")).toBeInTheDocument();
    expect(screen.queryByText("コーチ解説の全文")).toBeNull();
    expect(screen.getByText("週次トレンド")).toBeInTheDocument();
  });

  it("falls back when durability data is insufficient", async () => {
    stubPerformanceFetch({ durability: DURABILITY_EMPTY });

    renderPerformance();

    expect(
      await screen.findByRole("heading", { level: 2, name: "耐久性" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/10km以上のロングランがないため/),
    ).toBeInTheDocument();
  });

  it("renders resolved blocks independently of slow ones", async () => {
    stubPerformanceFetch({ slowPrefix: "/api/trends/physiology" });

    renderPerformance();

    // A fast block resolves even though physiology never does.
    expect(
      await screen.findByText(/今週 8\.0km/),
    ).toBeInTheDocument();

    const skeletons = screen.getAllByRole("status");
    expect(
      skeletons.some((el) => el.getAttribute("aria-label") === "生理指標"),
    ).toBe(true);
  });
});
