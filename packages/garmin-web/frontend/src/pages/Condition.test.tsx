import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { energyBalanceFixture } from "../test/energyBalanceFixture";
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

/** The six section headings of the brief, in page order (#1120, #1439). */
const SECTION_HEADINGS = {
  formAnomaly: "今週の注意点",
  recovery: "回復トレンド",
  wellnessBaseline: "個人基準との差",
  trainingLoad: "訓練負荷",
  energyBalance: "エネルギー収支",
  bodyComposition: "体組成",
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
      if (url.startsWith("/api/energy-balance")) {
        return Promise.resolve(jsonResponse(energyBalanceFixture()));
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

function renderCondition() {
  return render(
    <MemoryRouter>
      <Condition />
    </MemoryRouter>,
  );
}

describe("Condition", () => {
  it("test_condition_page_order_and_anchors", async () => {
    stubConditionFetch();

    const { container } = renderCondition();

    // ① The verdict is the page heading: recovery state, then what qualifies
    // it (nothing out of band, one caution from the recent runs).
    const heading = await screen.findByRole("heading", { level: 1 });
    expect(heading).toHaveTextContent("回復は良好。");
    expect(heading).toHaveTextContent("1 件の注意点");
    expect(screen.getByText(RECOVERY_STATUS.reasons[0])).toBeInTheDocument();

    // ② The four numbers sit directly under it, at the `#today` anchor.
    const today = container.querySelector("#today");
    expect(today).not.toBeNull();
    expect(
      heading.compareDocumentPosition(today as Node) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(screen.getByText("HRV 夜間")).toBeInTheDocument();
    expect(screen.getByText("負荷 ACWR")).toBeInTheDocument();

    // ③ Six sections, each one reading; the old card wrapper is gone.
    for (const name of Object.values(SECTION_HEADINGS)) {
      expect(
        await screen.findByRole("heading", { level: 2, name }),
      ).toBeInTheDocument();
    }
    expect(
      screen.queryByRole("heading", { name: "当日コンディション" }),
    ).toBeNull();
    expect(
      screen.queryByRole("heading", { level: 2, name: "走行量" }),
    ).toBeNull();

    // The home vitals row and the /trends redirect deep-link into these.
    for (const id of ["form-anomaly", "recovery", "training-load"]) {
      expect(container.querySelector(`#${id}`)).not.toBeNull();
    }
  });

  it("test_condition_card_error_is_isolated", async () => {
    stubConditionFetch({ failingPrefix: "/api/recovery-trend" });

    renderCondition();

    // The broken section degrades to a retryable in-card alert...
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("回復トレンドの読み込みに失敗しました");
    expect(
      within(alert).getByRole("button", { name: "再試行" }),
    ).toBeInTheDocument();
    // ...stated once: the vitals row keeps rendering what did land.
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(await screen.findByText("負荷 ACWR")).toBeInTheDocument();

    // ...while every other section renders normally, heading included.
    for (const name of Object.values(SECTION_HEADINGS)) {
      expect(
        await screen.findByRole("heading", { level: 2, name }),
      ).toBeInTheDocument();
    }

    // No all-or-nothing page banner replaces the page.
    expect(screen.queryByText(/^エラー: /)).toBeNull();
  });

  it("test_condition_anchors_exist_before_data_lands", async () => {
    stubConditionFetch();

    const { container } = renderCondition();

    // Anchors sit on the sections, which render before their queries settle,
    // so a deep link lands even while the page is still skeletons.
    for (const id of ["training-load", "recovery", "form-anomaly"]) {
      const anchor = container.querySelector(`#${id}`);
      expect(anchor).not.toBeNull();
      expect(anchor).toHaveClass("scroll-mt-[60px]");
    }

    await screen.findByRole("heading", {
      level: 2,
      name: SECTION_HEADINGS.formAnomaly,
    });
    for (const id of ["training-load", "recovery", "form-anomaly"]) {
      expect(container.querySelector(`#${id}`)).not.toBeNull();
    }
  });

  it("renders a high-risk warning in the ACWR block", async () => {
    stubConditionFetch({ trainingLoad: TRAINING_LOAD_HIGH_RISK });

    renderCondition();

    expect(
      await screen.findByRole("heading", {
        level: 2,
        name: SECTION_HEADINGS.trainingLoad,
      }),
    ).toBeInTheDocument();
    expect(await screen.findByText("高リスク")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/故障リスクが高い/);
  });

  it("falls back when ACWR data is insufficient", async () => {
    stubConditionFetch({ trainingLoad: TRAINING_LOAD_INSUFFICIENT });

    renderCondition();

    expect(
      await screen.findByRole("heading", {
        level: 2,
        name: SECTION_HEADINGS.trainingLoad,
      }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/ACWRを算出するためのデータが不足しています/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/急性 /)).toBeNull();
  });

  it("raises a wellness baseline alert when overall_flag is set", async () => {
    stubConditionFetch({ wellnessBaseline: WELLNESS_BASELINE_ADVERSE });

    renderCondition();

    expect(
      await screen.findByRole("heading", {
        level: 2,
        name: SECTION_HEADINGS.wellnessBaseline,
      }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/個人ベースラインから不利な方向に逸脱/),
    ).toBeInTheDocument();
    // The HRV row is far outside the band, so its z value is flagged.
    expect(await screen.findByText("z -6.25")).toHaveClass("text-status-warn");
  });

  it("states a quiet week in one sentence when no flags", async () => {
    stubConditionFetch({ formAnomalyFlags: FORM_ANOMALY_FLAGS_EMPTY });

    renderCondition();

    expect(
      await screen.findByRole("heading", {
        level: 2,
        name: SECTION_HEADINGS.formAnomaly,
      }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(
        /直近のランでフォームの異常は検出されていません/,
      ),
    ).toBeInTheDocument();
    // The verdict counts the same zero.
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent(
      "注意点なし",
    );
  });
});
