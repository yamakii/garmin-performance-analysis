import { afterAll, beforeAll, describe, expect, it } from "vitest";
import {
  dayOfMonthLabel,
  formatDayLabel,
  formatMonthLabel,
  shiftMonth,
  weekRowLabel,
  weekRowsForMonth,
  weekdayLabels,
} from "./week";

/**
 * Week boundaries are calendar facts. CI runs in UTC, so pin JST here: a row
 * that leaks through a local timezone lands a day early east of Greenwich.
 */
const ORIGINAL_TZ = process.env.TZ;
beforeAll(() => {
  process.env.TZ = "Asia/Tokyo";
});
afterAll(() => {
  process.env.TZ = ORIGINAL_TZ;
});

describe("weekRowsForMonth", () => {
  it("test_week_rows_for_month_monday_start", () => {
    // 2026-09-01 is a Tuesday, so a Monday-start grid opens on 2026-08-31.
    const rows = weekRowsForMonth("2026-09", 0);

    expect(rows).toHaveLength(5);
    expect(rows[0].weekStart).toBe("2026-08-31");
    expect(rows[0].days).toEqual([
      "2026-08-31",
      "2026-09-01",
      "2026-09-02",
      "2026-09-03",
      "2026-09-04",
      "2026-09-05",
      "2026-09-06",
    ]);
    expect(rows.every((row) => row.days.length === 7)).toBe(true);
    // The last row carries the month's tail plus its October spill.
    expect(rows[4].days[6]).toBe("2026-10-04");
  });

  it("test_week_rows_for_month_sunday_start", () => {
    const rows = weekRowsForMonth("2026-09", 6);

    expect(rows[0].weekStart).toBe("2026-08-30");
    expect(rows[0].days[6]).toBe("2026-09-05");
  });

  it("returns no rows for a malformed month", () => {
    expect(weekRowsForMonth("2026-9", 0)).toEqual([]);
    expect(weekRowsForMonth("", 0)).toEqual([]);
  });
});

describe("weekdayLabels", () => {
  it("orders the header from the configured start day", () => {
    expect(weekdayLabels(0)).toEqual(["月", "火", "水", "木", "金", "土", "日"]);
    expect(weekdayLabels(6)).toEqual(["日", "月", "火", "水", "木", "金", "土"]);
    // An out-of-range value degrades to Monday instead of shifting off-grid.
    expect(weekdayLabels(9)[0]).toBe("月");
  });
});

describe("day labels", () => {
  it("formats a day as MM/DD (曜)", () => {
    expect(formatDayLabel("2026-09-13")).toBe("09/13 (日)");
    expect(formatDayLabel("not-a-date")).toBe("not-a-date");
  });

  it("formats the day of month without a leading zero", () => {
    expect(dayOfMonthLabel("2026-09-01")).toBe("1");
    expect(dayOfMonthLabel("2026-09-13")).toBe("13");
  });
});

describe("month helpers", () => {
  it("shifts across year boundaries", () => {
    expect(shiftMonth("2026-09", -1)).toBe("2026-08");
    expect(shiftMonth("2026-12", 1)).toBe("2027-01");
    expect(shiftMonth("2026-01", -1)).toBe("2025-12");
    expect(shiftMonth("bad", 1)).toBe("bad");
  });

  it("labels a month in Japanese", () => {
    expect(formatMonthLabel("2026-09")).toBe("2026年9月");
    expect(formatMonthLabel("bad")).toBe("bad");
  });

  it("labels a week row by its start day", () => {
    expect(weekRowLabel("2026-09-07")).toBe("9/7週");
    expect(weekRowLabel("bad")).toBe("bad");
  });
});
