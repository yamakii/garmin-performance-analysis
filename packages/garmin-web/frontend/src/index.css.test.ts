/**
 * @vitest-environment node
 */
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * Contrast regression guard for the palette (Issue #911).
 *
 * The audit in #910 measured every semantic token against its real background
 * and found four status tokens plus 36 muted-gray call sites below the WCAG
 * 2.1 AA 4.5:1 floor for body text. Both are one careless edit away from
 * coming back, and neither `tsc` nor eslint can see a contrast ratio — so the
 * ratios are recomputed here from the checked-in CSS rather than trusted to a
 * comment.
 */

const SRC_DIR = fileURLToPath(new URL(".", import.meta.url));
const INDEX_CSS = readFileSync(join(SRC_DIR, "index.css"), "utf8");

/** WCAG 2.1 SC 1.4.3 floor for body-sized text. */
const AA_TEXT = 4.5;

/** The muted gray that is never contrast-safe (2.63:1 on white). */
const BANNED_MUTED_GRAY = ["text", "slate", "400"].join("-");

/**
 * Surfaces any of these tokens can land on. Tailwind v4 ships the slate ramp
 * as oklch; these are the sRGB values those oklch triples resolve to
 * (`oklch(98.4% 0.003 247.858)` -> #f8fafc, `oklch(96.8% 0.007 247.896)` ->
 * #f1f5f9). slate-100 is the dark end of the `from-white via-slate-50
 * to-slate-100` hero gradients, i.e. the worst case a badge can sit on.
 */
const SURFACES = ["#ffffff", "#f8fafc", "#f1f5f9"];

function toLinearChannels(hex: string): number[] {
  const value = hex.replace("#", "");
  return [0, 2, 4].map((offset) => {
    const srgb = parseInt(value.slice(offset, offset + 2), 16) / 255;
    return srgb <= 0.04045 ? srgb / 12.92 : ((srgb + 0.055) / 1.055) ** 2.4;
  });
}

function relativeLuminance(hex: string): number {
  const [r, g, b] = toLinearChannels(hex);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG contrast ratio between two opaque colors. */
function contrastRatio(a: string, b: string): number {
  const [hi, lo] = [relativeLuminance(a), relativeLuminance(b)].sort(
    (x, y) => y - x,
  );
  return (hi + 0.05) / (lo + 0.05);
}

/** Composites `hex` at `alpha` over `backdrop` — i.e. Tailwind's `bg-x/10`. */
function tint(hex: string, alpha: number, backdrop: string): string {
  const fg = toLinearChannels(hex);
  const bg = toLinearChannels(backdrop);
  const encode = (linear: number) => {
    const srgb =
      linear <= 0.0031308
        ? 12.92 * linear
        : 1.055 * linear ** (1 / 2.4) - 0.055;
    return Math.round(Math.min(1, Math.max(0, srgb)) * 255)
      .toString(16)
      .padStart(2, "0");
  };
  return `#${fg.map((c, i) => encode(c * alpha + bg[i] * (1 - alpha))).join("")}`;
}

/** Reads a color custom property out of the `@theme` block of index.css. */
function themeToken(name: string): string {
  const match = new RegExp(`--color-${name}:\\s*(#[0-9a-f]{6})`, "i").exec(
    INDEX_CSS,
  );
  if (match === null) {
    throw new Error(`--color-${name} not found in index.css`);
  }
  return match[1].toLowerCase();
}

/** Every non-test component source, i.e. everywhere class names are written. */
function componentSources(): { path: string; text: string }[] {
  return readdirSync(SRC_DIR, { recursive: true, encoding: "utf8" })
    .filter((entry) => entry.endsWith(".tsx") && !entry.includes(".test."))
    .map((entry) => ({
      path: entry,
      text: readFileSync(join(SRC_DIR, entry), "utf8"),
    }));
}

describe("palette contrast", () => {
  /**
   * The four status tokens are the "on" color of their own soft tint
   * (`bg-status-warn/10 text-status-warn`), so both the flat surface and the
   * tinted one have to clear AA. The pinned hexes are the values those ratios
   * were derived from: changing one without re-deriving is the regression this
   * guards.
   */
  it("test_status_tokens_meet_aa", () => {
    const expected = {
      "status-good": "#047857",
      "status-warn": "#92400e",
      "status-bad": "#b91c1c",
      "status-info": "#0369a1",
    };

    for (const [token, hex] of Object.entries(expected)) {
      expect(themeToken(token), token).toBe(hex);

      for (const surface of SURFACES) {
        expect(
          contrastRatio(hex, surface),
          `${token} on ${surface}`,
        ).toBeGreaterThanOrEqual(AA_TEXT);
        expect(
          contrastRatio(hex, tint(hex, 0.1, surface)),
          `${token} on its own /10 tint over ${surface}`,
        ).toBeGreaterThanOrEqual(AA_TEXT);
      }
    }
  });

  /**
   * The brand orange stays a fill / large-text color; `signal-ink` is what
   * small text uses, including over a signal tint (the "今日" pill, the
   * A-race tag, the ActionCallout heading).
   */
  it("test_signal_ink_meets_aa_on_signal_tints", () => {
    const signalInk = themeToken("signal-ink");
    const signal = themeToken("signal");
    expect(signalInk).toBe("#bf360c");

    for (const surface of SURFACES) {
      expect(
        contrastRatio(signalInk, surface),
        `signal-ink on ${surface}`,
      ).toBeGreaterThanOrEqual(AA_TEXT);
      for (const alpha of [0.05, 0.15]) {
        expect(
          contrastRatio(signalInk, tint(signal, alpha, surface)),
          `signal-ink on bg-signal/${alpha * 100} over ${surface}`,
        ).toBeGreaterThanOrEqual(AA_TEXT);
      }
    }
  });

  /**
   * slate-400 is 2.63:1 on white — under AA at every text size, and under the
   * 3:1 non-text floor too, so it is not a legitimate color for muted labels,
   * chevrons or oversized decorative numerals anywhere in the app. slate-500
   * (4.77:1 on white, 4.55:1 on slate-50) is the muted replacement; copy that
   * sits on slate-100, or on the dark end of a hero gradient, takes slate-600.
   */
  it("test_no_slate400_text_remains", () => {
    const sources = componentSources();
    // A scan that silently walks nothing would "pass" forever.
    expect(sources.some(({ path }) => path.endsWith("SectionHeading.tsx"))).toBe(
      true,
    );

    const offenders = sources
      .filter(({ text }) => text.includes(BANNED_MUTED_GRAY))
      .map(({ path }) => path);

    expect(offenders).toEqual([]);
  });
});
