import { describe, expect, it } from "vitest";
import type { GoalRace } from "../types";
import { toIsoDate } from "./format";
import {
  daysUntil,
  formatGap,
  formatTargetTime,
  pickFeaturedRace,
} from "./race";

/** A goal race `days` days from today, so the sort is clock-independent. */
function race(
  goal_id: number,
  priority: string | null,
  days: number | null,
): GoalRace {
  const date = new Date();
  date.setDate(date.getDate() + (days ?? 0));
  return {
    goal_id,
    race_name: `レース${goal_id}`,
    race_date: days == null ? null : toIsoDate(date),
    priority,
    goal_type: "marathon",
    distance_km: 42.195,
    target_time_seconds: 16200,
    status: "active",
    notes: null,
  };
}

describe("formatTargetTime", () => {
  it("formats seconds as H:MM:SS", () => {
    expect(formatTargetTime(16200)).toBe("4:30:00");
    expect(formatTargetTime(7200)).toBe("2:00:00");
    expect(formatTargetTime(null)).toBe("-");
  });
});

describe("daysUntil", () => {
  it("test_days_until_future_date", () => {
    const today = new Date(2026, 0, 1); // 2026-01-01 local
    expect(daysUntil("2026-01-11", today)).toBe(10);
    expect(daysUntil("2025-12-31", today)).toBe(-1);
    expect(daysUntil(null, today)).toBeNull();
    expect(daysUntil("not-a-date", today)).toBeNull();
  });
});

describe("pickFeaturedRace", () => {
  it("test_pick_featured_race", () => {
    const b = race(1, "B", 30);
    const a = race(2, "A", 120);

    // The A race wins even when a B race is sooner.
    expect(pickFeaturedRace([b, a])?.goal_id).toBe(2);
    // Without an A race, the nearest upcoming one carries the countdown.
    expect(pickFeaturedRace([b])?.goal_id).toBe(1);
    expect(pickFeaturedRace([])).toBeNull();
  });

  it("falls back to the first goal when every race has passed", () => {
    const past = race(3, "B", -10);
    const older = race(4, "C", -40);

    expect(pickFeaturedRace([past, older])?.goal_id).toBe(3);
  });
});

describe("formatGap", () => {
  it("test_format_gap_negative_is_ahead", () => {
    // A negative gap means the prediction is faster than the target, rendered
    // with the minus sign (U+2212) rather than a hyphen.
    expect(formatGap(-900)).toBe("−15:00");
    expect(formatGap(900)).toBe("+15:00");
    expect(formatGap(0)).toBe("±0:00");
    expect(formatGap(3661)).toBe("+1:01:01");
  });
});
