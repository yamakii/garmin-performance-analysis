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
 * Semantic color per metric key. Used consistently by TimeSeriesChart, the
 * metric toggles and the trend blocks.
 *
 * Two groups live in one map so that no chart has to borrow a hue that already
 * means something else (Issue #913): a borrowed token implies a kinship the
 * data does not have — HRV drawn in the power violet reads as "power". Every
 * plotted metric therefore owns a token here.
 */
export const METRIC_COLORS: Record<string, string> = {
  // Activity time-series metrics. Form metrics (GCT / VO / VR) deliberately
  // share the violet family: the toggles read as one "form" group.
  heart_rate: "#e11d48",
  speed: "#0d9488",
  cadence: "#d97706",
  power: "#7c3aed",
  elevation: "#78716c",
  ground_contact_time: "#8b5cf6",
  vertical_oscillation: "#8b5cf6",
  vertical_ratio: "#8b5cf6",
  // Longitudinal trend metrics (condition / performance pages). VO2max and
  // weight take the editorial ink because each is the primary series of its
  // chart; whatever they are compared against gets a hue of its own.
  vo2max: INK_COLOR,
  weight: INK_COLOR,
  objective_vdot: "#c2410c",
  hrv: "#0284c7",
  ef: "#047857",
  acwr: "#9333ea",
  heat_cost: "#ea580c",
  fat_mass: "#f59e0b",
  lean_mass: "#0f766e",
};

/**
 * On-light text variant of each metric color (Issue #911).
 *
 * `METRIC_COLORS` is tuned for canvas strokes on white, where the 3:1 non-text
 * threshold applies; as *text* those hues run 2.93-4.41:1 and miss AA. Wherever
 * a metric color has to letter something on a light surface — the time-series
 * toggles paint their label over an 8% tint of the metric — use this map. Each
 * entry keeps its metric's hue so the toggle still reads as the chart line it
 * controls, and clears 4.5:1 on that tint (4.75:1 worst case, cadence).
 */
export const METRIC_TEXT_COLORS: Record<string, string> = {
  // Time-series metrics only: the trend tokens never letter on a tint.
  heart_rate: "#be123c",
  speed: "#0f766e",
  cadence: "#b45309",
  power: "#6d28d9",
  elevation: "#57534e",
  ground_contact_time: "#6d28d9",
  vertical_oscillation: "#6d28d9",
  vertical_ratio: "#6d28d9",
};

/** Decimal places per time-series metric. speed (pace) is excluded
 *  because it uses a dedicated mm:ss formatter. */
export const METRIC_DECIMALS: Record<string, number> = {
  heart_rate: 0,
  cadence: 0,
  power: 0,
  elevation: 0,
  ground_contact_time: 1,
  vertical_oscillation: 1,
  vertical_ratio: 1,
};

/** Overall form score: the editorial ink, its panel being single-series. */
export const FORM_SCORE_COLOR = INK_COLOR;

/**
 * Distinct hues for the three form deltas (GCT / VO / VR), chosen for
 * legibility over the shared-violet theme. GCT keeps its metric token so the
 * delta panel and DurabilityBlock's GCT-fade line read as the same metric
 * (Issue #913).
 */
export const FORM_DELTA_COLORS = [
  METRIC_COLORS.ground_contact_time,
  "#0d9488",
  "#d97706",
] as const; // violet (GCT) / teal (VO) / amber (VR)

/**
 * Garmin HR zone colors z1-z5 as a single-hue sequential ramp (pale -> deep
 * rose). Zone order *is* intensity order, so lightness encodes it; five
 * unrelated hues (the old slate/sky/emerald/amber/red set) read as five
 * unordered categories instead (Issue #913). The rose family is the
 * heart-rate hue, which is what zones measure.
 */
export const ZONE_COLORS = [
  "#fecdd3",
  "#fda4af",
  "#fb7185",
  "#f43f5e",
  "#be123c",
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
