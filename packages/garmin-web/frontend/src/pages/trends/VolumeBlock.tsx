import { useMemo } from "react";
import EChart from "../../components/EChart";
import {
  AXIS_STYLE,
  BASE_CHART_OPTION,
  INK_COLOR,
} from "../../components/chartTheme";
import type { Granularity, VolumeTrendPoint } from "../../api/trends";

interface VolumeBlockProps {
  data: VolumeTrendPoint[];
  granularity: Granularity;
  onGranularityChange: (granularity: Granularity) => void;
}

function toggleClass(active: boolean): string {
  const base =
    "rounded-md px-3 py-1 text-sm font-medium transition-colors cursor-pointer";
  return active
    ? `${base} bg-white text-ink shadow-sm`
    : `${base} text-slate-600 hover:text-ink`;
}

export default function VolumeBlock({
  data,
  granularity,
  onGranularityChange,
}: VolumeBlockProps) {
  const option = useMemo(
    () => ({
      ...BASE_CHART_OPTION,
      tooltip: { trigger: "axis" as const },
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
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="font-display text-base font-semibold text-ink">走行量</h2>
        <div
          role="group"
          aria-label="集計単位"
          className="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-0.5"
        >
          <button
            type="button"
            aria-pressed={granularity === "week"}
            className={toggleClass(granularity === "week")}
            onClick={() => onGranularityChange("week")}
          >
            週
          </button>
          <button
            type="button"
            aria-pressed={granularity === "month"}
            className={toggleClass(granularity === "month")}
            onClick={() => onGranularityChange("month")}
          >
            月
          </button>
        </div>
      </div>
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
