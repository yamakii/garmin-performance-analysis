import type { JSX } from "react";
import EChart from "../EChart";
import SectionBlock from "../SectionBlock";
import type { EChartsOption } from "../../lib/echarts";
import {
  AXIS_LABEL_COLOR,
  CHART_FONT_FAMILY,
  CHART_FONT_SIZE,
  GRID_LINE_COLOR,
  METRIC_COLORS,
  THRESHOLD_LINE,
} from "../chartTheme";
import type {
  RunFlowData,
  RunFlowSegment,
  RunMoment,
  RunNoteTimelineItem,
} from "../../types";
import { formatPaceLabel } from "../TimeSeriesChart";

/** Scene numbers, matching the list under the chart. */
export const SCENE_MARKERS = ["①", "②", "③", "④", "⑤"];

/**
 * The two ink washes the scene bands alternate between.
 *
 * Adjacent scenes are the normal case (a climb straight into a fade), and one
 * tint for all of them fuses them into a single grey slab that says nothing
 * about where one ends and the next begins. Two washes plus the hairline at
 * each boundary keep them countable (#1252).
 */
export const SCENE_TINTS = ["rgba(28,27,24,0.04)", "rgba(28,27,24,0.09)"];

/** Japanese name per scene kind, for a scene the coach wrote nothing about. */
const KIND_LABELS: Record<string, string> = {
  start: "入り",
  fast_start: "速い入り",
  climb: "登り",
  fade: "ペース低下",
  surge: "ペースアップ",
  progression: "ビルドアップ",
  strong_finish: "終盤の粘り",
  walk_break: "歩き",
  ceiling_touch: "上限到達",
  self_correction: "立て直し",
  steady: "一定ペース",
  warmup: "ウォームアップ",
  rep: "レップ",
  rest: "レスト",
  work_set: "本編",
  main: "本編",
  cooldown: "クールダウン",
};

const GRID_SIDES = { left: 56, right: 16 } as const;
/** A row above the plot area: scene captions cannot collide with y labels. */
const CAPTION_GRID = { ...GRID_SIDES, top: 4, height: 16 } as const;
const PACE_GRID = { ...GRID_SIDES, top: 32, height: 88 } as const;
const HR_GRID = { ...GRID_SIDES, top: 158, height: 88 } as const;

/** ECharts' default distance between an axis and its tick labels. */
const AXIS_LABEL_MARGIN = 8;
/** Bottom of the tick-label row, in chart pixels. */
const TICK_ROW_BOTTOM =
  HR_GRID.top + HR_GRID.height + AXIS_LABEL_MARGIN + CHART_FONT_SIZE;
/**
 * Top of the axis-unit line, a row of its own *below* the tick labels.
 *
 * ECharts' `nameLocation: "end"` puts the unit at the end of the tick row,
 * where it reads as part of the last tick: "25" + "km" was read as "2km" on
 * the shipped page, and at 400 px "35" and "分" overlapped outright (#1269).
 */
export const AXIS_UNIT_TOP = TICK_ROW_BOTTOM + 4;
const CHART_HEIGHT = AXIS_UNIT_TOP + CHART_FONT_SIZE + 2;

/**
 * Chart width the caption widths are judged against.
 *
 * A band's width in pixels depends on the container, which the option builder
 * cannot measure. The reference is the page's content column on a laptop; a
 * band that carries its step's name here still carries it at 400 px, only
 * tighter — and a band too narrow for a name at this width would be unreadable
 * at any width.
 */
export const REFERENCE_CHART_WIDTH_PX = 720;
/** A band narrower than this shows its scene number alone. */
export const CAPTION_MIN_PX = 64;

/** Above this distance an integer tick per kilometre crowds the axis. */
const DENSE_AXIS_MAX_KM = 12;
/** Ticks every 5 minutes on a time axis, every 5 km on a long distance one. */
const COARSE_AXIS_INTERVAL = 5;

function round3(value: number): number {
  return Math.round(value * 1000) / 1000;
}

/** The axis a run is drawn on: its unit, its extent and its tick spacing. */
export function flowAxis(flow: RunFlowData): {
  unit: string;
  max: number;
  interval: number;
} {
  if (flow.axis === "time") {
    return {
      unit: "分",
      max: round3(flow.total_s / 60),
      interval: COARSE_AXIS_INTERVAL,
    };
  }
  return {
    unit: "km",
    max: round3(flow.total_km),
    interval: flow.total_km <= DENSE_AXIS_MAX_KM ? 1 : COARSE_AXIS_INTERVAL,
  };
}

/** Where one drawn segment starts and ends, in the axis' own unit. */
function segmentSpan(
  flow: RunFlowData,
  segment: RunFlowSegment,
): [number, number] {
  return flow.axis === "time"
    ? [round3(segment.start_s / 60), round3(segment.end_s / 60)]
    : [round3(segment.start_km), round3(segment.end_km)];
}

/**
 * The invisible series that answers the tooltip (#1285).
 *
 * A step is drawn as two points, and ECharts' axis tooltip reports the nearest
 * *point*: both ends of a boundary (pace twice), only the closest series per
 * axis (the ring beat the average line, so 心拍 vanished), one header per axis
 * at the snapped value ("1.00" and "1.50"). It cannot describe step-shaped
 * data, so the drawn series opt out and this one stands in for the segment.
 */
export const CARRIER_SERIES_NAME = "区間";

/** How far inside its segment a carrier point sits, as a share of the axis. */
const CARRIER_INSET_SHARE = 1 / 2000;

/**
 * Two points per segment, just inside each end. For a pointer anywhere in a
 * segment the nearest of these is in the same segment — its own edge point is
 * `d − ε` away and the neighbour's `d + ε` — whatever the widths. A midpoint
 * would hand the last 400 m of a kilometre to the 0.18 km rest beside it.
 */
function carrierPoints(flow: RunFlowData, axisMax: number): [number, number][] {
  const inset = axisMax * CARRIER_INSET_SHARE;
  return flow.segments.flatMap((segment): [number, number][] => {
    const [from, to] = segmentSpan(flow, segment);
    const reach = Math.min(inset, (to - from) / 4);
    return [
      [from + reach, 0],
      [to - reach, 0],
    ];
  });
}

/** The segment drawn at `x`; a boundary belongs to the one that starts there. */
export function segmentAt(flow: RunFlowData, x: number): RunFlowSegment | null {
  if (!Number.isFinite(x)) {
    return null;
  }
  let found: RunFlowSegment | null = null;
  for (const segment of flow.segments) {
    const [from, to] = segmentSpan(flow, segment);
    if (x >= from && x <= to) {
      found = segment;
    }
  }
  return found;
}

function clock(seconds: number): string {
  const whole = Math.round(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

/** "1.0–2.0 km" on a distance axis, "10:00–13:00" on a time axis. */
function segmentSpanLabel(flow: RunFlowData, segment: RunFlowSegment): string {
  if (flow.axis === "time") {
    return `${clock(segment.start_s)}–${clock(segment.end_s)}`;
  }
  const digits = segment.end_km - segment.start_km < 0.1 ? 2 : 1;
  return `${segment.start_km.toFixed(digits)}–${segment.end_km.toFixed(digits)} km`;
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/**
 * What hovering a segment says: where it was, then one row per series.
 *
 * The step's name leads when the run has steps to tell apart — on a threshold
 * session "1本目" is how the athlete thinks of it, the clock span is where to
 * find it on the axis.
 */
export function segmentTooltipHtml(
  flow: RunFlowData,
  segment: RunFlowSegment,
): string {
  const step =
    flow.steps.length > 1
      ? flow.steps.find((candidate) => candidate.id === segment.step_id)
      : undefined;
  const span = segmentSpanLabel(flow, segment);
  const header = step ? `${escapeHtml(step.label_ja)} · ${span}` : span;

  const line = `display:inline-block;width:12px;height:2px;margin-right:6px;vertical-align:middle;`;
  const ring = `display:inline-block;width:6px;height:6px;margin:0 9px 0 3px;vertical-align:middle;box-sizing:border-box;border:1px solid ${METRIC_COLORS.heart_rate};border-radius:50%;`;
  const rows: [string, string, string][] = [
    [
      `${line}background:${METRIC_COLORS.speed};`,
      "ペース",
      segment.pace_s_per_km != null
        ? `${formatPaceLabel(segment.pace_s_per_km)}/km`
        : "-",
    ],
    [
      `${line}background:${METRIC_COLORS.heart_rate};`,
      "平均心拍",
      segment.avg_hr != null ? `${Math.round(segment.avg_hr)} bpm` : "-",
    ],
    [
      ring,
      "最大心拍",
      segment.max_hr != null ? `${Math.round(segment.max_hr)} bpm` : "-",
    ],
  ];
  const body = rows
    .map(
      ([marker, name, value]) =>
        `<div style="display:flex;justify-content:space-between;gap:16px;">` +
        `<span><span style="${marker}"></span>${name}</span>` +
        `<span style="font-variant-numeric:tabular-nums;">${value}</span></div>`,
    )
    .join("");
  return (
    `<div style="font-family:${CHART_FONT_FAMILY};font-size:${CHART_FONT_SIZE}px;line-height:1.6;">` +
    `<div style="margin-bottom:2px;">${header}</div>${body}</div>`
  );
}

/** The lap numbers a scene happened on, or null when it is a stretch. */
export function momentLaps(moment: RunMoment): number[] | null {
  const laps = moment.facts.split_list;
  if (!Array.isArray(laps) || laps.length === 0) {
    return null;
  }
  const numbers = laps.filter(
    (lap): lap is number => typeof lap === "number" && Number.isFinite(lap),
  );
  return numbers.length > 0 ? numbers : null;
}

/** The span the laps `from..to` cover, or null when none of them is drawn. */
function lapsSpan(
  flow: RunFlowData,
  from: number,
  to: number,
): [number, number] | null {
  const spans = flow.segments
    .filter(
      (segment) => segment.split_to >= from && segment.split_from <= to,
    )
    .map((segment) => segmentSpan(flow, segment));
  if (spans.length === 0) {
    return null;
  }
  return [spans[0][0], spans[spans.length - 1][1]];
}

/** One drawn band: where it sits on the axis and what is written above it. */
export interface SceneBand {
  /** Index of the scene in `moments` — its number and its tint. */
  index: number;
  from: number;
  to: number;
  caption: string;
}

/**
 * The step name a scene may be captioned with, or null for a number alone.
 *
 * A scene that *is* a step is named after it (アップ / 1本目 / R / ダウン). So
 * is a kilometre-unit scene that happens to cover a whole step of a structured
 * run: on the tempo session the widest band read "②" while its neighbours read
 * "① アップ" and "③ ダウン", which made the main set look like the nameless
 * one (#1269).
 */
function stepName(flow: RunFlowData, moment: RunMoment): string | null {
  if (moment.unit === "step") {
    const step = flow.steps.find((entry) => entry.id === moment.step_id);
    return step?.short_ja ?? (moment.label_ja || null);
  }
  if (flow.steps.length > 1) {
    const step = flow.steps.find(
      (entry) =>
        entry.split_from === moment.split_from &&
        entry.split_to === moment.split_to,
    );
    if (step != null) {
      return step.short_ja;
    }
  }
  return null;
}

/**
 * The bands the chart tints, one entry per drawn area.
 *
 * Every scene gets a band, a one-split scene included — a scene drawn as a
 * zero-width line is invisible. A walk break gets one band per walk lap
 * instead of a single slab from the first stop to the last: the 9/13 run
 * walked at km 14, 20 and 22, and one band over km 13-22 both overstated the
 * break and swallowed the scene that happened at km 17 (#1269).
 */
export function sceneBands(
  flow: RunFlowData,
  moments: RunMoment[],
): SceneBand[] {
  const axis = flowAxis(flow);
  const plotWidth =
    REFERENCE_CHART_WIDTH_PX - GRID_SIDES.left - GRID_SIDES.right;

  return moments.flatMap((moment, index) => {
    const name = stepName(flow, moment);
    const marker = SCENE_MARKERS[index] ?? String(index + 1);
    const laps = momentLaps(moment);
    const spans: [number, number][] =
      laps != null
        ? laps
            .map((lap) => lapsSpan(flow, lap, lap))
            .filter((span): span is [number, number] => span != null)
        : [momentSpan(flow, moment)];

    return spans
      .filter(([from, to]) => to > from)
      .map(([from, to]) => {
        const widthPx =
          axis.max > 0 ? ((to - from) / axis.max) * plotWidth : 0;
        const wide = name != null && widthPx >= CAPTION_MIN_PX;
        return {
          index,
          from,
          to,
          caption: wide ? `${marker} ${name}` : marker,
        };
      });
  });
}

/** Where a scene sits on the axis, falling back to the laps behind it. */
function momentSpan(flow: RunFlowData, moment: RunMoment): [number, number] {
  const span: [number, number] =
    flow.axis === "time"
      ? [round3(moment.t_from_s / 60), round3(moment.t_to_s / 60)]
      : [round3(moment.km_from), round3(moment.km_to)];
  if (span[1] > span[0]) {
    return span;
  }
  return lapsSpan(flow, moment.split_from, moment.split_to) ?? span;
}

/**
 * The chart the run's shape is read off: pace above, heart rate below.
 *
 * The two are stacked on a shared axis rather than overlaid on dual axes: a
 * pace line and an HR line share no unit and no scale, so a crossing of the
 * two means nothing and the reader spends their attention deciding which axis
 * each line belongs to. Stacked, each panel is read on its own and the
 * position they share does the comparing.
 *
 * That shared axis is a *real quantity* — kilometres run, or minutes elapsed —
 * never a category axis of split numbers. On the shipped page a 5 km run with
 * two lap presses drew an axis running to 7, leaving the right third empty,
 * and a 0.6 km manual lap was as wide as a kilometre (#1269). Each segment is
 * therefore drawn as a step over the span it actually covered, and the report
 * decides which segments exist, so pace, average HR and max HR always describe
 * the same splits.
 */
export function runFlowOption(
  flow: RunFlowData,
  moments: RunMoment[],
  hrCeiling: number | null,
): EChartsOption {
  const axis = flowAxis(flow);
  const paceData: [number, number | null][] = [];
  const hrData: [number, number | null][] = [];
  const maxHrData: [number, number | null][] = [];
  for (const segment of flow.segments) {
    const [from, to] = segmentSpan(flow, segment);
    paceData.push([from, segment.pace_s_per_km], [to, segment.pace_s_per_km]);
    hrData.push([from, segment.avg_hr], [to, segment.avg_hr]);
    maxHrData.push([round3((from + to) / 2), segment.max_hr]);
  }

  const bands = sceneBands(flow, moments);
  // The wash only: the number lives in the caption row above the plot, where
  // it cannot land on a y-axis label or on the ceiling's own label.
  const markArea = {
    silent: true,
    data: bands.map((band) => [
      {
        xAxis: band.from,
        itemStyle: { color: SCENE_TINTS[band.index % SCENE_TINTS.length] },
      },
      { xAxis: band.to },
    ]),
  };

  // A hairline where each band starts: without it two adjacent washes read as
  // one band with a slight gradient.
  const boundaries = bands.map((band) => ({
    xAxis: band.from,
    lineStyle: { color: GRID_LINE_COLOR, type: "solid" as const, width: 1 },
    label: { show: false },
  }));

  const xAxis = [CAPTION_GRID, PACE_GRID, HR_GRID].map((_, index) => ({
    type: "value" as const,
    gridIndex: index,
    min: 0,
    max: axis.max,
    interval: axis.interval,
    axisLabel: {
      // Only the lower panel carries the tick row; the unit sits below it.
      show: index === 2,
      color: AXIS_LABEL_COLOR,
      fontSize: CHART_FONT_SIZE,
      fontFamily: CHART_FONT_FAMILY,
      margin: AXIS_LABEL_MARGIN,
      hideOverlap: true,
      showMaxLabel: false,
    },
    axisLine: { show: false },
    axisTick: { show: false },
    splitLine: { show: false },
  }));

  return {
    animation: false,
    textStyle: {
      fontSize: CHART_FONT_SIZE,
      fontFamily: CHART_FONT_FAMILY,
      color: AXIS_LABEL_COLOR,
    },
    axisPointer: { link: [{ xAxisIndex: "all" }] },
    // Built per segment, from the carrier series alone (#1285).
    tooltip: {
      trigger: "axis",
      formatter: (params: unknown) => {
        const first = (Array.isArray(params) ? params[0] : params) as
          | { axisValue?: unknown; value?: unknown }
          | undefined;
        const raw =
          first?.axisValue ??
          (Array.isArray(first?.value) ? first.value[0] : undefined);
        const segment = segmentAt(flow, Number(raw));
        return segment ? segmentTooltipHtml(flow, segment) : "";
      },
    },
    grid: [CAPTION_GRID, PACE_GRID, HR_GRID],
    xAxis,
    yAxis: [
      // The caption row: no scale of its own, it only holds the band labels.
      {
        type: "value" as const,
        gridIndex: 0,
        min: 0,
        max: 1,
        show: false,
      },
      {
        type: "value" as const,
        gridIndex: 1,
        // No axis title: the legend under the chart already names both series,
        // and a title has nowhere to sit that is not someone else's row. As
        // the y axis' `name` it landed in the caption row, where "ペース" met
        // the first band's caption whenever a scene started at the axis —
        // "ペース①" over "アップ" on the shipped page (#1277).
        // Faster at the top: the run reads as it felt.
        inverse: true,
        scale: true,
        axisLabel: {
          color: AXIS_LABEL_COLOR,
          fontSize: CHART_FONT_SIZE,
          fontFamily: CHART_FONT_FAMILY,
          hideOverlap: true,
          formatter: (value: number) => formatPaceLabel(value),
        },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: GRID_LINE_COLOR } },
      },
      {
        type: "value" as const,
        gridIndex: 2,
        // No axis title here either, for the same reason (#1277).
        scale: true,
        axisLabel: {
          color: AXIS_LABEL_COLOR,
          fontSize: CHART_FONT_SIZE,
          fontFamily: CHART_FONT_FAMILY,
          hideOverlap: true,
        },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: GRID_LINE_COLOR } },
      },
    ],
    // The unit on a line of its own under the tick labels, at the right end
    // where the axis finishes — never appended to the last tick (#1269).
    graphic: [
      {
        type: "text" as const,
        right: GRID_SIDES.right,
        top: AXIS_UNIT_TOP,
        silent: true,
        style: {
          text: axis.unit,
          fill: AXIS_LABEL_COLOR,
          fontSize: CHART_FONT_SIZE,
          fontFamily: CHART_FONT_FAMILY,
          align: "right" as const,
        },
      },
    ],
    series: [
      {
        name: "場面",
        type: "line" as const,
        xAxisIndex: 0,
        yAxisIndex: 0,
        // One invisible point: a series with no data draws no mark area.
        data: [[0, 0]],
        symbol: "none" as const,
        lineStyle: { opacity: 0 },
        silent: true,
        tooltip: { show: false },
        markArea: {
          silent: true,
          data: bands.map((band) => [
            {
              xAxis: band.from,
              itemStyle: { color: "transparent" },
              label: {
                show: true,
                position: "inside" as const,
                formatter: band.caption,
                color: AXIS_LABEL_COLOR,
                fontSize: CHART_FONT_SIZE,
                fontFamily: CHART_FONT_FAMILY,
              },
            },
            { xAxis: band.to },
          ]),
        },
      },
      {
        // Draws nothing: it only gives the tooltip one point to find, inside
        // the segment under the pointer. It lives on the caption axis so the
        // pointer line in the two panels follows the mouse instead of
        // snapping to a segment's edge.
        name: CARRIER_SERIES_NAME,
        type: "line" as const,
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: carrierPoints(flow, axis.max),
        symbol: "none" as const,
        lineStyle: { opacity: 0 },
        silent: true,
      },
      {
        name: "ペース",
        type: "line" as const,
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: paceData,
        itemStyle: { color: METRIC_COLORS.speed },
        lineStyle: { color: METRIC_COLORS.speed },
        showSymbol: false,
        connectNulls: false,
        markArea,
        markLine: { silent: true, symbol: "none" as const, data: boundaries },
        tooltip: { show: false },
      },
      {
        name: "心拍",
        type: "line" as const,
        xAxisIndex: 2,
        yAxisIndex: 2,
        data: hrData,
        itemStyle: { color: METRIC_COLORS.heart_rate },
        lineStyle: { color: METRIC_COLORS.heart_rate },
        showSymbol: false,
        connectNulls: false,
        tooltip: { show: false },
        markArea,
        markLine: {
          silent: true,
          symbol: "none" as const,
          data: [
            ...boundaries,
            // The prescribed cap, dotted in the 注意 hue: a stretch spent above
            // it is then visible in the shape of the line, not only in prose.
            // The line carries no label. Every place on the canvas was
            // someone else's: at the start it met the y axis' top tick —
            // "上限 150" beside "150" (#1277) — outside the end it landed on
            // the last scene's number (#1269), and inside the end it sat under
            // the max-HR rings of a long run that finished at its ceiling
            // (#1285). Where the data goes is not ours to choose, so the
            // legend under the chart names the line instead.
            ...(hrCeiling != null
              ? [
                  {
                    yAxis: hrCeiling,
                    lineStyle: {
                      type: "dotted" as const,
                      color: THRESHOLD_LINE.warn,
                    },
                    label: { show: false },
                  },
                ]
              : []),
          ],
        },
      },
      {
        // The peak of each segment as a hollow ring, drawn at its midpoint:
        // the average line says how hard the segment was, the ring says how
        // hard its hardest moment was, and a ring far above its line is what a
        // surge looks like.
        name: "最大心拍",
        type: "scatter" as const,
        xAxisIndex: 2,
        yAxisIndex: 2,
        data: maxHrData,
        tooltip: { show: false },
        symbolSize: 5,
        itemStyle: {
          color: "transparent",
          borderColor: METRIC_COLORS.heart_rate,
          borderWidth: 1,
        },
      },
    ],
  } as EChartsOption;
}

/**
 * Which line is which (#1281).
 *
 * The y-axis titles were removed because they collided with the band captions
 * (#1277), so this row is the only place that names the series. It is DOM, not
 * canvas, so it stays readable at 400px, and its swatches read the same
 * constants the series do — the legend cannot drift from the chart. The
 * prescribed HR ceiling is named here too, for the same reason (#1285).
 */
export function SeriesLegend({
  hrCeiling,
}: {
  hrCeiling: number | null;
}): JSX.Element {
  const swatch = "mr-1.5 inline-block h-0.5 w-3.5 align-middle";
  return (
    <p className="mt-1 flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs text-ink-muted">
      <span>
        <span
          aria-hidden="true"
          data-series="pace"
          className={swatch}
          style={{ backgroundColor: METRIC_COLORS.speed }}
        />
        ペース /km（上が速い）
      </span>
      <span>
        <span
          aria-hidden="true"
          data-series="heart_rate"
          className={swatch}
          style={{ backgroundColor: METRIC_COLORS.heart_rate }}
        />
        平均心拍
      </span>
      <span>
        <span
          aria-hidden="true"
          data-series="max_heart_rate"
          className="mr-1.5 inline-block h-1.5 w-1.5 rounded-sm border align-middle"
          style={{ borderColor: METRIC_COLORS.heart_rate }}
        />
        最大心拍
      </span>
      {hrCeiling != null && (
        // The dotted line's name and value live here, not on the canvas,
        // where every position ended up on top of something (#1285).
        <span>
          <span
            aria-hidden="true"
            data-series="hr_ceiling"
            className="mr-1.5 inline-block h-0 w-3.5 border-t-2 border-dotted align-middle"
            style={{ borderColor: THRESHOLD_LINE.warn }}
          />
          上限 {Math.round(hrCeiling)}
        </span>
      )}
    </p>
  );
}

/** What the x axis is, and what the width of a step means. */
export function flowLegend(flow: RunFlowData): string {
  return flow.axis === "time"
    ? "横軸は経過時間（分） · 段の幅 = そのスプリット（区間）が覆った時間"
    : "横軸は実際の距離（km） · 段の幅 = そのスプリット（区間）が覆った距離";
}

/**
 * ランの流れ (#1252, #1269): the shape of the run, its scenes numbered on the
 * chart and told in one line each underneath.
 *
 * The scenes are deterministic (`report.moments`) and so is what the chart
 * draws (`report.flow`); the sentences are the coach's (`run_note.timeline`),
 * joined on the moment id. A scene the coach did not write about keeps its
 * band and its label, with nothing beside it — the run happened whether or not
 * there was anything to say about it.
 *
 * The component holds no rule about which splits are real: the report decided
 * that once, for every series and for the table below, so a fragment cannot be
 * dropped from the pace line while still moving the heart-rate line.
 */
export default function RunFlow({
  id,
  flow,
  moments,
  timeline,
  hrCeiling,
}: {
  id?: string;
  flow: RunFlowData | null;
  moments: RunMoment[];
  timeline: RunNoteTimelineItem[];
  hrCeiling: number | null;
}): JSX.Element | null {
  const drawable = flow != null && flow.segments.length > 0;
  if (!drawable && moments.length === 0) {
    return null;
  }
  const textOf = new Map(timeline.map((item) => [item.moment_id, item.text]));

  return (
    <SectionBlock id={id} title="ランの流れ">
      {drawable && flow != null && (
        <>
          <EChart
            option={runFlowOption(flow, moments, hrCeiling)}
            ariaLabel="ペースと心拍の推移"
            height={CHART_HEIGHT}
          />
          <SeriesLegend hrCeiling={hrCeiling} />
          <p className="mt-1 font-mono text-xs text-ink-muted">
            {flowLegend(flow)}
          </p>
        </>
      )}
      {moments.length > 0 && (
        <ol className="mt-4 flex flex-col gap-2">
          {moments.map((moment, index) => (
            <li
              key={moment.id}
              className="grid grid-cols-[1.5rem_minmax(0,1fr)] items-baseline gap-x-2 gap-y-1 md:grid-cols-[1.5rem_8rem_minmax(0,1fr)]"
            >
              <span aria-hidden="true" className="font-mono text-ink-muted">
                {SCENE_MARKERS[index] ?? index + 1}
              </span>
              {/* The label the report wrote: "3–5 km", "13・19・21 km 付近",
                  "本編 0.9–5.9 km", "1本目". The page does not re-derive it —
                  a lap number is not a kilometre (#1268). */}
              <span className="font-mono text-[13px] text-ink-muted md:whitespace-nowrap">
                {moment.label_ja || KIND_LABELS[moment.kind] || moment.kind}
              </span>
              {/* Empty when the coach wrote nothing about this scene: the
                  label beside it already names the scene, and repeating that
                  name as the sentence read as a note that said nothing — ⑤
                  showed "クールダウン" twice on the threshold session
                  (#1277). */}
              <span className="col-start-2 min-w-0 text-[15px] leading-[1.7] text-ink-soft md:col-start-3">
                {textOf.get(moment.id) ?? ""}
              </span>
            </li>
          ))}
        </ol>
      )}
    </SectionBlock>
  );
}
