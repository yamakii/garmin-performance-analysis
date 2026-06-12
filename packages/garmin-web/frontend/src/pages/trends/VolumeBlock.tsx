import { useMemo } from "react";
import EChart from "../../components/EChart";
import type { Granularity, VolumeTrendPoint } from "../../api/trends";

interface VolumeBlockProps {
  data: VolumeTrendPoint[];
  granularity: Granularity;
  onGranularityChange: (granularity: Granularity) => void;
}

export default function VolumeBlock({
  data,
  granularity,
  onGranularityChange,
}: VolumeBlockProps) {
  const option = useMemo(
    () => ({
      tooltip: { trigger: "axis" as const },
      xAxis: { type: "category" as const, data: data.map((p) => p.bucket) },
      yAxis: { type: "value" as const, name: "km" },
      series: [
        {
          name: "距離 (km)",
          type: "bar" as const,
          data: data.map((p) => p.distance_km),
        },
      ],
    }),
    [data],
  );

  return (
    <section aria-label="走行量">
      <h2>走行量</h2>
      <div role="group" aria-label="集計単位">
        <button
          type="button"
          aria-pressed={granularity === "week"}
          onClick={() => onGranularityChange("week")}
        >
          週
        </button>
        <button
          type="button"
          aria-pressed={granularity === "month"}
          onClick={() => onGranularityChange("month")}
        >
          月
        </button>
      </div>
      {data.length === 0 ? (
        <p>データがありません</p>
      ) : (
        <>
          <p>
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
