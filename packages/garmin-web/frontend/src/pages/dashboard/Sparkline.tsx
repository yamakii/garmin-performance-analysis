import { useMemo } from "react";
import EChart from "../../components/EChart";
import { formatNumber } from "../../utils/formatNumber";

interface SparklineProps {
  /** Series values, index-aligned with `labels`. Nulls are connected over. */
  data: (number | null)[];
  /** X labels (dates) surfaced only in the hover tooltip. */
  labels: string[];
  color: string;
  type?: "line" | "bar";
  height?: number;
  ariaLabel: string;
  /** Tooltip value precision. */
  decimals?: number;
  unit?: string;
}

/**
 * Axis-less mini chart for the dashboard snapshot tiles. Single series only
 * (identity is carried by the tile heading, so no legend); the hover tooltip
 * is the sole way to read exact values, keeping the tile quiet at rest.
 */
export default function Sparkline({
  data,
  labels,
  color,
  type = "line",
  height = 56,
  ariaLabel,
  decimals = 0,
  unit = "",
}: SparklineProps) {
  const option = useMemo(
    () => ({
      grid: { left: 2, right: 2, top: 6, bottom: 2 },
      tooltip: {
        trigger: "axis" as const,
        confine: true,
        formatter: (params: unknown) => {
          const list = Array.isArray(params) ? params : [params];
          const p = list[0] as { axisValueLabel?: string; value?: unknown };
          const value = typeof p.value === "number" ? p.value : null;
          return `${p.axisValueLabel ?? ""}<br/><b>${formatNumber(value, decimals)}${unit}</b>`;
        },
      },
      xAxis: {
        type: "category" as const,
        data: labels,
        show: false,
      },
      yAxis: { type: "value" as const, show: false, scale: true },
      series: [
        type === "line"
          ? {
              type: "line" as const,
              data,
              connectNulls: true,
              showSymbol: false,
              lineStyle: { color, width: 2 },
              itemStyle: { color },
            }
          : {
              type: "bar" as const,
              data,
              barCategoryGap: "25%",
              itemStyle: { color, borderRadius: [2, 2, 0, 0] },
            },
      ],
    }),
    [data, labels, color, type, decimals, unit],
  );

  return <EChart option={option} ariaLabel={ariaLabel} height={height} />;
}
