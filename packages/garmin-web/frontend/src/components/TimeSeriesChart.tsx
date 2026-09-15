import { echarts, type EChartsOption } from "../lib/echarts";
import { useEffect, useRef } from "react";
import type { TimeSeriesResponse } from "../types";
import { formatNumber } from "../utils/formatNumber";
import {
  AXIS_LABEL_COLOR,
  CHART_FONT_SIZE,
  GRID_LINE_COLOR,
  INK_COLOR,
  METRIC_COLORS,
  METRIC_DECIMALS,
  THRESHOLD_LINE,
} from "./chartTheme";

const GRID_HEIGHT = 140;
const GRID_GAP = 50;
const GRID_TOP = 40;

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
  const height = GRID_TOP + metricNames.length * (GRID_HEIGHT + GRID_GAP) + 60;
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
        return {
          type: "value",
          gridIndex: i,
          name: metricLabels[name] ?? name,
          nameTextStyle: { color: AXIS_LABEL_COLOR, fontSize: CHART_FONT_SIZE },
          scale: true,
          inverse: isPace,
          axisLabel: {
            color: AXIS_LABEL_COLOR,
            fontSize: CHART_FONT_SIZE,
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
        const values = isPace
          ? data.metrics[name].map(speedToPace)
          : data.metrics[name];
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
