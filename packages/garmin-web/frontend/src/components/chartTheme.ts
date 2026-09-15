/**
 * Shared visual tokens for ECharts (Morning Brief, Epic #1115).
 * Visual styling only — chart data shaping stays in each component.
 *
 * Color values mirror the CSS custom properties in index.css @theme;
 * ECharts renders into canvas so it cannot read CSS variables directly.
 *
 * Chart rules (docs/design/morning-brief-handoff.md §Charts): the primary
 * series of a chart is ink, whatever it is compared against is the hairline
 * `COMPARE_COLOR`, personal baselines / optimal bands are a faint ink wash,
 * thresholds are dotted lines in the status hue, and axis text is the mono
 * face at 11px with horizontal grid lines only.
 */

/** Near-black ink: the primary series of every single-series chart. */
export const INK_COLOR = "#1c1b18";

/** Comparison series and reference lines: the hairline gray. */
export const COMPARE_COLOR = "#c9c3b6";

/** Personal-baseline / optimal band: a faint ink wash (`markArea`). */
export const BASELINE_BAND_COLOR = "rgba(28,27,24,0.06)";

/** Threshold lines (`markLine`, dotted): 注意 / 高リスク. */
export const THRESHOLD_LINE = { warn: "#9a5b12", bad: "#a83a2e" } as const;

/**
 * Semantic color per metric key. Used consistently by TimeSeriesChart, the
 * metric toggles and the trend blocks.
 *
 * Two groups live in one map so that no chart has to borrow a hue that already
 * means something else (Issue #913): a borrowed token implies a kinship the
 * data does not have. Every plotted metric therefore owns a token here.
 */
export const METRIC_COLORS: Record<string, string> = {
  // Activity time-series metrics. Power and the form metrics (GCT / VO / VR)
  // deliberately share the violet: the toggles read as one "form" group.
  heart_rate: "#b8433f",
  speed: "#1f6f6b",
  cadence: "#b07a1d",
  power: "#6a4fb3",
  elevation: "#6b675e",
  ground_contact_time: "#6a4fb3",
  vertical_oscillation: "#6a4fb3",
  vertical_ratio: "#6a4fb3",
  // Longitudinal trend metrics (condition / performance pages). The primary
  // series of each chart takes ink; whatever it is compared against gets a
  // hue of its own.
  vo2max: INK_COLOR,
  weight: INK_COLOR,
  objective_vdot: "#1f6f6b",
  hrv: INK_COLOR,
  ef: "#1f6f6b",
  acwr: "#3d3a34",
  heat_cost: "#9a5b12",
  fat_mass: "#b07a1d",
  lean_mass: "#1f6f6b",
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

/** Overall form score: ink, its panel being single-series. */
export const FORM_SCORE_COLOR = INK_COLOR;

/**
 * Distinct hues for the three form deltas (GCT / VO / VR). GCT keeps its
 * metric token so the delta panel and DurabilityBlock's GCT-fade line read as
 * the same metric (Issue #913); VO and VR take the pace and cadence hues.
 */
export const FORM_DELTA_COLORS = [
  METRIC_COLORS.ground_contact_time,
  "#1f6f6b",
  "#b07a1d",
] as const; // violet (GCT) / teal (VO) / amber (VR)

/**
 * Garmin HR zone colors z1-z5 as a single-hue sequential ramp (pale -> deep,
 * the heart-rate hue). Zone order *is* intensity order, so lightness encodes
 * it; five unrelated hues would read as five unordered categories (#913).
 */
export const ZONE_COLORS = [
  "#e8c9c7",
  "#d49c98",
  "#c2716c",
  "#b8433f",
  "#8a2e2a",
];

/** ink, pace teal, HR rose, cadence amber, power violet */
export const CHART_PALETTE = [
  INK_COLOR,
  METRIC_COLORS.speed,
  METRIC_COLORS.heart_rate,
  METRIC_COLORS.cadence,
  METRIC_COLORS.power,
];

/** hairline */
export const GRID_LINE_COLOR = "#dcd7cc";

/** ink-muted */
export const AXIS_LABEL_COLOR = "#6b675e";

export const CHART_FONT_SIZE = 11;

/** The mono face: axis labels, tooltips and mark labels are all numerals. */
export const CHART_FONT_FAMILY = "IBM Plex Mono";

/** Spread into every option: palette + unified typography. */
export const BASE_CHART_OPTION = {
  color: CHART_PALETTE,
  textStyle: {
    fontSize: CHART_FONT_SIZE,
    fontFamily: CHART_FONT_FAMILY,
    color: AXIS_LABEL_COLOR,
  },
} as const;

/**
 * Spread into value axes: mono labels, no axis line, horizontal grid only.
 * Category (x) axes take `X_AXIS_STYLE`, which also drops the vertical grid.
 */
export const AXIS_STYLE = {
  axisLabel: {
    color: AXIS_LABEL_COLOR,
    fontSize: CHART_FONT_SIZE,
    fontFamily: CHART_FONT_FAMILY,
  },
  axisLine: { show: false },
  axisTick: { show: false },
  splitLine: { lineStyle: { color: GRID_LINE_COLOR } },
} as const;

export const X_AXIS_STYLE = {
  ...AXIS_STYLE,
  splitLine: { show: false },
} as const;
