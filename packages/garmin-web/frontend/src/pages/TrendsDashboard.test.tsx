import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import TrendsDashboard from "./TrendsDashboard";

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

const VOLUME = [
  { bucket: "2025-09-22", distance_km: 15.0, duration_seconds: 5400, run_count: 2 },
  { bucket: "2025-09-29", distance_km: 8.0, duration_seconds: 2400, run_count: 1 },
];

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

const TRAINING_LOAD_OPTIMAL = {
  current: {
    end_date: "2025-10-13",
    acute_load_7d: 20.0,
    chronic_load_28d_weekly: 20.0,
    acwr: 1.0,
    status: "optimal",
    load_metric: "distance_km",
  },
  trend: {
    weeks: [
      { week_start: "2025-09-22", load_km: 20.0, acwr: 1.0, status: "optimal" },
      { week_start: "2025-09-29", load_km: 22.0, acwr: 1.05, status: "optimal" },
    ],
    load_metric: "distance_km",
  },
};

const TRAINING_LOAD_HIGH_RISK = {
  current: {
    end_date: "2025-10-13",
    acute_load_7d: 50.0,
    chronic_load_28d_weekly: 20.0,
    acwr: 2.5,
    status: "high_risk",
    load_metric: "distance_km",
  },
  trend: {
    weeks: [
      { week_start: "2025-09-22", load_km: 10.0, acwr: 0.6, status: "undertraining" },
      { week_start: "2025-10-06", load_km: 50.0, acwr: 2.5, status: "high_risk" },
    ],
    load_metric: "distance_km",
  },
};

const TRAINING_LOAD_INSUFFICIENT = {
  current: {
    end_date: null,
    acute_load_7d: 0.0,
    chronic_load_28d_weekly: 0.0,
    acwr: null,
    status: "insufficient_data",
    load_metric: "distance_km",
  },
  trend: { weeks: [], load_metric: "distance_km" },
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

const RECOVERY_TREND = {
  weeks: 8,
  rhr: { median_7d: 48, median_30d: 49, rhr_trend: "improving" },
  hrv: {
    latest_ms: 65.0,
    status: "balanced",
    hrv_below_baseline_days: 0,
    under_recovery: false,
  },
  series: [
    { date: "2025-10-06", resting_hr: 48, hrv_overnight_ms: 65.0 },
    { date: "2025-10-07", resting_hr: 47, hrv_overnight_ms: 68.0 },
  ],
};

const RECOVERY_STATUS = {
  date: "2025-10-07",
  recommendation: "quality",
  score: 80,
  reasons: ["Training Readiness 80 が高くHRVも正常→質練OK"],
  training_readiness: 80,
  body_battery_high: 92,
  sleep_score: 80,
};

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

const BODY_COMPOSITION = {
  weeks: 12,
  series: [
    { date: "2025-10-06", weight_kg: 80.0, fat_mass: 17.6, lean_mass: 62.4 },
    { date: "2025-10-07", weight_kg: 78.8, fat_mass: 16.4, lean_mass: 62.4 },
  ],
  change: {
    delta_weight: -1.2,
    delta_fat: -1.0,
    delta_lean: -0.2,
    lean_loss_ratio: 0.17,
    muscle_loss_warning: false,
  },
  lean_pwr: 4.0,
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
    { activity_id: 1, run_date: "2025-10-06", weight_kg: 80.0, ef: 0.0176, weight_gap_days: 0 },
    { activity_id: 2, run_date: "2025-10-20", weight_kg: 78.8, ef: 0.0181, weight_gap_days: 1 },
  ],
  note: "association with effect-size estimate (no collinearity detected)",
};

const WELLNESS_BASELINE_WITHIN = {
  date: "2025-10-07",
  hrv: {
    metric: "hrv",
    mean: 65.0,
    std: 4.0,
    today: 64.0,
    z: -0.25,
    flag: "within",
    adverse: false,
    n: 30,
  },
  readiness: {
    metric: "readiness",
    mean: 75.0,
    std: 6.0,
    today: 76.0,
    z: 0.17,
    flag: "within",
    adverse: false,
    n: 30,
  },
  rhr: {
    metric: "rhr",
    mean: 48.0,
    std: 1.5,
    today: 48.0,
    z: 0.0,
    flag: "within",
    adverse: false,
    n: 30,
  },
  overall_flag: false,
};

const WELLNESS_BASELINE_ADVERSE = {
  ...WELLNESS_BASELINE_WITHIN,
  hrv: {
    metric: "hrv",
    mean: 65.0,
    std: 4.0,
    today: 40.0,
    z: -6.25,
    flag: "low",
    adverse: true,
    n: 30,
  },
  overall_flag: true,
};

const FORM_ANOMALY_FLAGS = {
  weeks: 2,
  scanned: 4,
  limited: false,
  flags: [
    {
      activity_id: 9100000002,
      activity_date: "2025-10-19",
      anomalies_detected: 3,
      severity_high: 1,
      top_recommendation: "後半のGCT増加に注意してください。",
    },
  ],
};

const FORM_ANOMALY_FLAGS_EMPTY = {
  weeks: 2,
  scanned: 4,
  limited: false,
  flags: [],
};

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function stubTrendsFetch(
  trainingLoad: unknown,
  durability: unknown = DURABILITY_WORSENING,
  wellnessBaseline: unknown = WELLNESS_BASELINE_WITHIN,
  formAnomalyFlags: unknown = FORM_ANOMALY_FLAGS,
  // When set, any endpoint whose URL starts with this prefix never resolves,
  // simulating a slow card that must not block the rest of the dashboard.
  slowPrefix?: string,
): void {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      if (slowPrefix != null && url.startsWith(slowPrefix)) {
        return new Promise<Response>(() => {});
      }
      if (url.startsWith("/api/form-anomaly-flags")) {
        return Promise.resolve(jsonResponse(formAnomalyFlags));
      }
      if (url.startsWith("/api/trends/volume")) {
        return Promise.resolve(jsonResponse(VOLUME));
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
      if (url.startsWith("/api/training-load")) {
        return Promise.resolve(jsonResponse(trainingLoad));
      }
      if (url.startsWith("/api/durability-trend")) {
        return Promise.resolve(jsonResponse(durability));
      }
      if (url.startsWith("/api/recovery-trend")) {
        return Promise.resolve(jsonResponse(RECOVERY_TREND));
      }
      if (url.startsWith("/api/recovery-status")) {
        return Promise.resolve(jsonResponse(RECOVERY_STATUS));
      }
      if (url.startsWith("/api/body-composition-trend")) {
        return Promise.resolve(jsonResponse(BODY_COMPOSITION));
      }
      if (url.startsWith("/api/trends/heat-adjusted")) {
        return Promise.resolve(jsonResponse(HEAT_ADJUSTED));
      }
      if (url.startsWith("/api/trends/objective-fitness")) {
        return Promise.resolve(jsonResponse(OBJECTIVE_FITNESS));
      }
      if (url.startsWith("/api/weight-economy-coupling")) {
        return Promise.resolve(jsonResponse(WEIGHT_ECONOMY));
      }
      if (url.startsWith("/api/wellness-baseline-deviation")) {
        return Promise.resolve(jsonResponse(wellnessBaseline));
      }
      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("TrendsDashboard", () => {
  it("TrendsDashboard still shows トレンド heading", async () => {
    stubTrendsFetch(TRAINING_LOAD_OPTIMAL);

    render(<TrendsDashboard />);

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "トレンドダッシュボード",
      }),
    ).toBeInTheDocument();
  });

  it("renders all six trend blocks from API data", async () => {
    stubTrendsFetch(TRAINING_LOAD_OPTIMAL);

    render(<TrendsDashboard />);

    // All six block headings appear once data is loaded
    expect(
      await screen.findByRole("heading", { level: 2, name: "走行量" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: "生理指標 (VO2max / 乳酸閾値)" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: "フォームスコア推移" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: "効率推移 (HRゾーン分布)" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: "訓練負荷 (ACWR)" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        level: 2,
        name: "耐久性 (心拍デカップリング・フォーム失速)",
      }),
    ).toBeInTheDocument();

    // Volume block summary is rendered from the mocked API data
    // (weekly buckets now key on the week's start date, e.g. "2025-09-29")
    expect(screen.getByText(/2025-09-29/)).toBeInTheDocument();
    expect(screen.getByText(/8\.0 km/)).toBeInTheDocument();

    // Physiology block shows the latest VO2max from the mocked API data
    expect(screen.getByText(/最新VO2max: 50\.1/)).toBeInTheDocument();

    // Objective fitness overlay block renders with the optimism gap annotation.
    expect(
      screen.getByRole("heading", {
        level: 2,
        name: "客観フィットネス曲線 (実走VDOT vs Garmin VO2max)",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText(/63 s\/km/)).toBeInTheDocument();

    // ACWR block shows the optimal status badge and current ACWR value
    expect(screen.getByText("最適")).toBeInTheDocument();
    expect(screen.getByText(/現在のACWR:/)).toBeInTheDocument();

    // Durability block shows worsening HR + form direction badges and the run
    // count line covering both decoupling and GCT fade.
    expect(screen.getByText("心拍 悪化傾向")).toBeInTheDocument();
    expect(screen.getByText("フォーム 悪化傾向")).toBeInTheDocument();
    expect(
      screen.getByText(/デカップリングとGCT後半失速の推移/),
    ).toBeInTheDocument();

    // Recovery / condition / body-composition panels (Issue #502).
    expect(
      screen.getByRole("heading", { level: 2, name: "回復トレンド (RHR / HRV)" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: "当日コンディション" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: "体組成 (体重内訳)" }),
    ).toBeInTheDocument();
    // Quality recommendation -> green badge label.
    expect(screen.getByText("質練OK")).toBeInTheDocument();
    // Body-composition summary renders the net weight loss via formatNumber.
    expect(screen.getByText(/-1\.2kg/)).toBeInTheDocument();

    // Wellness personal-baseline deviation panel heading (Issue #635).
    expect(
      screen.getByRole("heading", {
        level: 2,
        name: "個人ベースライン逸脱 (HRV / Readiness / RHR)",
      }),
    ).toBeInTheDocument();
    // All-within baseline -> no overall-flag alert.
    expect(
      screen.queryByText(/個人ベースラインから不利な方向に逸脱/),
    ).not.toBeInTheDocument();

    // "今週の注意点" card lists the flagged run with its recommendation.
    expect(
      screen.getByRole("heading", { level: 2, name: "今週の注意点" }),
    ).toBeInTheDocument();
    expect(screen.getByText("2025-10-19")).toBeInTheDocument();
    expect(
      screen.getByText(/後半のGCT増加に注意してください/),
    ).toBeInTheDocument();
  });

  it("shows skeletons while data is null and content after resolve", async () => {
    stubTrendsFetch(TRAINING_LOAD_OPTIMAL);

    render(<TrendsDashboard />);

    // Before any fetch resolves, every card is a busy skeleton placeholder and
    // no real card heading exists yet (the page is not blocked on a spinner).
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
    expect(
      screen.queryByRole("heading", { level: 2, name: "走行量" }),
    ).toBeNull();

    // Once the fetches resolve, the skeletons are replaced by real cards.
    expect(
      await screen.findByRole("heading", { level: 2, name: "走行量" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("renders resolved cards independently of slow ones", async () => {
    // Physiology hangs forever; every other endpoint resolves promptly.
    stubTrendsFetch(
      TRAINING_LOAD_OPTIMAL,
      DURABILITY_WORSENING,
      WELLNESS_BASELINE_WITHIN,
      FORM_ANOMALY_FLAGS,
      "/api/trends/physiology",
    );

    render(<TrendsDashboard />);

    // A fast card resolves and renders its real content even though physiology
    // never resolves — proving cards no longer wait on the slowest fetch.
    expect(
      await screen.findByRole("heading", { level: 2, name: "走行量" }),
    ).toBeInTheDocument();

    // The slow physiology card stays a busy skeleton alongside the resolved ones.
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

  it("renders 今週の注意点 as a full-width band outside the metric grid", async () => {
    stubTrendsFetch(TRAINING_LOAD_OPTIMAL);

    render(<TrendsDashboard />);

    const band = (
      await screen.findByRole("heading", { level: 2, name: "今週の注意点" })
    ).closest("section");
    expect(band).not.toBeNull();
    // The alert band is its own region, not nested in any metric-group grid.
    expect(band).toHaveAttribute("aria-label", "今週の注意点");
    expect(band?.closest(".grid")).toBeNull();
    // None of the three group regions contain the alert band.
    for (const title of ["今の状態", "パフォーマンス", "フォーム & 身体"]) {
      expect(band?.closest(`section[aria-label="${title}"]`)).toBeNull();
    }
  });

  it("renders three section headings 今の状態 / パフォーマンス / フォーム & 身体", async () => {
    stubTrendsFetch(TRAINING_LOAD_OPTIMAL);

    render(<TrendsDashboard />);

    expect(await screen.findByText("今の状態")).toBeInTheDocument();
    expect(screen.getByText("パフォーマンス")).toBeInTheDocument();
    expect(screen.getByText("フォーム & 身体")).toBeInTheDocument();
  });

  it("groups コンディション card under 今の状態 section", async () => {
    stubTrendsFetch(TRAINING_LOAD_OPTIMAL);

    render(<TrendsDashboard />);

    const card = await screen.findByRole("heading", {
      level: 2,
      name: "当日コンディション",
    });
    const group = card.closest('section[aria-label="今の状態"]');
    expect(group).not.toBeNull();
    expect(within(group as HTMLElement).getByText("今の状態")).toBeInTheDocument();
  });

  it("groups 走行量 card under パフォーマンス section", async () => {
    stubTrendsFetch(TRAINING_LOAD_OPTIMAL);

    render(<TrendsDashboard />);

    const card = await screen.findByRole("heading", {
      level: 2,
      name: "走行量",
    });
    const group = card.closest('section[aria-label="パフォーマンス"]');
    expect(group).not.toBeNull();
    expect(
      within(group as HTMLElement).getByText("パフォーマンス"),
    ).toBeInTheDocument();
  });

  it("still renders all 15 metric cards after regroup", async () => {
    stubTrendsFetch(TRAINING_LOAD_OPTIMAL);

    render(<TrendsDashboard />);

    // Wait for data to load, then assert every card heading survives the regroup.
    await screen.findByRole("heading", { level: 2, name: "走行量" });

    const cardHeadings = [
      "今週の注意点",
      "走行量",
      "生理指標 (VO2max / 乳酸閾値)",
      "客観フィットネス曲線 (実走VDOT vs Garmin VO2max)",
      "フォームスコア推移",
      "効率推移 (HRゾーン分布)",
      "気候中立HRトレンド (暑熱補正)",
      "クリティカルスピード (四半期)",
      "訓練負荷 (ACWR)",
      "耐久性 (心拍デカップリング・フォーム失速)",
      "回復トレンド (RHR / HRV)",
      "当日コンディション",
      "体組成 (体重内訳)",
      "体重 × ランニングエコノミー (EF)",
      "個人ベースライン逸脱 (HRV / Readiness / RHR)",
    ];
    for (const name of cardHeadings) {
      expect(
        screen.getByRole("heading", { level: 2, name }),
      ).toBeInTheDocument();
    }
  });

  it("raises a wellness baseline alert when overall_flag is set", async () => {
    stubTrendsFetch(
      TRAINING_LOAD_OPTIMAL,
      DURABILITY_WORSENING,
      WELLNESS_BASELINE_ADVERSE,
    );

    render(<TrendsDashboard />);

    expect(
      await screen.findByRole("heading", {
        level: 2,
        name: "個人ベースライン逸脱 (HRV / Readiness / RHR)",
      }),
    ).toBeInTheDocument();

    // Adverse HRV deviation -> overall_flag alert is surfaced.
    expect(
      screen.getByText(/個人ベースラインから不利な方向に逸脱/),
    ).toBeInTheDocument();
  });

  it("shows 問題なし in the form-anomaly card when no flags", async () => {
    stubTrendsFetch(
      TRAINING_LOAD_OPTIMAL,
      DURABILITY_WORSENING,
      WELLNESS_BASELINE_WITHIN,
      FORM_ANOMALY_FLAGS_EMPTY,
    );

    render(<TrendsDashboard />);

    expect(
      await screen.findByRole("heading", { level: 2, name: "今週の注意点" }),
    ).toBeInTheDocument();
    expect(screen.getByText("問題なし")).toBeInTheDocument();
    expect(
      screen.getByText(/直近のランでフォームの異常は検出されていません/),
    ).toBeInTheDocument();
  });

  it("falls back when durability data is insufficient", async () => {
    stubTrendsFetch(TRAINING_LOAD_OPTIMAL, DURABILITY_EMPTY);

    render(<TrendsDashboard />);

    expect(
      await screen.findByRole("heading", {
        level: 2,
        name: "耐久性 (心拍デカップリング・フォーム失速)",
      }),
    ).toBeInTheDocument();

    // No qualifying long runs -> insufficient_data badges (HR + form) + fallback.
    expect(screen.getByText("心拍 データ不足")).toBeInTheDocument();
    expect(screen.getByText("フォーム データ不足")).toBeInTheDocument();
    expect(
      screen.getByText(/10km以上のロングランがないため/),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/デカップリングとGCT後半失速の推移/),
    ).not.toBeInTheDocument();
  });

  it("renders a high-risk warning in the ACWR block", async () => {
    stubTrendsFetch(TRAINING_LOAD_HIGH_RISK);

    render(<TrendsDashboard />);

    expect(
      await screen.findByRole("heading", { level: 2, name: "訓練負荷 (ACWR)" }),
    ).toBeInTheDocument();

    // High-risk status renders a badge and an alert message.
    expect(screen.getByText("高リスク")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/故障リスクが高い/);
  });

  it("falls back when ACWR data is insufficient", async () => {
    stubTrendsFetch(TRAINING_LOAD_INSUFFICIENT);

    render(<TrendsDashboard />);

    expect(
      await screen.findByRole("heading", { level: 2, name: "訓練負荷 (ACWR)" }),
    ).toBeInTheDocument();

    // Insufficient data -> fallback message, no current ACWR line.
    expect(
      screen.getByText(/ACWRを算出するためのデータが不足しています/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/現在のACWR:/)).not.toBeInTheDocument();
  });
});
