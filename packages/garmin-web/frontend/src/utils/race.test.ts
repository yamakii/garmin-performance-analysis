import { describe, expect, it } from "vitest";
import { daysUntil, formatGap, formatTargetTime } from "./race";

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
