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
  objective_curve: [
    { date: "2025-10-06", vdot: 34.5, source_distance_km: 5.0 },
    { date: "2025-10-13", vdot: 35.2, source_distance_km: 5.0 },
  ],
  garmin_vo2max: [
    { date: "2025-10-06", value: 44.6 },
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
  series: [
    {
      activity_id: 1,
      run_date: "2025-10-06",
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

/** Every metric card heading on the page (the narration card is separate). */
const METRIC_CARD_HEADINGS = [
  "走行量",
  "生理指標 (VO2max / 乳酸閾値)",
  "効率推移 (HRゾーン分布)",
  "クリティカルスピード (四半期)",
  "客観フィットネス曲線 (実走VDOT vs Garmin VO2max)",
  "気候中立HRトレンド (暑熱補正)",
  "フォームスコア推移",
  "耐久性 (心拍デカップリング・フォーム失速)",
  "体重 × ランニングエコノミー (EF)",
];

/** The in-page table of contents: chip label -> card anchor id. */
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

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function stubPerformanceFetch({
  durability = DURABILITY_WORSENING,
  // When set, any endpoint whose URL starts with this prefix never resolves,
  // simulating a slow card that must not block the rest of the page.
  slowPrefix,
}: { durability?: unknown; slowPrefix?: string } = {}): void {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      if (slowPrefix != null && url.startsWith(slowPrefix)) {
        return new Promise<Response>(() => {});
      }
      if (url.startsWith("/api/trends/narration/versions")) {
        return Promise.resolve(jsonResponse([]));
      }
      if (url.startsWith("/api/trends/narration")) {
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

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Performance", () => {
  it("test_performance_renders_ten_cards", async () => {
    stubPerformanceFetch();

    render(<Performance />);

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "速くなっているか",
      }),
    ).toBeInTheDocument();

    // Coach narration leads the page...
    expect(
      await screen.findByRole("heading", { level: 2, name: "トレンド解説" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/今週は距離を維持しながらHRを抑えられています/),
    ).toBeInTheDocument();

    // ...followed by the nine metric cards.
    for (const name of METRIC_CARD_HEADINGS) {
      expect(
        await screen.findByRole("heading", { level: 2, name }),
      ).toBeInTheDocument();
    }

    // Content from the mocked payloads reaches the cards.
    expect(screen.getByText(/最新VO2max: 50\.1/)).toBeInTheDocument();
    expect(screen.getByText(/63 s\/km/)).toBeInTheDocument();
    expect(screen.getByText("心拍 悪化傾向")).toBeInTheDocument();

    // Condition-page cards do not leak onto the performance page.
    expect(
      screen.queryByRole("heading", { level: 2, name: "訓練負荷 (ACWR)" }),
    ).toBeNull();
  });

  it("test_performance_granularity_toggle_updates_narration_and_volume", async () => {
    stubPerformanceFetch();

    render(<Performance />);

    // Weekly is the default: weekly narration + weekly volume bucket.
    expect(
      await screen.findByText(
        /今週は距離を維持しながらHRを抑えられています/,
      ),
    ).toBeInTheDocument();
    expect(await screen.findByText(/直近週 \(2025-09-29\)/)).toBeInTheDocument();

    // The toggle lives on the page, not inside the volume card.
    const toggle = screen.getByRole("group", { name: "集計単位" });
    const monthButton = within(toggle).getByRole("button", { name: "月" });
    expect(within(toggle).getByRole("button", { name: "週" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    fireEvent.click(monthButton);

    // granularity="month" propagates to the narration card (monthly fetch)...
    expect(
      await screen.findByText(
        /今月は月間走行量が前月から積み上がっています/,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/月次トレンド: 2025-10-01/)).toBeInTheDocument();

    // ...and to the volume card (monthly buckets).
    expect(await screen.findByText(/直近月 \(2025-10\)/)).toBeInTheDocument();
    expect(screen.getByText(/120\.0 km/)).toBeInTheDocument();
    expect(monthButton).toHaveAttribute("aria-pressed", "true");
  });

  it("test_performance_has_section_nav", async () => {
    stubPerformanceFetch();

    const { container } = render(<Performance />);

    const nav = screen.getByRole("navigation", { name: "セクション目次" });
    // Each chip links to one card section...
    for (const { id, label } of SECTIONS) {
      expect(within(nav).getByRole("link", { name: label })).toHaveAttribute(
        "href",
        `#${id}`,
      );
    }

    // ...and every target anchor is actually rendered, so no chip is a dead
    // link (the anchors wrap the skeletons too, before the data lands).
    await screen.findByRole("heading", { level: 2, name: "走行量" });
    for (const { id } of SECTIONS) {
      expect(container.querySelector(`#${id}`)).not.toBeNull();
    }
  });

  it("falls back when durability data is insufficient", async () => {
    stubPerformanceFetch({ durability: DURABILITY_EMPTY });

    render(<Performance />);

    expect(
      await screen.findByRole("heading", {
        level: 2,
        name: "耐久性 (心拍デカップリング・フォーム失速)",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("心拍 データ不足")).toBeInTheDocument();
    expect(screen.getByText("フォーム データ不足")).toBeInTheDocument();
    expect(
      screen.getByText(/10km以上のロングランがないため/),
    ).toBeInTheDocument();
  });

  it("renders resolved cards independently of slow ones", async () => {
    stubPerformanceFetch({ slowPrefix: "/api/trends/physiology" });

    render(<Performance />);

    // A fast card resolves even though physiology never does.
    expect(
      await screen.findByRole("heading", { level: 2, name: "走行量" }),
    ).toBeInTheDocument();

    expect(
      screen.queryByRole("heading", {
        level: 2,
        name: "生理指標 (VO2max / 乳酸閾値)",
      }),
    ).toBeNull();
    const skeletons = screen.getAllByRole("status");
    expect(
      skeletons.some((el) => el.getAttribute("aria-label") === "生理指標"),
    ).toBe(true);
  });
});
