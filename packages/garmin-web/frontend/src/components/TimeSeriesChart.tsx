import { echarts, type EChartsOption } from "../lib/echarts";
import { useEffect, useRef } from "react";
import type { TimeSeriesResponse } from "../types";
import { formatNumber } from "../utils/formatNumber";
import { robustAxisBounds, type AxisBounds } from "../utils/robustBounds";
import {
  AXIS_LABEL_COLOR,
  CHART_FONT_SIZE,
  GRID_LINE_COLOR,
  INK_COLOR,
  METRIC_COLORS,
  METRIC_DECIMALS,
  THRESHOLD_LINE,
} from "./chartTheme";
import { axisUnitFor, threeTickAxis } from "./timeSeriesAxis";

const GRID_HEIGHT = 64;
const GRID_GAP = 36;
const GRID_TOP = 20;
/** Room under the last grid for its x labels and the zoom slider. */
const SLIDER_BAND = 40;

/**
 * Chart height for `metricCount` stacked grids — 260px at the default two
 * metrics (#1153).
 *
 * The chart used to be sized at 140px per grid plus 50px of gap, which put the
 * two default metrics at 480px: a screenful of chrome for two lines, and the
 * run's shape pushed below the fold. The Morning Brief spec sizes the pair at
 * 260px instead, so each extra metric the reader toggles on adds exactly one
 * grid band (100px) rather than re-proportioning the ones already drawn.
 */
export function timeSeriesHeight(metricCount: number): number {
  return GRID_TOP + metricCount * (GRID_HEIGHT + GRID_GAP) + SLIDER_BAND;
}

export function formatElapsed(totalSeconds: number): string {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = Math.floor(totalSeconds % 60);
  const mmss = `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  return hours > 0 ? `${hours}:${mmss}` : mmss;
}

export function formatPaceLabel(secondsPerKm: number): string {
  const minutes = Math.floor(secondsPerKm / 60);
  const seconds = Math.round(secondsPerKm % 60);
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

/** speed (m/s) -> pace (sec/km); null for non-positive speeds. */
function speedToPace(value: number | null): number | null {
  if (value == null || value <= 0) {
    return null;
  }
  return Math.round(1000 / value);
}

/**
 * Plot range for the pace axis, with stops trimmed off (Issue #1148).
 *
 * A run holds still at traffic lights and water stops, and those samples reach
 * the series as 16:00/km-ish paces. Auto-scaling to them squeezed the running
 * paces — the reason the chart exists — into the top quarter of the grid, so
 * the axis is bounded by the robust percentile/IQR range instead. ECharts
 * clips the spikes at the top edge; the data itself is untouched, so tooltips
 * still report the real pace of a stopped sample.
 *
 * Returns null for a series with fewer than two paces, where there is no
 * spread to speak of and `scale: true` is the better default.
 */
export function paceAxisBounds(paces: (number | null)[]): AxisBounds | null {
  const finite = paces.filter(
    (v): v is number => typeof v === "number" && Number.isFinite(v),
  );
  return finite.length < 2 ? null : robustAxisBounds(finite);
}

const HOVER_THROTTLE_MS = 50;

/**
 * Stacked line charts (one grid per metric) with a shared x axis:
 * dataZoom and axisPointer are linked across all grids.
 * The "speed" metric is displayed as pace (min/km, inverted axis).
 *
 * Hover sync (Issue #200): onHoverIndex reports the hovered data index
 * (throttled 50ms); hoverIndex shows the tooltip at an externally chosen
 * index (e.g. driven by the GPS map).
 *
 * The frame follows the Morning Brief chart rules (#1118): horizontal grid
 * lines only, no axis lines, and the prescribed HR ceiling drawn as a dotted
 * `markLine` on the heart-rate grid, so a stretch spent over the cap is
 * visible in the shape of the line instead of only in the prose.
 */
export default function TimeSeriesChart({
  data,
  metricLabels,
  hoverIndex = null,
  onHoverIndex,
  hrCeiling = null,
}: {
  data: TimeSeriesResponse;
  metricLabels: Record<string, string>;
  hoverIndex?: number | null;
  onHoverIndex?: (index: number | null) => void;
  /** Prescribed HR cap for the day; drawn on the heart-rate grid only. */
  hrCeiling?: number | null;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  // "Latest callback" ref: synced in an effect (not during render) so the
  // chart's hover handler, registered once, always sees the current prop.
  const onHoverIndexRef = useRef(onHoverIndex);
  useEffect(() => {
    onHoverIndexRef.current = onHoverIndex;
  }, [onHoverIndex]);
  // Last index dispatched from the outside; suppresses re-emitting it.
  const externalIndexRef = useRef<number | null>(null);
  const lastEmitRef = useRef(0);

  const metricNames = Object.keys(data.metrics);
  const height = timeSeriesHeight(metricNames.length);
  // Canvas charts are opaque to assistive tech, so the container carries the
  // same role/label contract as EChart (Issue #913).
  const seriesLabels = metricNames.map((name) => metricLabels[name] ?? name);
  const ariaLabel =
    seriesLabels.length > 0
      ? `${seriesLabels.join("・")}の時系列グラフ`
      : "時系列グラフ";

  useEffect(() => {
    const container = containerRef.current;
    if (!container || metricNames.length === 0) {
      return;
    }
    if (!chartRef.current) {
      const chart = echarts.init(container);
      chartRef.current = chart;
      chart.on("updateAxisPointer", (event) => {
        const axesInfo = (event as { axesInfo?: { value: number }[] })
          .axesInfo;
        const index = axesInfo?.[0]?.value;
        if (index == null || index === externalIndexRef.current) {
          return;
        }
        const now = Date.now();
        if (now - lastEmitRef.current < HOVER_THROTTLE_MS) {
          return;
        }
        lastEmitRef.current = now;
        onHoverIndexRef.current?.(index);
      });
      chart.getZr().on("globalout", () => {
        externalIndexRef.current = null;
        onHoverIndexRef.current?.(null);
      });
    }

    const base = data.timestamps[0] ?? 0;
    const elapsedLabels = data.timestamps.map((t) => formatElapsed(t - base));
    const lastIndex = metricNames.length - 1;
    const allXAxisIndices = metricNames.map((_, i) => i);
    const paceValues = (data.metrics.speed ?? []).map(speedToPace);
    const paceBounds = paceAxisBounds(paceValues);

    const option: EChartsOption = {
      animation: false,
      textStyle: { fontSize: CHART_FONT_SIZE, color: AXIS_LABEL_COLOR },
      axisPointer: { link: [{ xAxisIndex: "all" }] },
      tooltip: { trigger: "axis" },
      grid: metricNames.map((_, i) => ({
        left: 80,
        right: 30,
        top: GRID_TOP + i * (GRID_HEIGHT + GRID_GAP),
        height: GRID_HEIGHT,
      })),
      xAxis: metricNames.map((_, i) => ({
        type: "category",
        gridIndex: i,
        data: elapsedLabels,
        axisLabel: {
          show: i === lastIndex,
          color: AXIS_LABEL_COLOR,
          fontSize: CHART_FONT_SIZE,
        },
        // The frame is the data: no axis line, no vertical grid (#1118).
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
        axisPointer: { show: true },
      })),
      yAxis: metricNames.map((name, i) => {
        const isPace = name === "speed";
        // The plot range: the robust (stop-clipped) bounds for pace
        // (#1148), otherwise the plain min/max of that metric's finite
        // values. Heart rate additionally grows to cover the prescribed
        // ceiling, so the dashed cap line always lands inside the axis.
        let lo: number;
        let hi: number;
        if (isPace && paceBounds != null) {
          lo = paceBounds.min;
          hi = paceBounds.max;
        } else {
          const finite = (isPace ? paceValues : data.metrics[name]).filter(
            (v): v is number => typeof v === "number" && Number.isFinite(v),
          );
          lo = finite.length > 0 ? Math.min(...finite) : 0;
          hi = finite.length > 0 ? Math.max(...finite) : 0;
        }
        if (name === "heart_rate" && hrCeiling != null) {
          lo = Math.min(lo, hrCeiling);
          hi = Math.max(hi, hrCeiling);
        }
        // Snapped to exactly three round-number labels (min/mid/max)
        // instead of ECharts' own tick choice, which crowded 4 labels on
        // heart rate and ragged mm:ss values on pace (Issue #1170).
        const axis = threeTickAxis(lo, hi, axisUnitFor(name, lo, hi));
        return {
          type: "value",
          gridIndex: i,
          name: metricLabels[name] ?? name,
          nameTextStyle: { color: AXIS_LABEL_COLOR, fontSize: CHART_FONT_SIZE },
          inverse: isPace,
          min: axis.min,
          max: axis.max,
          interval: axis.interval,
          axisLabel: {
            color: AXIS_LABEL_COLOR,
            fontSize: CHART_FONT_SIZE,
            hideOverlap: true,
            ...(isPace
              ? { formatter: (value: number) => formatPaceLabel(value) }
              : {}),
          },
          axisLine: { show: false },
          axisTick: { show: false },
          splitLine: { lineStyle: { color: GRID_LINE_COLOR } },
        };
      }),
      series: metricNames.map((name, i) => {
        const isPace = name === "speed";
        const values = isPace ? paceValues : data.metrics[name];
        // Each line carries its metric's semantic color (Issue #214),
        // matching the active toggle pill in ActivityDetail.
        const color = METRIC_COLORS[name] ?? INK_COLOR;
        // The prescribed cap belongs to heart rate, and only on a day that
        // carried a prescription to be capped by.
        const ceiling = name === "heart_rate" ? hrCeiling : null;
        return {
          name: metricLabels[name] ?? name,
          type: "line" as const,
          xAxisIndex: i,
          yAxisIndex: i,
          data: values,
          itemStyle: { color },
          lineStyle: { color },
          showSymbol: false,
          connectNulls: false,
          ...(ceiling != null
            ? {
                markLine: {
                  silent: true,
                  symbol: "none" as const,
                  lineStyle: {
                    type: "dashed" as const,
                    color: THRESHOLD_LINE.warn,
                  },
                  label: {
                    formatter: `上限 ${Math.round(ceiling)}`,
                    position: "insideEndTop" as const,
                    color: THRESHOLD_LINE.warn,
                    fontSize: CHART_FONT_SIZE,
                    fontFamily: "IBM Plex Mono",
                  },
                  data: [{ yAxis: ceiling }],
                },
              }
            : {}),
          tooltip: isPace
            ? {
                valueFormatter: (value) =>
                  typeof value === "number"
                    ? `${formatPaceLabel(value)}/km`
                    : "-",
              }
            : {
                valueFormatter: (value) =>
                  typeof value === "number"
                    ? formatNumber(value, METRIC_DECIMALS[name] ?? 1)
                    : "-",
              },
        };
      }),
      dataZoom: [
        { type: "inside", xAxisIndex: allXAxisIndices },
        { type: "slider", xAxisIndex: allXAxisIndices, bottom: 10 },
      ],
    };
    chartRef.current.setOption(option, true);
    chartRef.current.resize({ height });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, metricLabels, height, hrCeiling]);

  // Externally driven hover (map -> chart): show/hide the tooltip.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) {
      return;
    }
    externalIndexRef.current = hoverIndex;
    if (hoverIndex == null) {
      chart.dispatchAction({ type: "hideTip" });
      return;
    }
    chart.dispatchAction({
      type: "showTip",
      seriesIndex: 0,
      dataIndex: hoverIndex,
    });
  }, [hoverIndex]);

  useEffect(() => {
    const handleResize = () => chartRef.current?.resize();
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  return (
    <div
      ref={containerRef}
      role="img"
      aria-label={ariaLabel}
      style={{ width: "100%", height }}
    />
  );
}
