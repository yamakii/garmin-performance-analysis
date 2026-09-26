import { describe, expect, it } from "vitest";
import { PICTOGRAPH_RE } from "../utils/emoji";

/**
 * Source guard (#1428): no component, page or util spells an emoji.
 *
 * The design system states verdicts in words or the `✓` / `!` glyphs
 * (#1186 / #1187 / #1188). Each of those fixes was local, so the next surface
 * brought the emoji back (#1407's plan card steps). Scanning the source makes
 * that a failing test instead of a screenshot. Comments count too: a comment
 * that says "a ✅ badge" is how the next badge gets written.
 *
 * `verdictRating.ts` is the one exception -- it is the table that turns the
 * stored `rating` key into its word, so it has to spell the marks it matches.
 */
const ALLOWED = new Set(["../utils/verdictRating.ts"]);

const SOURCES = import.meta.glob<string>(
  ["../**/*.{ts,tsx}", "!../**/*.test.{ts,tsx}", "!../test/**"],
  { query: "?raw", import: "default", eager: true },
);

const LINE_RE = new RegExp(PICTOGRAPH_RE.source, "u");

describe("source guard", () => {
  it("scans the app sources", () => {
    // A glob that silently matched nothing would pass the guard below.
    expect(Object.keys(SOURCES).length).toBeGreaterThan(50);
    expect(Object.keys(SOURCES)).toContain("../components/run/PlanCheck.tsx");
  });

  it("test_no_pictographs_in_source", () => {
    const offenders: string[] = [];
    for (const [path, text] of Object.entries(SOURCES)) {
      if (ALLOWED.has(path)) continue;
      text.split("\n").forEach((line, index) => {
        if (LINE_RE.test(line)) {
          offenders.push(`${path.slice(3)}:${index + 1}: ${line.trim()}`);
        }
      });
    }
    expect(
      offenders,
      "write the word (良好 / 注意 / 要改善, 計画どおり / ずれ) or ✓ / ! instead",
    ).toEqual([]);
  });
});
