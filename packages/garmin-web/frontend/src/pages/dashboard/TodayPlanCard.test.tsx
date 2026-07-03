import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ActivitySummary, PlannedWorkoutToday } from "../../types";
import { TodayPlanCard } from "./TodayPlanCard";

// The card reads its data through these two hooks; mock them so each test can
// stage a planned / actual combination synchronously.
const { usePlannedWorkoutToday, useActivities } = vi.hoisted(() => ({
  usePlannedWorkoutToday: vi.fn(),
  useActivities: vi.fn(),
}));

vi.mock("../../api/hooks", () => ({ usePlannedWorkoutToday, useActivities }));

const DATE = "2026-07-02";

const PLANNED: PlannedWorkoutToday = {
  workout_id: "w-1",
  workout_type: "tempo",
  description_ja: "テンポ走 6km",
  target_distance_km: 6.0,
  target_pace_low: 300, // 5:00/km
  target_pace_high: 320, // 5:20/km
  target_hr_low: 150,
  target_hr_high: 165,
  actual_activity_id: null,
  adherence_score: null,
};

const ACTUAL: ActivitySummary = {
  activity_id: 111,
  activity_date: DATE,
  activity_name: "Tempo Run",
  total_distance_km: 6.1,
  total_time_seconds: 1860,
  avg_pace_seconds_per_km: 305, // 5:05/km — inside the 5:00〜5:20 band
  avg_heart_rate: 158, // inside 150〜165
};

function stub(
  planned: PlannedWorkoutToday | null,
  activities: ActivitySummary[],
) {
  usePlannedWorkoutToday.mockReturnValue({ data: planned, isLoading: false });
  useActivities.mockReturnValue({ data: activities, isLoading: false });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("TodayPlanCard", () => {
  it("予定と実績の対比を表示する", () => {
    stub(PLANNED, [ACTUAL]);
    render(<TodayPlanCard date={DATE} />);

    // Target band and actual pace both rendered.
    expect(screen.getByText("目標 5:00〜5:20/km")).toBeInTheDocument();
    expect(screen.getByText("実績 5:05/km")).toBeInTheDocument();
    // Actual is inside every band -> 達成 badge.
    expect(screen.getByText("達成")).toBeInTheDocument();
  });

  it("実績なしは予定のみ表示する", () => {
    stub(PLANNED, []); // no activity for the day
    render(<TodayPlanCard date={DATE} />);

    expect(screen.getByText("本日の予定")).toBeInTheDocument();
    expect(screen.getByText("テンポ走 6km")).toBeInTheDocument();
    expect(screen.getByText("目標 5:00〜5:20/km")).toBeInTheDocument();
    // No actual column when the run has not happened (the heading's 予定と実績
    // has no trailing value, so match only "実績 <value>").
    expect(screen.queryByText(/実績 /)).not.toBeInTheDocument();
  });

  it("予定なしは休養日と表示する", () => {
    stub(null, []);
    render(<TodayPlanCard date={DATE} />);

    expect(screen.getByText("休養日")).toBeInTheDocument();
    expect(
      screen.getByText("本日の予定はありません。休養日です。"),
    ).toBeInTheDocument();
  });

  it("目標を外すと未達バッジを表示する", () => {
    // Ran well outside the pace band (way too slow) -> 未達.
    stub(PLANNED, [{ ...ACTUAL, avg_pace_seconds_per_km: 420 }]);
    render(<TodayPlanCard date={DATE} />);

    expect(screen.getByText("未達")).toBeInTheDocument();
  });
});
