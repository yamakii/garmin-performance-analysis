/**
 * @vitest-environment node
 */
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { fetchDurabilityTrend } from "../api/durability";
import {
  formatBpm,
  formatBpmValue,
  formatDate,
  formatDateTime,
  formatDistanceKm,
  formatDistanceKmValue,
  formatDuration,
  formatFullDateLabel,
  formatPace,
  formatIntensityShare,
  formatPaceValue,
  formatSleepDuration,
  formatTimeOfDay,
  humanizeKey,
  toIsoDate,
  weekEndIso,
} from "./format";

const SRC_DIR = fileURLToPath(new URL("..", import.meta.url));

/**
 * The date bugs this module exists to prevent only show up east of Greenwich,
 * and CI runs in UTC. Node applies a `process.env.TZ` change at runtime, so the
 * suite pins JST and restores whatever the host had.
 */
const ORIGINAL_TZ = process.env.TZ;
beforeAll(() => {
  process.env.TZ = "Asia/Tokyo";
});
afterAll(() => {
  process.env.TZ = ORIGINAL_TZ;
});

describe("pace / distance / bpm", () => {
  it("formats pace with and without its unit", () => {
    expect(formatPace(386)).toBe("6:26/km");
    expect(formatPaceValue(386)).toBe("6:26");
    // 59.6s rounds to 60 and carries into the minute rather than showing ":60".
    expect(formatPace(359.6)).toBe("6:00/km");
    expect(formatPace(null)).toBe("-");
    expect(formatPace(0)).toBe("-");
  });

  it("formats distance at two decimals by default, one on request", () => {
    expect(formatDistanceKm(15.041)).toBe("15.04 km");
    expect(formatDistanceKm(42.53333, 1)).toBe("42.5 km");
    expect(formatDistanceKmValue(15.041)).toBe("15.04");
    expect(formatDistanceKm(null)).toBe("-");
  });

  it("formats heart rate as whole beats", () => {
    expect(formatBpm(144.4)).toBe("144 bpm");
    expect(formatBpmValue(144.4)).toBe("144");
    expect(formatBpm(null)).toBe("-");
  });

  it("formats duration as mm:ss under an hour and h:mm:ss over it", () => {
    expect(formatDuration(2186)).toBe("36:26");
    expect(formatDuration(3733)).toBe("1:02:13");
    expect(formatDuration(null)).toBe("-");
  });

  it("test_format_sleep_duration", () => {
    // A night is read in hours and minutes, not in a run's h:mm:ss (#1153).
    expect(formatSleepDuration(25920)).toBe("7時間12分");
    // A whole hour still names its minutes, so the column stays one shape.
    expect(formatSleepDuration(3600)).toBe("1時間0分");
    expect(formatSleepDuration(null)).toBe("—");
  });
});

describe("dates", () => {
  it("keeps a plain calendar day and trims a datetime to its day", () => {
    expect(formatDate("2026-08-08")).toBe("2026-08-08");
    expect(formatDate("2026-08-08T09:00:00")).toBe("2026-08-08");
    expect(formatDate(null)).toBe("-");
  });

  it("renders a datetime without the ISO separator or seconds", () => {
    expect(formatDateTime("2026-06-22T09:00:00")).toBe("2026-06-22 09:00");
    expect(formatDateTime("2026-06-22 09:00:00")).toBe("2026-06-22 09:00");
    // Date-only stamps degrade to the day rather than inventing a time.
    expect(formatDateTime("2026-06-22")).toBe("2026-06-22");
  });

  /**
   * `toISOString()` reports the UTC day; before 09:00 JST that is yesterday.
   * Every date bound the app sends must be the local calendar day (#915).
   */
  it("test_to_iso_date_local_not_utc", () => {
    const jstMorning = new Date("2026-08-09T08:00:00+09:00");

    expect(toIsoDate(jstMorning)).toBe("2026-08-09");
    // The instant really is the previous UTC day — i.e. the old implementation
    // would have returned "2026-08-08" here.
    expect(jstMorning.toISOString().slice(0, 10)).toBe("2026-08-08");
  });

  /**
   * The suite runs under JST, so a week end derived from local time would slip
   * a day; the helper stays on `Date.UTC` for exactly that reason (#931).
   */
  it("test_weekEndIso_adds_six_days", () => {
    expect(weekEndIso("2026-08-10")).toBe("2026-08-16");
    // The end rolls into the next month, and the next year, on its own.
    expect(weekEndIso("2026-08-28")).toBe("2026-09-03");
    expect(weekEndIso("2026-12-28")).toBe("2027-01-03");
    // A stored datetime is accepted; only its calendar day matters.
    expect(weekEndIso("2026-08-10T00:00:00")).toBe("2026-08-16");
  });

  it("test_format_full_date_label", () => {
    // The report header reads "YYYY-MM-DD DDD", the same shape as the site
    // header (#1118); the weekday is a calendar fact, not a local instant.
    expect(formatFullDateLabel("2025-10-09")).toBe("2025-10-09 THU");
    expect(formatFullDateLabel("2025-10-09T06:12:00")).toBe("2025-10-09 THU");
    expect(formatFullDateLabel(null)).toBe("-");
    // Unparseable input is shown rather than hidden.
    expect(formatFullDateLabel("not-a-date")).toBe("not-a-date");
  });

  it("test_format_time_of_day", () => {
    // The header line names when the run started; a date without a time gets
    // no placeholder at all (#1153).
    expect(formatTimeOfDay("2026-09-13 13:45:19")).toBe("13:45");
    expect(formatTimeOfDay("2026-09-13T06:12:00")).toBe("06:12");
    expect(formatTimeOfDay("2026-09-13")).toBeNull();
    expect(formatTimeOfDay(null)).toBeNull();
  });

  it("test_weekEndIso_invalid_returns_null", () => {
    expect(weekEndIso(null)).toBeNull();
    expect(weekEndIso(undefined)).toBeNull();
    expect(weekEndIso("")).toBeNull();
    expect(weekEndIso("not-a-date")).toBeNull();
    // A day that does not exist must not be rolled over into a real one.
    expect(weekEndIso("2026-02-30")).toBeNull();
  });
});

describe("humanizeKey", () => {
  it("test_fallback_fields_humanized", () => {
    expect(humanizeKey("easy_z1_z2")).toBe("easy z1 z2");
    expect(humanizeKey("next-run-target")).toBe("next run target");
    expect(humanizeKey("easy_z1_z2")).not.toContain("_");
  });
});

describe("formatIntensityShare", () => {
  it("test_format_intensity_share", () => {
    // A saved distribution is a fraction of the week, so the card reads it as
    // a percentage under a Japanese label — not "aerobic base: 0.5" (#1144).
    expect(formatIntensityShare("aerobic_base", 0.5)).toBe("有酸素ベース 50%");
    expect(formatIntensityShare("tempo", 0.25)).toBe("テンポ 25%");
    expect(formatIntensityShare("long", 0.25)).toBe("ロング 25%");
    // An unknown bucket still loses its underscores.
    expect(formatIntensityShare("foo_bar", 0.1)).toBe("foo bar 10%");
  });

  it("keeps an out-of-range value as a plain number", () => {
    // Older payloads stored run counts rather than shares: 4 runs is not 400%.
    expect(formatIntensityShare("easy_z1_z2", 4)).toBe("イージー（Z1-Z2） 4");
    // The boundary is still read as a share — a whole week of one bucket.
    expect(formatIntensityShare("long_run", 1)).toBe("ロング 100%");
  });
});

describe("fetchDurabilityTrend", () => {
  const REAL_FETCH = globalThis.fetch;
  afterEach(() => {
    globalThis.fetch = REAL_FETCH;
  });

  /** Captures the requested URL and returns an empty trend payload. */
  function stubFetch(): { calls: string[] } {
    const calls: string[] = [];
    globalThis.fetch = ((input: RequestInfo | URL) => {
      calls.push(String(input));
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ points: [] }),
      } as Response);
    }) as typeof fetch;
    return { calls };
  }

  it("test_durability_uses_local_iso", async () => {
    const { calls } = stubFetch();
    // 08:30 JST on 2026-08-09 — still 2026-08-08 in UTC.
    const jstMorning = new Date("2026-08-09T08:30:00+09:00");

    await fetchDurabilityTrend(180, jstMorning);

    const query = new URL(calls[0], "http://localhost").searchParams;
    expect(query.get("end_date")).toBe("2026-08-09");
    expect(query.get("start_date")).toBe("2026-02-10");
  });

  it("no longer derives the window from the UTC day", () => {
    const source = readFileSync(join(SRC_DIR, "api/durability.ts"), "utf8");
    expect(source).not.toContain("toISOString");
    expect(source).toContain("toIsoDate");
  });
});

/** Every non-test source file, i.e. everywhere a value gets formatted. */
function sources(): { path: string; text: string }[] {
  return readdirSync(SRC_DIR, { recursive: true, encoding: "utf8" })
    .filter(
      (entry) =>
        (entry.endsWith(".ts") || entry.endsWith(".tsx")) &&
        !entry.includes(".test."),
    )
    .map((entry) => ({
      path: entry,
      text: readFileSync(join(SRC_DIR, entry), "utf8"),
    }));
}

describe("formatter usage", () => {
  /**
   * Two pages used to call `formatDistance(...).replace(" km", "")` to get the
   * bare number back so they could typeset the unit themselves. Stripping a
   * unit off a formatted string silently breaks the moment the formatter
   * changes; the unit-less `formatXValue` variants exist for that layout.
   */
  it("test_no_unit_strip_hack", () => {
    const offenders = sources().filter(
      ({ text }) =>
        text.includes('replace("/km"') ||
        text.includes('replace(" km"') ||
        text.includes('replace(" bpm"'),
    );

    expect(offenders.map((o) => o.path)).toEqual([]);
  });

  /** The local-date helper has exactly one definition (#915). */
  it("defines toIsoDate only in utils/format", () => {
    const definitions = sources().filter(
      ({ text }) =>
        /function toIsoDate\b/.test(text) || /function isoDate\b/.test(text),
    );

    expect(definitions.map((d) => d.path)).toEqual(["utils/format.ts"]);
  });
});
