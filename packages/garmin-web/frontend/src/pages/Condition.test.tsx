import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "../test/utils";
import Condition from "./Condition";

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
      {
        week_start: "2025-09-22",
        load_km: 10.0,
        acwr: 0.6,
        status: "undertraining",
      },
      {
        week_start: "2025-10-06",
        load_km: 50.0,
        acwr: 2.5,
        status: "high_risk",
      },
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

/** The five card headings that are not the one under test in isolation checks. */
const CARD_HEADINGS = {
  formAnomaly: "今週の注意点",
  condition: "当日コンディション",
  recovery: "回復トレンド (RHR / HRV)",
  wellnessBaseline: "個人ベースライン逸脱 (HRV / Readiness / RHR)",
  trainingLoad: "訓練負荷 (ACWR)",
  bodyComposition: "体組成 (体重内訳)",
};

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function stubConditionFetch({
  trainingLoad = TRAINING_LOAD_OPTIMAL,
  wellnessBaseline = WELLNESS_BASELINE_WITHIN,
  formAnomalyFlags = FORM_ANOMALY_FLAGS,
  // When set, the endpoint whose URL starts with this prefix returns 500,
  // simulating a single broken card.
  failingPrefix,
}: {
  trainingLoad?: unknown;
  wellnessBaseline?: unknown;
  formAnomalyFlags?: unknown;
  failingPrefix?: string;
} = {}): void {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      if (failingPrefix != null && url.startsWith(failingPrefix)) {
        return Promise.resolve(
          new Response(JSON.stringify({ detail: "boom" }), {
            status: 500,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      if (url.startsWith("/api/form-anomaly-flags")) {
        return Promise.resolve(jsonResponse(formAnomalyFlags));
      }
      if (url.startsWith("/api/training-load")) {
        return Promise.resolve(jsonResponse(trainingLoad));
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

describe("Condition", () => {
  it("test_condition_renders_six_cards", async () => {
    stubConditionFetch();

    render(<Condition />);

    expect(
      await screen.findByRole("heading", { level: 1, name: "今の体の状態" }),
    ).toBeInTheDocument();

    for (const name of Object.values(CARD_HEADINGS)) {
      expect(
        await screen.findByRole("heading", { level: 2, name }),
      ).toBeInTheDocument();
    }

    // Content from the mocked payloads reaches the cards.
    expect(screen.getByText("2025-10-19")).toBeInTheDocument();
    expect(screen.getByText("質練OK")).toBeInTheDocument();
    expect(screen.getByText(/現在のACWR:/)).toBeInTheDocument();
    expect(screen.getByText(/-1\.2kg/)).toBeInTheDocument();

    // Performance-page cards do not leak onto the condition page.
    expect(
      screen.queryByRole("heading", { level: 2, name: "走行量" }),
    ).toBeNull();
  });

  it("test_condition_card_error_is_isolated", async () => {
    stubConditionFetch({ failingPrefix: "/api/recovery-trend" });

    render(<Condition />);

    // The broken card degrades to a retryable in-card alert...
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("回復トレンドの読み込みに失敗しました");
    expect(
      within(alert).getByRole("button", { name: "再試行" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", {
        level: 2,
        name: CARD_HEADINGS.recovery,
      }),
    ).toBeNull();

    // ...while the other five cards render normally.
    for (const [key, name] of Object.entries(CARD_HEADINGS)) {
      if (key === "recovery") continue;
      expect(
        await screen.findByRole("heading", { level: 2, name }),
      ).toBeInTheDocument();
    }

    // No all-or-nothing page banner replaces the page.
    expect(screen.queryByText(/^エラー: /)).toBeNull();
  });

  it("test_condition_keeps_anchor_ids", async () => {
    stubConditionFetch();

    const { container } = render(<Condition />);

    // Anchors exist from first paint (they wrap the skeleton too), so the Home
    // snapshot tiles' deep links resolve before the data lands.
    for (const id of ["training-load", "recovery", "form-anomaly"]) {
      const anchor = container.querySelector(`#${id}`);
      expect(anchor).not.toBeNull();
      expect(anchor).toHaveClass("scroll-mt-20");
    }

    // ...and they survive the swap from skeleton to real card.
    await screen.findByRole("heading", {
      level: 2,
      name: CARD_HEADINGS.formAnomaly,
    });
    for (const id of ["training-load", "recovery", "form-anomaly"]) {
      expect(container.querySelector(`#${id}`)).not.toBeNull();
    }
  });

  it("renders a high-risk warning in the ACWR block", async () => {
    stubConditionFetch({ trainingLoad: TRAINING_LOAD_HIGH_RISK });

    render(<Condition />);

    expect(
      await screen.findByRole("heading", {
        level: 2,
        name: CARD_HEADINGS.trainingLoad,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("高リスク")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/故障リスクが高い/);
  });

  it("falls back when ACWR data is insufficient", async () => {
    stubConditionFetch({ trainingLoad: TRAINING_LOAD_INSUFFICIENT });

    render(<Condition />);

    expect(
      await screen.findByRole("heading", {
        level: 2,
        name: CARD_HEADINGS.trainingLoad,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/ACWRを算出するためのデータが不足しています/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/現在のACWR:/)).toBeNull();
  });

  it("raises a wellness baseline alert when overall_flag is set", async () => {
    stubConditionFetch({ wellnessBaseline: WELLNESS_BASELINE_ADVERSE });

    render(<Condition />);

    expect(
      await screen.findByRole("heading", {
        level: 2,
        name: CARD_HEADINGS.wellnessBaseline,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/個人ベースラインから不利な方向に逸脱/),
    ).toBeInTheDocument();
  });

  it("shows 問題なし in the form-anomaly card when no flags", async () => {
    stubConditionFetch({ formAnomalyFlags: FORM_ANOMALY_FLAGS_EMPTY });

    render(<Condition />);

    expect(
      await screen.findByRole("heading", {
        level: 2,
        name: CARD_HEADINGS.formAnomaly,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("問題なし")).toBeInTheDocument();
    expect(
      screen.getByText(/直近のランでフォームの異常は検出されていません/),
    ).toBeInTheDocument();
  });
});
