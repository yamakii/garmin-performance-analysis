import { useMemo } from "react";
import EChart from "../../components/EChart";
import {
  AXIS_STYLE,
  BASE_CHART_OPTION,
  INK_COLOR,
} from "../../components/chartTheme";
import { axisTooltipFormatter } from "../../utils/formatNumber";
import type { Granularity, VolumeTrendPoint } from "../../api/trends";
import { CARD_CLASS } from "../../components/Card";

interface VolumeBlockProps {
  data: VolumeTrendPoint[];
  /**
   * Display-only: which bucket the data is aggregated by. The control that
   * changes it lives at the page level (Performance), because the same choice
   * also drives the coach narration at the top of the page — a switch hidden
   * inside this card would silently rewrite content far above it (#892).
   */
  granularity: Granularity;
}

export default function VolumeBlock({ data, granularity }: VolumeBlockProps) {
  const option = useMemo(
    () => ({
      ...BASE_CHART_OPTION,
      tooltip: {
        trigger: "axis" as const,
        formatter: axisTooltipFormatter({ "距離 (km)": 1 }),
      },
      xAxis: {
        type: "category" as const,
        data: data.map((p) => p.bucket),
        ...AXIS_STYLE,
      },
      yAxis: { type: "value" as const, name: "km", ...AXIS_STYLE },
      series: [
        {
          name: "距離 (km)",
          type: "bar" as const,
          data: data.map((p) => p.distance_km),
          itemStyle: { color: INK_COLOR, borderRadius: [3, 3, 0, 0] },
        },
      ],
    }),
    [data],
  );

  return (
    <section
      aria-label="走行量"
      className={CARD_CLASS}
    >
      <h2 className="mb-3 font-display text-base font-semibold text-ink">
        走行量
      </h2>
      {data.length === 0 ? (
        <p className="py-8 text-center text-sm text-slate-500">
          データがありません
        </p>
      ) : (
        <>
          <p className="mb-2 text-sm text-slate-600">
            直近{granularity === "week" ? "週" : "月"} ({data[data.length - 1].bucket}
            ): {data[data.length - 1].distance_km.toFixed(1)} km /{" "}
            {data[data.length - 1].run_count} 回
          </p>
          <EChart option={option} ariaLabel="走行量の棒グラフ" />
        </>
      )}
    </section>
  );
}
