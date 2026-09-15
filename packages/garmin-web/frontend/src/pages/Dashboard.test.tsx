import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "../test/utils";
import { toIsoDate, weekEndIso } from "../utils/format";
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
  fetchMonthPlan: vi.fn(),
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
  fetchMonthPlan,
  fetchRaceReadiness,
  fetchWeeklyReviews,
} from "../api/client";
import {
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
    star_rating: "★★★★☆ 4.2/5.0",
    summary_lead: "有酸素ベースとして安定しました。",
  },
];

/**
 * A plan week built around the real "today", so the verdict, the TODAY cell
 * and the week caption are all exercised without pinning the clock.
 */
function makeCurrentWeek() {
  const today = new Date();
  const weekStart = new Date(today);
  weekStart.setDate(weekStart.getDate() - 3);
  const weekStartIso = toIsoDate(weekStart);
  const todayIso = toIsoDate(today);
  const days = Array.from({ length: 7 }, (_, offset) => {
    const day = new Date(weekStart);
    day.setDate(day.getDate() + offset);
    const date = toIsoDate(day);
    return {
      date,
      in_month: true,
      prescriptions:
        date === todayIso
          ? [
              {
                prescription_id: 1,
                session_type: "easy",
                title: "イージー 10km",
                target_km: 10,
                target_minutes: null,
                hr_high: 145,
                status: "prescribed",
              },
            ]
          : [],
      activities: [],
    };
  });
  return {
    week_start: weekStartIso,
    week_end: weekEndIso(weekStartIso) ?? todayIso,
    in_month: true,
    ladder_step: null,
    review_exists: true,
    adherence: { prescribed: 1, done: 0, replaced: 0, skipped: 0, pending: 1 },
    days,
  };
}

const CURRENT_WEEK = makeCurrentWeek();

const MONTH_PLAN = {
  month: CURRENT_WEEK.week_start.slice(0, 7),
  week_start_day: 0,
  weeks: [CURRENT_WEEK],
  blocks: [],
  adherence: { prescribed: 1, done: 0, replaced: 0, skipped: 0, pending: 1 },
};

const REVIEW = {
  review_id: 24,
  user_id: "default",
  week_start_date: CURRENT_WEEK.week_start,
  week_end_date: CURRENT_WEEK.week_end,
  review_date: CURRENT_WEEK.week_start,
  review_data: {
    recommendations: ["ロング走は時間×HRで管理"],
  },
  created_at: CURRENT_WEEK.week_start,
  agent_name: "weekly-review",
  agent_version: "1.3",
};

function mockAll() {
  vi.mocked(fetchMonthPlan).mockResolvedValue(MONTH_PLAN as never);
  vi.mocked(fetchRecoveryStatus).mockResolvedValue(RECOVERY_STATUS as never);
  vi.mocked(fetchWellnessBaselineDeviation).mockResolvedValue(
    BASELINE as never,
  );
  vi.mocked(fetchWeeklyReviews).mockResolvedValue([REVIEW] as never);
  vi.mocked(fetchTrainingLoad).mockResolvedValue(LOAD as never);
  vi.mocked(fetchRecoveryTrend).mockResolvedValue(RECOVERY_TREND as never);
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
  it("test_dashboard_renders_all_blocks_on_success", async () => {
    mockAll();
    renderDashboard();

    // ① 判定: the verdict is the page heading and carries today's session.
    expect(await screen.findByText("イージー推奨。")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "イージー推奨。今日はイージー 10km、心拍 145 以下。",
    );
    expect(
      screen.getByText("HRVが2夜連続でベースラインを下回っています"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "今日のメニュー詳細" }),
    ).toHaveAttribute("href", "/plan");

    // ② 今朝の数値: four readings, each linked into /condition.
    expect(await screen.findByText("HRV 夜間")).toBeInTheDocument();
    expect(screen.getByText("安静時心拍")).toBeInTheDocument();
    expect(screen.getByText("睡眠 / 準備度")).toBeInTheDocument();
    expect(screen.getByText("負荷 ACWR")).toBeInTheDocument();
    expect(screen.getByText("1.02")).toBeInTheDocument();
    expect(screen.getByText("基準割れ 2日連続")).toHaveClass(
      "text-status-warn",
    );
    expect(screen.getByText("最適 · 週 6.5km")).toBeInTheDocument();

    // ③ 今週: the 7-day strip with today highlighted, plus the coach note.
    expect(
      await screen.findByRole("heading", { level: 2, name: "今週" }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(7);
    expect(screen.getByText("TODAY")).toBeInTheDocument();
    expect(screen.getByText("ロング走は時間×HRで管理")).toBeInTheDocument();

    // ④ 進捗: the featured race and the last run.
    expect(
      await screen.findByText("さいたまマラソン · A"),
    ).toBeInTheDocument();
    expect(screen.getByText(/前回 · 06\/30 TUE · イージーラン/)).toBeInTheDocument();
    // The last run's verdict, joined in from its latest summary section (#1131).
    expect(screen.getByLabelText("評価 4.2 / 5.0")).toBeInTheDocument();
    expect(
      screen.getByText(/有酸素ベースとして安定しました。/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "すべてのラン →" }),
    ).toBeInTheDocument();
  });

  it("test_dashboard_no_duplicate_vitals", async () => {
    mockAll();
    renderDashboard();

    // The HRV reading is stated once: the hero chips and the tile row that
    // used to repeat it are gone (#1117).
    expect(await screen.findByText("51")).toBeInTheDocument();
    expect(screen.getAllByText("51")).toHaveLength(1);
  });

  it("keeps the page alive when supplementary endpoints fail", async () => {
    mockAll();
    vi.mocked(fetchRaceReadiness).mockRejectedValue(new Error("boom"));
    vi.mocked(fetchGoal).mockRejectedValue(new Error("boom"));
    vi.mocked(fetchWellnessBaselineDeviation).mockRejectedValue(
      new Error("boom"),
    );
    renderDashboard();

    expect(await screen.findByText("イージー推奨。")).toBeInTheDocument();
    expect(await screen.findByText("HRV 夜間")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    // The race column degrades away; the last run still renders.
    expect(screen.queryByText("さいたまマラソン · A")).not.toBeInTheDocument();
    expect(
      await screen.findByText(/前回 · 06\/30 TUE · イージーラン/),
    ).toBeInTheDocument();
  });

  it("test_dashboard_card_error_isolated", async () => {
    mockAll();
    vi.mocked(fetchTrainingLoad).mockRejectedValue(new Error("db down"));
    renderDashboard();

    // The failing endpoint degrades into a retryable alert in place of the
    // vitals row…
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(
      "今朝の数値の読み込みに失敗しました: db down",
    );
    expect(alert).toHaveClass("bg-bad-tint");
    expect(screen.getByRole("button", { name: "再試行" })).toBeInTheDocument();

    // …while every other block still renders (no page-level banner).
    expect(await screen.findByText("イージー推奨。")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "今週" })).toBeInTheDocument();
    expect(
      await screen.findByText(/前回 · 06\/30 TUE · イージーラン/),
    ).toBeInTheDocument();
    expect(screen.queryByText("HRV 夜間")).not.toBeInTheDocument();
  });
});
