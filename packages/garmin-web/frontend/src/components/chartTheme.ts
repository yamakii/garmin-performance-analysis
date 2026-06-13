/**
 * Shared visual tokens for ECharts (Issue #214 "Editorial Sport" theme).
 * Visual styling only — chart data shaping stays in each component.
 *
 * Color values mirror the CSS custom properties in index.css @theme;
 * ECharts renders into canvas so it cannot read CSS variables directly.
 */

/** Ink navy: editorial axis color, first in the default palette. */
export const INK_COLOR = "#16213a";

/**
 * Semantic color per time-series metric key. Used consistently by
 * TimeSeriesChart, the metric toggles and the trend blocks.
 * Form metrics (GCT / VO / VR) share the violet family.
 */
export const METRIC_COLORS: Record<string, string> = {
  heart_rate: "#e11d48",
  speed: "#0d9488",
  cadence: "#d97706",
  power: "#7c3aed",
  elevation: "#78716c",
  ground_contact_time: "#8b5cf6",
  vertical_oscillation: "#8b5cf6",
  vertical_ratio: "#8b5cf6",
};

/** Violet shades for overlaid form lines (overall / GCT / VO / VR). */
export const FORM_LINE_COLORS = ["#16213a", "#8b5cf6", "#a78bfa", "#c4b5fd"];

/** Garmin HR zone colors z1-z5 (calm -> hot). */
export const ZONE_COLORS = [
  "#94a3b8",
  "#38bdf8",
  "#34d399",
  "#fbbf24",
  "#f87171",
];

/** ink, pace teal, HR rose, cadence amber, power violet */
export const CHART_PALETTE = [
  INK_COLOR,
  METRIC_COLORS.speed,
  METRIC_COLORS.heart_rate,
  METRIC_COLORS.cadence,
  METRIC_COLORS.power,
];

/** slate-200 */
export const GRID_LINE_COLOR = "#e2e8f0";

/** slate-500 */
export const AXIS_LABEL_COLOR = "#64748b";

export const CHART_FONT_SIZE = 12;

/** Spread into every option: palette + unified typography. */
export const BASE_CHART_OPTION = {
  color: CHART_PALETTE,
  textStyle: { fontSize: CHART_FONT_SIZE, color: AXIS_LABEL_COLOR },
} as const;

/** Spread into category/value axes for unified line + label styling. */
export const AXIS_STYLE = {
  axisLabel: { color: AXIS_LABEL_COLOR, fontSize: CHART_FONT_SIZE },
  axisLine: { lineStyle: { color: GRID_LINE_COLOR } },
  splitLine: { lineStyle: { color: GRID_LINE_COLOR } },
} as const;
