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
 */
export default function TimeSeriesChart({
  data,
  metricLabels,
  hoverIndex = null,
  onHoverIndex,
}: {
  data: TimeSeriesResponse;
  metricLabels: Record<string, string>;
  hoverIndex?: number | null;
  onHoverIndex?: (index: number | null) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const onHoverIndexRef = useRef(onHoverIndex);
  onHoverIndexRef.current = onHoverIndex;
  // Last index dispatched from the outside; suppresses re-emitting it.
  const externalIndexRef = useRef<number | null>(null);
  const lastEmitRef = useRef(0);

  const metricNames = Object.keys(data.metrics);
  const height = GRID_TOP + metricNames.length * (GRID_HEIGHT + GRID_GAP) + 60;

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
        axisLine: { lineStyle: { color: GRID_LINE_COLOR } },
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
  }, [data, metricLabels, height]);

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

  return <div ref={containerRef} style={{ width: "100%", height }} />;
}
