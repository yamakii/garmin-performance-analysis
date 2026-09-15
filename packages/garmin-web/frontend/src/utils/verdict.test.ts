import { describe, expect, it } from "vitest";
import { makeMonthPlan } from "../test/planFixture";
import type { TrendNarration } from "../api/trends";
import type { Prescription, RecoveryStatus } from "../types";
import {
  homeVerdict,
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

describe("todayPrescription", () => {
  it("test_today_prescription_picks_today_row", () => {
    const week = makeMonthPlan().weeks[1];

    expect(todayPrescription(week, "2026-09-13")?.prescription_id).toBe(2);
    expect(todayPrescription(week, "2026-09-12")).toBeNull();
    expect(todayPrescription(null, "2026-09-13")).toBeNull();
  });
});
