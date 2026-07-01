import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import Dashboard from "./Dashboard";

// echarts requires a real canvas; mock the modular wrapper out for jsdom.
vi.mock("../lib/echarts", () => ({
  echarts: {
    init: () => ({
      setOption: vi.fn(),
      resize: vi.fn(),
      dispose: vi.fn(),
    }),
  },
}));

vi.mock("../api/client", () => ({
  fetchActivities: vi.fn(),
  fetchGoal: vi.fn(),
  fetchRaceReadiness: vi.fn(),
  fetchWeeklyReviews: vi.fn(),
}));

vi.mock("../api/recovery", () => ({
  fetchFormAnomalyFlags: vi.fn(),
  fetchRecoveryStatus: vi.fn(),
  fetchRecoveryTrend: vi.fn(),
  fetchWellnessBaselineDeviation: vi.fn(),
}));

vi.mock("../api/training_load", () => ({
  fetchTrainingLoad: vi.fn(),
}));

import {
  fetchActivities,
  fetchGoal,
  fetchRaceReadiness,
  fetchWeeklyReviews,
} from "../api/client";
import {
  fetchFormAnomalyFlags,
  fetchRecoveryStatus,
  fetchRecoveryTrend,
  fetchWellnessBaselineDeviation,
} from "../api/recovery";
import { fetchTrainingLoad } from "../api/training_load";

const RECOVERY_STATUS = {
  date: "2026-07-02",
  recommendation: "easy",
  score: 59,
  reasons: ["HRVが2夜連続でベースラインを下回っています"],
  training_readiness: 59,
  body_battery_high: 80,
  sleep_score: 61,
};

const BASELINE = {
  date: "2026-07-02",
  hrv: { metric: "hrv", mean: 60, std: 5, today: 51, z: -1.69, flag: "low", adverse: true, n: 30 },
  readiness: { metric: "readiness", mean: 70, std: 8, today: 59, z: -1.3, flag: "within", adverse: false, n: 30 },
  rhr: { metric: "rhr", mean: 45, std: 2, today: 48, z: 1.24, flag: "high", adverse: true, n: 30 },
  overall_flag: true,
};

const REVIEW = {
  review_id: 24,
  user_id: "default",
  week_start_date: "2026-06-29",
  week_end_date: "2026-07-05",
  review_date: "2026-06-30",
  review_data: {
    verdict: [{ date: "2026-07-05", session: "Long Run", rating: "✅" }],
    recommendations: ["ロング走は時間×HRで管理"],
  },
  created_at: "2026-06-30",
  agent_name: "weekly-review",
  agent_version: "1.3",
};

const LOAD = {
  current: {
    end_date: "2026-07-01",
    acute_load_7d: 26.4,
    chronic_load_28d_weekly: 25.9,
    acwr: 1.02,
    status: "optimal",
    load_metric: "distance_km",
  },
  trend: {
    weeks: [
      { week_start: "2026-06-22", load_km: 26.4, acwr: 0.99, status: "optimal" },
      { week_start: "2026-06-29", load_km: 6.5, acwr: 1.02, status: "optimal" },
    ],
    load_metric: "distance_km",
  },
};

const RECOVERY_TREND = {
  weeks: 8,
  rhr: { median_7d: 45, median_30d: 45, rhr_trend: "stable" },
  hrv: { latest_ms: 51, status: "low", hrv_below_baseline_days: 2, under_recovery: true },
  series: [
    { date: "2026-06-30", resting_hr: 45, hrv_overnight_ms: 47 },
    { date: "2026-07-01", resting_hr: 48, hrv_overnight_ms: 51 },
  ],
};

const FLAGS = { weeks: 2, scanned: 6, limited: false, flags: [] };

const READINESS = {
  current_vdot: 44.0,
  predicted_times: { full: 12734 },
  goal: {
    race_name: "さいたまマラソン",
    race_date: null,
    distance_km: 42.195,
    target_time_seconds: 16200,
  },
  progress: {
    predicted_time_seconds: 12734,
    gap_seconds: -3466,
    pace_gap_sec_per_km: -82.1,
    weeks_remaining: null,
    status: "ahead",
  },
};

const GOAL = {
  profile: { current_focus: null, focus_notes: null, updated_at: null },
  goals: [
    {
      goal_id: 25,
      race_name: "さいたまマラソン",
      race_date: null,
      priority: "A",
      goal_type: "marathon",
      distance_km: 42.195,
      target_time_seconds: 16200,
      status: "active",
      notes: null,
    },
  ],
  retrospectives: [],
};

const ACTIVITIES = [
  {
    activity_id: 2001,
    activity_date: "2026-06-30",
    activity_name: "イージーラン",
    total_distance_km: 6.47,
    total_time_seconds: 2940,
    avg_pace_seconds_per_km: 454,
    avg_heart_rate: 145,
  },
];

function mockAll() {
  vi.mocked(fetchRecoveryStatus).mockResolvedValue(RECOVERY_STATUS as never);
  vi.mocked(fetchWellnessBaselineDeviation).mockResolvedValue(
    BASELINE as never,
  );
  vi.mocked(fetchWeeklyReviews).mockResolvedValue([REVIEW] as never);
  vi.mocked(fetchTrainingLoad).mockResolvedValue(LOAD as never);
  vi.mocked(fetchRecoveryTrend).mockResolvedValue(RECOVERY_TREND as never);
  vi.mocked(fetchFormAnomalyFlags).mockResolvedValue(FLAGS as never);
  vi.mocked(fetchRaceReadiness).mockResolvedValue(READINESS as never);
  vi.mocked(fetchGoal).mockResolvedValue(GOAL as never);
  vi.mocked(fetchActivities).mockResolvedValue(ACTIVITIES as never);
}

function renderDashboard() {
  return render(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("Dashboard", () => {
  it("renders 状態 → 行動 → 進捗 sections from the mocked APIs", async () => {
    mockAll();
    renderDashboard();

    // ① 状態: verdict hero + snapshot tiles
    expect(await screen.findByText("イージー推奨")).toBeInTheDocument();
    expect(await screen.findByText("1.02")).toBeInTheDocument();
    // ② 行動: this week's plan and next action
    expect(await screen.findByText("Long Run")).toBeInTheDocument();
    expect(screen.getByText("ロング走は時間×HRで管理")).toBeInTheDocument();
    // ③ 進捗: race strip + recent runs
    expect(screen.getByText("レースへの道")).toBeInTheDocument();
    expect(screen.getByText("イージーラン")).toBeInTheDocument();
  });

  it("keeps the page alive when supplementary endpoints fail", async () => {
    mockAll();
    vi.mocked(fetchRaceReadiness).mockRejectedValue(new Error("boom"));
    vi.mocked(fetchGoal).mockRejectedValue(new Error("boom"));
    vi.mocked(fetchWellnessBaselineDeviation).mockRejectedValue(
      new Error("boom"),
    );
    renderDashboard();

    expect(await screen.findByText("イージー推奨")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    // Race strip degrades away without an error banner.
    expect(screen.queryByText("レースへの道")).not.toBeInTheDocument();
  });

  it("shows the error banner when a core endpoint fails", async () => {
    mockAll();
    vi.mocked(fetchRecoveryStatus).mockRejectedValue(new Error("db down"));
    renderDashboard();

    expect(await screen.findByRole("alert")).toHaveTextContent("db down");
  });
});
