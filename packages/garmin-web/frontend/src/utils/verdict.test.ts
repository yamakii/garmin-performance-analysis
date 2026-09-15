import { describe, expect, it } from "vitest";
import { makeMonthPlan } from "../test/planFixture";
import type {
  FormAnomalyFlagsResponse,
  GoalRace,
  MetricBaseline,
  Prescription,
  RaceReadiness,
  RecoveryStatus,
  WellnessBaselineDeviation,
} from "../types";
import {
  conditionVerdict,
  goalVerdict,
  homeVerdict,
  todayPrescription,
} from "./verdict";

function status(
  recommendation: RecoveryStatus["recommendation"],
): RecoveryStatus {
  return {
    date: "2026-09-13",
    recommendation,
    score: 70,
    reasons: [],
    training_readiness: 70,
    body_battery_high: 80,
    sleep_score: 74,
  };
}

function prescription(overrides: Partial<Prescription> = {}): Prescription {
  return {
    prescription_id: 1,
    session_type: "easy",
    title: "イージー 10km",
    target_km: 10,
    target_minutes: null,
    hr_high: 145,
    status: "prescribed",
    ...overrides,
  };
}

describe("homeVerdict", () => {
  it("test_home_verdict_with_prescription", () => {
    expect(homeVerdict(status("moderate"), prescription())).toEqual({
      verdict: "通常ラン OK。",
      tone: "neutral",
      rest: "今日はイージー 10km、心拍 145 以下。",
    });
  });

  it("test_home_verdict_rest_tone", () => {
    const rest = homeVerdict(status("rest"), null);
    expect(rest.tone).toBe("bad");
    expect(rest.verdict).toBe("休養推奨。");
    expect(rest.rest).toBe("今日の処方はありません。");

    expect(homeVerdict(status("easy"), null).tone).toBe("warn");
    expect(homeVerdict(status("quality"), null).tone).toBe("neutral");
  });

  it("falls back to minutes and drops a missing HR ceiling", () => {
    expect(
      homeVerdict(
        status("quality"),
        prescription({
          session_type: "long",
          target_km: null,
          target_minutes: 150,
        }),
      ).rest,
    ).toBe("今日はロング 150分、心拍 145 以下。");

    expect(
      homeVerdict(status("quality"), prescription({ hr_high: null })).rest,
    ).toBe("今日はイージー 10km。");
  });

  it("says 休養日 for a prescribed rest day", () => {
    expect(
      homeVerdict(
        status("rest"),
        prescription({ session_type: "rest", target_km: null, hr_high: null }),
      ).rest,
    ).toBe("今日は休養日。");
  });
});

function metric(
  name: MetricBaseline["metric"],
  overrides: Partial<MetricBaseline> = {},
): MetricBaseline {
  return {
    metric: name,
    mean: 50,
    std: 4,
    today: 50,
    z: 0,
    flag: "within",
    adverse: false,
    n: 30,
    ...overrides,
  };
}

function baseline(
  overrides: Partial<WellnessBaselineDeviation> = {},
): WellnessBaselineDeviation {
  return {
    date: "2026-09-13",
    hrv: metric("hrv"),
    rhr: metric("rhr"),
    readiness: metric("readiness"),
    overall_flag: false,
    ...overrides,
  };
}

function flagsResponse(count: number): FormAnomalyFlagsResponse {
  return {
    weeks: 2,
    scanned: 6,
    limited: false,
    flags: Array.from({ length: count }, (_, index) => ({
      activity_id: index + 1,
      activity_date: "2026-09-12",
      anomalies_detected: 2,
      severity_high: 1,
      top_recommendation: "後半のGCT増加に注意してください。",
    })),
  };
}

describe("conditionVerdict", () => {
  it("test_condition_verdict_rhr_outside", () => {
    const verdict = conditionVerdict(
      status("moderate"),
      baseline({
        rhr: metric("rhr", { z: 1.8, flag: "high", adverse: true }),
      }),
      flagsResponse(1),
    );

    expect(verdict.verdict).toBe("回復はほぼ正常。");
    expect(verdict.tone).toBe("neutral");
    expect(verdict.rest).toContain("安静時心拍が基準外");
    expect(verdict.rest).toContain("1 件の注意点");
  });

  it("test_condition_verdict_rest", () => {
    const rest = conditionVerdict(status("rest"), null, null);
    expect(rest.verdict).toBe("回復不足。");
    expect(rest.tone).toBe("bad");
    // Nothing loaded is not an all-clear: the sentence simply stops.
    expect(rest.rest).toBe("");

    const easy = conditionVerdict(status("easy"), baseline(), flagsResponse(0));
    expect(easy.verdict).toBe("回復に注意。");
    expect(easy.tone).toBe("warn");
    expect(easy.rest).toBe("基準外の項目なし、注意点なし。");
  });
});

describe("todayPrescription", () => {
  it("test_today_prescription_picks_today_row", () => {
    const week = makeMonthPlan().weeks[1];

    expect(todayPrescription(week, "2026-09-13")?.prescription_id).toBe(2);
    expect(todayPrescription(week, "2026-09-12")).toBeNull();
    expect(todayPrescription(null, "2026-09-13")).toBeNull();
  });
});

/** 2026-09-15, so a race on 2026-11-30 is exactly 76 days out. */
const TODAY = new Date(2026, 8, 15);

/** The A race the goal page counts down to. */
function goalRace(overrides: Partial<GoalRace> = {}): GoalRace {
  return {
    goal_id: 1,
    race_name: "新潟マラソン",
    race_date: "2026-11-30",
    priority: "A",
    goal_type: "marathon",
    distance_km: 42.195,
    target_time_seconds: 12000, // 3:20:00
    status: "active",
    notes: null,
    ...overrides,
  };
}

function readiness(
  progress: RaceReadiness["progress"],
  currentVdot = 49.2,
): RaceReadiness {
  return {
    current_vdot: currentVdot,
    predicted_times: { full: progress?.predicted_time_seconds ?? 0 },
    goal: null,
    progress,
  };
}

describe("goalVerdict", () => {
  it("test_goal_verdict_on_track", () => {
    const verdict = goalVerdict(
      readiness({
        predicted_time_seconds: 12250, // 3:24:10
        gap_seconds: 250,
        pace_gap_sec_per_km: 5.9,
        weeks_remaining: 10,
        status: "on_track",
      }),
      goalRace(),
      TODAY,
    );

    expect(verdict.verdict).toBe("目標 3:20:00 に対して予測 3:24:10。");
    expect(verdict.rest).toBe("あと 76 日、順調。差 +4:10。");
    // The prediction still trails the target, so the line is marked even
    // though the status word says the plan is on schedule.
    expect(verdict.tone).toBe("warn");
  });

  it("test_goal_verdict_without_prediction", () => {
    expect(goalVerdict(null, goalRace(), TODAY)).toEqual({
      verdict: "目標 3:20:00。",
      tone: "neutral",
      rest: "あと 76 日。",
    });

    expect(goalVerdict(null, null, TODAY)).toEqual({
      verdict: "目標レース未登録。",
      tone: "neutral",
      rest: "",
    });
  });

  it("stays neutral when the prediction beats the target", () => {
    const verdict = goalVerdict(
      readiness({
        predicted_time_seconds: 11700, // 3:15:00
        gap_seconds: -300,
        pace_gap_sec_per_km: -7.1,
        weeks_remaining: 10,
        status: "ahead",
      }),
      goalRace(),
      TODAY,
    );

    expect(verdict.rest).toBe("あと 76 日、前倒し。差 −5:00。");
    expect(verdict.tone).toBe("neutral");
  });

  it("says so when the race has no date or no target", () => {
    expect(goalVerdict(null, goalRace({ race_date: null }), TODAY).rest).toBe(
      "日程未定。",
    );
    expect(
      goalVerdict(null, goalRace({ race_date: "2026-09-01" }), TODAY).rest,
    ).toBe("開催済み。");
    expect(
      goalVerdict(null, goalRace({ target_time_seconds: null }), TODAY).verdict,
    ).toBe("目標タイム未設定。");
  });
});
