import { describe, expect, it } from "vitest";
import { METRIC_COLORS, METRIC_TEXT_COLORS, ZONE_COLORS } from "./chartTheme";

/** #rrggbb -> HSL, hue in degrees and lightness in 0-1. */
function hexToHsl(hex: string): { hue: number; lightness: number } {
  const [r, g, b] = [1, 3, 5].map(
    (offset) => parseInt(hex.slice(offset, offset + 2), 16) / 255,
  );
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const delta = max - min;
  let hue = 0;
  if (delta !== 0) {
    if (max === r) hue = ((g - b) / delta) % 6;
    else if (max === g) hue = (b - r) / delta + 2;
    else hue = (r - g) / delta + 4;
  }
  return { hue: ((hue * 60) % 360 + 360) % 360, lightness: (max + min) / 2 };
}

/** Shortest distance between two hues on the 360-degree wheel. */
function hueDistance(a: number, b: number): number {
  const raw = Math.abs(a - b) % 360;
  return raw > 180 ? 360 - raw : raw;
}

describe("ZONE_COLORS", () => {
  it("test_zone_colors_sequential", () => {
    const ramp = ZONE_COLORS.map(hexToHsl);
    expect(ramp).toHaveLength(5);

    for (let i = 1; i < ramp.length; i += 1) {
      // Single hue family: zone order is encoded by lightness, not by five
      // unrelated hues (which would read as unordered categories).
      expect(hueDistance(ramp[i].hue, ramp[i - 1].hue)).toBeLessThan(15);
      // Pale -> deep, monotonically, so "further right" reads as "harder".
      expect(ramp[i].lightness).toBeLessThan(ramp[i - 1].lightness);
    }
  });
});

describe("METRIC_TEXT_COLORS", () => {
  it("test_metric_text_colors_track_metric_colors", () => {
    // The on-light text variants exist only for metrics that have a chart
    // color; a stray key would mean a toggle painting a metric that no line
    // uses.
    for (const key of Object.keys(METRIC_TEXT_COLORS)) {
      expect(METRIC_COLORS).toHaveProperty(key);
    }
  });
});
