import { useEffect, useRef } from "react";
import * as echarts from "echarts";

interface EChartProps {
  option: echarts.EChartsOption;
  ariaLabel: string;
  height?: number;
}

/** Thin wrapper rendering an Apache ECharts chart into a div. */
export default function EChart({ option, ariaLabel, height = 300 }: EChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }
    const chart = echarts.init(container);
    chart.setOption(option);
    const handleResize = () => chart.resize();
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      chart.dispose();
    };
  }, [option]);

  return (
    <div
      ref={containerRef}
      role="img"
      aria-label={ariaLabel}
      style={{ width: "100%", height }}
    />
  );
}
