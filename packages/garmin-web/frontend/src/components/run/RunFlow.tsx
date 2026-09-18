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
import type { RunMoment, RunNoteTimelineItem, SplitRow } from "../../types";
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
  climb: "登り",
  fade: "ペース低下",
  surge: "ペースアップ",
  strong_finish: "終盤の粘り",
  walk_break: "歩き",
  ceiling_touch: "上限到達",
  self_correction: "立て直し",
  steady: "一定ペース",
};

const PACE_GRID = { left: 56, right: 16, top: 24, height: 88 } as const;
const HR_GRID = { left: 56, right: 16, top: 152, height: 88 } as const;
/** Room under the lower panel for its km labels. */
const CHART_HEIGHT = 276;

/** Splits shorter than this are lap-press fragments, not kilometres (#873). */
const MIN_SPLIT_KM = 0.4;

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** "3 km" for a one-kilometre scene, "3–5 km" for a longer one. */
export function kmRangeLabel(moment: RunMoment): string {
  return moment.km_from === moment.km_to
    ? `${moment.km_from} km`
    : `${moment.km_from}–${moment.km_to} km`;
}

/** The kilometres of the run, as the category axis labels them. */
function kmLabels(splits: SplitRow[]): string[] {
  return splits.map((split) => String(split.split_index));
}

/**
 * The chart the run's shape is read off: pace above, heart rate below.
 *
 * The two are stacked on a shared kilometre axis rather than overlaid on dual
 * axes: a pace line and an HR line share no unit and no scale, so a crossing
 * of the two means nothing and the reader spends their attention deciding
 * which axis each line belongs to. Stacked, each panel is read on its own and
 * the kilometre they share does the comparing.
 */
export function runFlowOption(
  splits: SplitRow[],
  moments: RunMoment[],
  hrCeiling: number | null,
): EChartsOption {
  const labels = kmLabels(splits);
  const paceValues = splits.map((split) =>
    (split.distance ?? 0) >= MIN_SPLIT_KM
      ? asNumber(split.pace_seconds_per_km)
      : null,
  );
  const hrValues = splits.map((split) => asNumber(split.heart_rate));
  const maxHrValues = splits.map((split) => asNumber(split.max_heart_rate));

  // One band per scene, alternating washes so neighbours stay countable.
  const markArea = {
    silent: true,
    data: moments.map((moment, index) => [
      {
        xAxis: String(moment.km_from),
        itemStyle: { color: SCENE_TINTS[index % SCENE_TINTS.length] },
        label: {
          show: true,
          position: "insideTop" as const,
          formatter: SCENE_MARKERS[index] ?? String(index + 1),
          color: AXIS_LABEL_COLOR,
          fontSize: CHART_FONT_SIZE,
          fontFamily: CHART_FONT_FAMILY,
        },
      },
      { xAxis: String(moment.km_to) },
    ]),
  };

  // A hairline where each band starts: without it two adjacent washes read as
  // one band with a slight gradient.
  const boundaries = moments.map((moment) => ({
    xAxis: String(moment.km_from),
    lineStyle: { color: GRID_LINE_COLOR, type: "solid" as const, width: 1 },
    label: { show: false },
  }));

  return {
    animation: false,
    textStyle: {
      fontSize: CHART_FONT_SIZE,
      fontFamily: CHART_FONT_FAMILY,
      color: AXIS_LABEL_COLOR,
    },
    axisPointer: { link: [{ xAxisIndex: "all" }] },
    tooltip: { trigger: "axis" },
    grid: [PACE_GRID, HR_GRID],
    xAxis: [0, 1].map((index) => ({
      type: "category" as const,
      gridIndex: index,
      data: labels,
      axisLabel: {
        show: index === 1,
        color: AXIS_LABEL_COLOR,
        fontSize: CHART_FONT_SIZE,
        fontFamily: CHART_FONT_FAMILY,
        hideOverlap: true,
      },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { show: false },
    })),
    yAxis: [
      {
        type: "value" as const,
        gridIndex: 0,
        name: "ペース",
        nameTextStyle: { color: AXIS_LABEL_COLOR, fontSize: CHART_FONT_SIZE },
        nameLocation: "start" as const,
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
        gridIndex: 1,
        name: "心拍",
        nameTextStyle: { color: AXIS_LABEL_COLOR, fontSize: CHART_FONT_SIZE },
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
    series: [
      {
        name: "ペース",
        type: "line" as const,
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: paceValues,
        itemStyle: { color: METRIC_COLORS.speed },
        lineStyle: { color: METRIC_COLORS.speed },
        showSymbol: false,
        connectNulls: false,
        markArea,
        markLine: { silent: true, symbol: "none" as const, data: boundaries },
        tooltip: {
          valueFormatter: (value: unknown) =>
            typeof value === "number" ? `${formatPaceLabel(value)}/km` : "-",
        },
      },
      {
        name: "心拍",
        type: "line" as const,
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: hrValues,
        itemStyle: { color: METRIC_COLORS.heart_rate },
        lineStyle: { color: METRIC_COLORS.heart_rate },
        showSymbol: false,
        connectNulls: false,
        markArea,
        markLine: {
          silent: true,
          symbol: "none" as const,
          data: [
            ...boundaries,
            // The prescribed cap, dotted in the 注意 hue: a stretch spent above
            // it is then visible in the shape of the line, not only in prose.
            ...(hrCeiling != null
              ? [
                  {
                    yAxis: hrCeiling,
                    lineStyle: {
                      type: "dotted" as const,
                      color: THRESHOLD_LINE.warn,
                    },
                    label: {
                      show: true,
                      formatter: `上限 ${Math.round(hrCeiling)}`,
                      position: "insideEndTop" as const,
                      color: THRESHOLD_LINE.warn,
                      fontSize: CHART_FONT_SIZE,
                      fontFamily: CHART_FONT_FAMILY,
                    },
                  },
                ]
              : []),
          ],
        },
      },
      {
        // The peak of each kilometre as a hollow ring: the average line says
        // how hard the kilometre was, the ring says how hard its hardest
        // moment was, and a ring far above its line is what a surge looks like.
        name: "最大心拍",
        type: "scatter" as const,
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: maxHrValues,
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
 * ランの流れ (#1252): the shape of the run, its scenes numbered on the chart
 * and told in one line each underneath.
 *
 * The scenes are deterministic (`report.moments`); the sentences are the
 * coach's (`run_note.timeline`), joined on the moment id. A scene the coach
 * did not write about keeps its band and its kilometres — the run happened
 * whether or not there was anything to say about it.
 */
export default function RunFlow({
  id,
  splits,
  moments,
  timeline,
  hrCeiling,
}: {
  id?: string;
  splits: SplitRow[];
  moments: RunMoment[];
  timeline: RunNoteTimelineItem[];
  hrCeiling: number | null;
}): JSX.Element | null {
  if (splits.length === 0 && moments.length === 0) {
    return null;
  }
  const textOf = new Map(timeline.map((item) => [item.moment_id, item.text]));

  return (
    <SectionBlock id={id} title="ランの流れ">
      {splits.length > 0 && (
        <EChart
          option={runFlowOption(splits, moments, hrCeiling)}
          ariaLabel="ペースと心拍の推移"
          height={CHART_HEIGHT}
        />
      )}
      {moments.length > 0 && (
        <ol className="mt-4 flex flex-col gap-2">
          {moments.map((moment, index) => (
            <li
              key={moment.id}
              className="grid grid-cols-[1.5rem_5.5rem_minmax(0,1fr)] items-baseline gap-x-2 gap-y-1"
            >
              <span aria-hidden="true" className="font-mono text-ink-muted">
                {SCENE_MARKERS[index] ?? index + 1}
              </span>
              <span className="font-mono text-[13px] whitespace-nowrap text-ink-muted">
                {kmRangeLabel(moment)}
              </span>
              <span className="min-w-0 text-[15px] leading-[1.7] text-ink-soft">
                {textOf.get(moment.id) ??
                  KIND_LABELS[moment.kind] ??
                  moment.kind}
              </span>
            </li>
          ))}
        </ol>
      )}
    </SectionBlock>
  );
}
