import { describe, expect, it } from "vitest";
import { makeMonthPlan } from "../test/planFixture";
import type { MonthPlan } from "../types";
import { monthSentence, monthSummary } from "./planSummary";

describe("monthSummary", () => {
  it("test_month_summary_counts", () => {
    const summary = monthSummary(makeMonthPlan(), "2026-09-13");

    // Six prescriptions inside September: four done, one skipped (9/18, still
    // ahead of the reader on 9/13) and the 9/20 long run still pending.
    expect(summary.prescribed).toBe(6);
    expect(summary.done).toBe(4);
    expect(summary.replaced).toBe(0);
    expect(summary.late).toBe(0);
    expect(summary.resolved).toBe(5);
    expect(summary.plannedKm).toBe(75);
    expect(summary.actualKm).toBe(21.4);
    // The block the month sits in: 08/24 – 10/11, 2 quality sessions a week.
    expect(summary.phase).toBe("ビルド");
    expect(summary.weekIndex).toBe(3);
    expect(summary.weekTotal).toBe(7);
    expect(summary.qualityPerWeek).toBe(2);
    // 9/13's long run is already run; the next one is the 9/20 25km.
    expect(summary.nextLongKm).toBe(25);
  });

  it("counts a session as late only once its day is behind the reader", () => {
    const summary = monthSummary(makeMonthPlan(), "2026-09-21");

    // The 9/18 easy run was skipped and is now in the past.
    expect(summary.late).toBe(1);
  });

  it("anchors the phase to the month when it is not the current one", () => {
    // Reading September in December still describes September's block week.
    const summary = monthSummary(makeMonthPlan(), "2026-12-01");

    expect(summary.weekIndex).toBe(2);
    expect(summary.late).toBe(1);
  });

  it("reports an unplanned month without a block", () => {
    const plan: MonthPlan = { ...makeMonthPlan(), weeks: [], blocks: [] };
    const summary = monthSummary(plan, "2026-09-13");

    expect(summary.prescribed).toBe(0);
    expect(summary.phase).toBeNull();
    expect(summary.weekIndex).toBeNull();
    expect(summary.nextLongKm).toBeNull();
  });
});

describe("monthSentence", () => {
  it("test_month_sentence", () => {
    const sentence = monthSentence(monthSummary(makeMonthPlan(), "2026-09-13"));

    expect(sentence.lead).toBe("ビルド期 3/7 週。");
    expect(sentence.rest).toContain("今月の処方 6 本のうち 4 本実施");
    expect(sentence.rest).toContain("遅れなし");
    expect(sentence.rest).toContain("次のロングは 25km。");
  });

  it("names the count of late sessions and drops an empty 代替 clause", () => {
    const sentence = monthSentence(monthSummary(makeMonthPlan(), "2026-09-21"));

    expect(sentence.rest).toContain("遅れ 1 本");
    expect(sentence.rest).not.toContain("代替");
  });

  it("says an unplanned month is unplanned instead of reporting 0/0", () => {
    const plan: MonthPlan = { ...makeMonthPlan(), weeks: [], blocks: [] };
    const sentence = monthSentence(monthSummary(plan, "2026-09-13"));

    expect(sentence.lead).toBe("");
    expect(sentence.rest).toBe("今月の処方はまだありません。");
  });
});
