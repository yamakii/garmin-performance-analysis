/**
 * @vitest-environment node
 */
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { PAPER_COLOR } from "./components/chartTheme";

/**
 * Contrast regression guard for the Morning Brief palette (#911 → #1116).
 *
 * Every text token is measured against the surfaces it actually sits on —
 * the paper ground, the well (bar tracks, skeletons) and its own tint for the
 * status colors. Neither `tsc` nor eslint can see a contrast ratio, so the
 * ratios are recomputed here from the checked-in CSS rather than trusted to a
 * comment.
 */

const SRC_DIR = fileURLToPath(new URL(".", import.meta.url));
const INDEX_CSS = readFileSync(join(SRC_DIR, "index.css"), "utf8");

/** WCAG 2.1 SC 1.4.3 floor for body-sized text. */
const AA_TEXT = 4.5;

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

describe("chart-side token copies", () => {
  it("test_paper_color_matches_css_token", () => {
    // ECharts cannot read CSS variables, so chartTheme keeps a copy (#1443).
    expect(PAPER_COLOR.toLowerCase()).toBe(themeToken("paper"));
  });
});

describe("palette contrast", () => {
  /**
   * The pinned hexes are the values the ratios below were derived from:
   * changing one without re-deriving is the regression this guards.
   */
  it("test_status_tokens_meet_aa", () => {
    const paper = themeToken("paper");
    const pinned: Record<string, string> = {
      paper: "#f4f1ea",
      ink: "#1c1b18",
      "ink-soft": "#3d3a34",
      "ink-muted": "#6b675e",
      accent: "#1f6f6b",
      "accent-tint": "#e6f0ef",
      "status-good": "#2f7a45",
      "status-warn": "#9a5b12",
      "warn-tint": "#fdf1e4",
      "status-bad": "#a83a2e",
      "bad-tint": "#fbe7e3",
      well: "#ebe7de",
    };
    for (const [token, hex] of Object.entries(pinned)) {
      expect(themeToken(token), token).toBe(hex);
    }

    // [text token, surface token] pairs that carry body-sized text.
    const pairs: [string, string][] = [
      ["ink", "paper"],
      ["ink-soft", "paper"],
      ["ink-muted", "paper"],
      ["ink-muted", "well"],
      ["ink-muted", "warn-tint"],
      ["accent", "paper"],
      ["accent", "accent-tint"],
      ["status-good", "paper"],
      ["status-warn", "paper"],
      ["status-warn", "warn-tint"],
      ["status-bad", "paper"],
      ["status-bad", "bad-tint"],
      ["paper", "ink"],
      ["paper", "accent"],
    ];
    for (const [fg, bg] of pairs) {
      expect(
        contrastRatio(themeToken(fg), themeToken(bg)),
        `${fg} on ${bg}`,
      ).toBeGreaterThanOrEqual(AA_TEXT);
    }
    // Sanity: the paper token really is the body ground the pairs assume.
    expect(paper).toBe("#f4f1ea");
  });

  /**
   * `ink-faint` is 2.67:1 on paper — under AA at every size — so it is only
   * legitimate for disabled cells (days outside the month on the plan grid),
   * never for labels or captions.
   */
  it("test_ink_faint_only_on_disabled_cells", () => {
    const sources = componentSources();
    expect(sources.some(({ path }) => path.endsWith("Layout.tsx"))).toBe(true);

    const offenders = sources
      .filter(({ text }) => text.includes("text-ink-faint"))
      .map(({ path }) => path.split("\\").join("/"))
      .filter((path) => path !== "components/plan/DayCell.tsx");

    expect(offenders).toEqual([]);
  });
});

describe("link underlines", () => {
  /**
   * Hover underline belongs to links inside running text, where it separates
   * the link from the prose. A global `a:hover` made every navigational
   * anchor — nav tabs, a vitals cell, a progress row, a button-shaped link —
   * wrong by default and forced a `hover:no-underline` on each (#1195).
   */
  it("test_hover_underline_scoped_to_body_links", () => {
    expect(INDEX_CSS).toMatch(
      /main p a:hover,\s*main li a:hover,\s*main dd a:hover\s*\{[^}]*@apply underline;/,
    );
    // The unscoped rule is gone: no selector line is a bare `a:hover`
    // (the scoped ones all begin with `main`).
    expect(INDEX_CSS).not.toMatch(/^\s*a:hover\s*[,{]/m);
  });

  /**
   * The cancels that survive are the two anchors the scoped rule still
   * reaches — both are `<a>` inside `<li>` inside `<main>`. Everything else
   * was removed with the global rule, and a new one would be a smell.
   */
  it("test_only_list_anchors_still_cancel_the_underline", () => {
    const offenders = componentSources()
      .filter(({ text }) => text.includes("hover:no-underline"))
      .map(({ path }) => path.split("\\").join("/"))
      .sort();

    expect(offenders).toEqual([
      "components/SectionNav.tsx",
      "pages/ActivityList.tsx",
    ]);
  });
});

describe("markdown prose wrapping", () => {
  /**
   * Analysis prose carries runs like `GCT★4.0/VO★5.0/VR★5.0` that have no
   * break opportunity. In a narrow column they widened the whole page to
   * 457px at a 390px viewport (#1145).
   */
  it("test_markdown_body_overflow_wrap", () => {
    const block = /\.markdown-body\s*\{([^}]*)\}/.exec(INDEX_CSS);
    expect(block, ".markdown-body rule not found in index.css").not.toBeNull();
    expect((block as RegExpExecArray)[1]).toMatch(
      /overflow-wrap:\s*anywhere;/,
    );
  });
});
