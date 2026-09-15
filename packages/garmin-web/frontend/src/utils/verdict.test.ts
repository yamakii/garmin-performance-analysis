import { describe, expect, it } from "vitest";
import { makeMonthPlan } from "../test/planFixture";
import type { TrendNarration } from "../api/trends";
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
  isBehindTarget,
  performanceVerdict,
  todayPrescription,
  type PerformanceKpis,
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
    sleep_seconds: 25920,
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

const NARRATION: TrendNarration = {
  granularity: "week",
  period_start: "2026-09-07",
  period_end: "2026-09-13",
  analysis_data: { narrative: "今週は積み上げが続いています。" },
  created_at: "2026-09-14 09:00:00",
};

function kpis(overrides: Partial<PerformanceKpis> = {}): PerformanceKpis {
  return {
    objectiveVdot: null,
    vdotDelta4w: null,
    ef: null,
    efDeltaPct4w: null,
    decouplingPct: null,
    ...overrides,
  };
}

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

describe("performanceVerdict", () => {
  it("test_performance_verdict_improving", () => {
    expect(
      performanceVerdict(
        NARRATION,
        kpis({ vdotDelta4w: 0.8, efDeltaPct4w: 3 }),
      ),
    ).toEqual({
      verdict: "速くなっている。",
      tone: "neutral",
      rest: "4週で客観VDOT +0.8 · EF +3.0%。",
    });

    const declining = performanceVerdict(
      NARRATION,
      kpis({ vdotDelta4w: -0.5 }),
    );
    expect(declining.verdict).toBe("落ちている。");
    expect(declining.tone).toBe("warn");

    // No numbers at all: the page still has prose, so it says the numbers are
    // missing rather than claiming a direction.
    expect(performanceVerdict(NARRATION, kpis())).toEqual({
      verdict: "停滞。",
      tone: "neutral",
      rest: "判断材料が不足。",
    });
    // Neither numbers nor prose: nothing has been generated yet.
    expect(performanceVerdict(null, kpis()).rest).toBe(
      "データがまだありません。",
    );
  });

  it("reads moves inside the noise band as 停滞", () => {
    expect(
      performanceVerdict(NARRATION, kpis({ vdotDelta4w: 0.2, efDeltaPct4w: 1 }))
        .verdict,
    ).toBe("停滞。");
    // Disagreeing measures establish nothing either.
    expect(
      performanceVerdict(
        NARRATION,
        kpis({ vdotDelta4w: 0.8, efDeltaPct4w: -3 }),
      ).verdict,
    ).toBe("停滞。");
  });

  it("names the decoupling reading among the evidence", () => {
    expect(
      performanceVerdict(NARRATION, kpis({ decouplingPct: 4.25 })).rest,
    ).toBe("デカップリング 4.3%。");
  });
});

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
    vdot_source: "objective",
    predicted_times: { full: progress?.predicted_time_seconds ?? 0 },
    goal: null,
    progress,
  };
}

describe("goalVerdict", () => {
  it("test_goal_verdict_on_track", () => {
    // Inside the backend's ±60 s band, so the prediction trails the target by
    // half a minute and the plan is still on schedule.
    const verdict = goalVerdict(
      readiness({
        predicted_time_seconds: 12030, // 3:20:30
        gap_seconds: 30,
        pace_gap_sec_per_km: 0.7,
        weeks_remaining: 10,
        status: "on_track",
      }),
      goalRace(),
      TODAY,
    );

    expect(verdict.verdict).toBe("目標 3:20:00 に対して予測 3:20:30。");
    expect(verdict.rest).toBe("あと 76 日、順調。差 +0:30。");
    // 順調 and a warning colour would contradict each other (#1151).
    expect(verdict.tone).toBe("neutral");
  });

  it("test_goal_verdict_behind", () => {
    const verdict = goalVerdict(
      readiness({
        predicted_time_seconds: 12600, // 3:30:00
        gap_seconds: 600,
        pace_gap_sec_per_km: 14.2,
        weeks_remaining: 10,
        status: "behind",
      }),
      goalRace(),
      TODAY,
    );

    expect(verdict.rest).toBe("あと 76 日、遅れ。差 +10:00。");
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

  it("test_goal_verdict_ahead", () => {
    // The live 2026-09-15 figures: an hour inside a 4:30:00 target.
    const verdict = goalVerdict(
      readiness({
        predicted_time_seconds: 12589, // 3:29:49
        gap_seconds: -3611,
        pace_gap_sec_per_km: -85.6,
        weeks_remaining: 10,
        status: "ahead",
      }),
      goalRace({ target_time_seconds: 16200 }),
      TODAY,
    );

    expect(verdict.rest).toBe("あと 76 日、前倒し。差 −1:00:11。");
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

describe("isBehindTarget", () => {
  it("test_is_behind_target", () => {
    expect(
      isBehindTarget({
        predicted_time_seconds: 12600,
        gap_seconds: 600,
        pace_gap_sec_per_km: 14.2,
        weeks_remaining: 10,
        status: "behind",
      }),
    ).toBe(true);

    // A positive gap inside the on-track band is not a warning.
    expect(
      isBehindTarget({
        predicted_time_seconds: 12030,
        gap_seconds: 30,
        pace_gap_sec_per_km: 0.7,
        weeks_remaining: 10,
        status: "on_track",
      }),
    ).toBe(false);

    expect(
      isBehindTarget({
        predicted_time_seconds: 12589,
        gap_seconds: -3611,
        pace_gap_sec_per_km: -85.6,
        weeks_remaining: 10,
        status: "ahead",
      }),
    ).toBe(false);

    expect(isBehindTarget(null)).toBe(false);
    expect(isBehindTarget(undefined)).toBe(false);
  });
});
