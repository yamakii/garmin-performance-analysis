import * as echarts from "echarts";
import { useEffect, useRef } from "react";
import type { TimeSeriesResponse } from "../types";

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

/**
 * Stacked line charts (one grid per metric) with a shared x axis:
 * dataZoom and axisPointer are linked across all grids.
 * The "speed" metric is displayed as pace (min/km, inverted axis).
 */
export default function TimeSeriesChart({
  data,
  metricLabels,
}: {
  data: TimeSeriesResponse;
  metricLabels: Record<string, string>;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  const metricNames = Object.keys(data.metrics);
  const height = GRID_TOP + metricNames.length * (GRID_HEIGHT + GRID_GAP) + 60;

  useEffect(() => {
    const container = containerRef.current;
    if (!container || metricNames.length === 0) {
      return;
    }
    chartRef.current ??= echarts.init(container);

    const base = data.timestamps[0] ?? 0;
    const elapsedLabels = data.timestamps.map((t) => formatElapsed(t - base));
    const lastIndex = metricNames.length - 1;
    const allXAxisIndices = metricNames.map((_, i) => i);

    const option: echarts.EChartsOption = {
      animation: false,
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
        axisLabel: { show: i === lastIndex },
        axisPointer: { show: true },
      })),
      yAxis: metricNames.map((name, i) => {
        const isPace = name === "speed";
        return {
          type: "value",
          gridIndex: i,
          name: metricLabels[name] ?? name,
          scale: true,
          inverse: isPace,
          axisLabel: isPace
            ? { formatter: (value: number) => formatPaceLabel(value) }
            : {},
        };
      }),
      series: metricNames.map((name, i) => {
        const isPace = name === "speed";
        const values = isPace
          ? data.metrics[name].map(speedToPace)
          : data.metrics[name];
        return {
          name: metricLabels[name] ?? name,
          type: "line" as const,
          xAxisIndex: i,
          yAxisIndex: i,
          data: values,
          showSymbol: false,
          connectNulls: false,
          tooltip: isPace
            ? {
                valueFormatter: (value) =>
                  typeof value === "number"
                    ? `${formatPaceLabel(value)}/km`
                    : "-",
              }
            : {},
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
