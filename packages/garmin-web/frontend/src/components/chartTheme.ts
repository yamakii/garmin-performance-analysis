/**
 * Shared visual tokens for ECharts (Issue #210 light-clean theme).
 * Visual styling only — chart data shaping stays in each component.
 */

/** indigo-600, sky-500, emerald-500, amber-500, violet-500 */
export const CHART_PALETTE = [
  "#4f46e5",
  "#0ea5e9",
  "#10b981",
  "#f59e0b",
  "#8b5cf6",
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
