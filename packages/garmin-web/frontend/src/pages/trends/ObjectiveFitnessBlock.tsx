import { useMemo } from "react";
import EChart from "../../components/EChart";
import {
  AXIS_STYLE,
  BASE_CHART_OPTION,
  INK_COLOR,
  METRIC_COLORS,
} from "../../components/chartTheme";
import type { ObjectiveFitnessTrend } from "../../api/trends";

interface ObjectiveFitnessBlockProps {
  data: ObjectiveFitnessTrend;
}

const GARMIN_SERIES = "Garmin VO2max";
const OBJECTIVE_SERIES = "客観VDOT";

/**
 * Overlays the objective (real-run derived) fitness curve on Garmin's VO2max
 * series on a shared VDOT/VO2max axis, surfacing the optimism gap (how much
 * faster Garmin's estimate looks than actual best-effort performance).
 */
export default function ObjectiveFitnessBlock({
  data,
}: ObjectiveFitnessBlockProps) {
  const { objective_curve, garmin_vo2max, optimism_gap } = data;

  // Shared category axis: union of both series' dates, ascending.
  const dates = useMemo(
    () =>
      Array.from(
        new Set([
          ...garmin_vo2max.map((p) => p.date),
          ...objective_curve.map((p) => p.date),
        ]),
      ).sort(),
    [garmin_vo2max, objective_curve],
  );

  const option = useMemo(
    () => ({
      ...BASE_CHART_OPTION,
      tooltip: { trigger: "axis" as const },
      legend: { data: [GARMIN_SERIES, OBJECTIVE_SERIES] },
      xAxis: {
        type: "category" as const,
        data: dates,
        ...AXIS_STYLE,
      },
      yAxis: [
        {
          type: "value" as const,
          name: "VDOT / VO2max",
          scale: true,
          ...AXIS_STYLE,
        },
      ],
      series: [
        {
          name: GARMIN_SERIES,
          type: "line" as const,
          itemStyle: { color: METRIC_COLORS.heart_rate },
          lineStyle: { color: METRIC_COLORS.heart_rate },
          data: garmin_vo2max.map((p) => [p.date, p.value]),
        },
        {
          name: OBJECTIVE_SERIES,
          type: "line" as const,
          itemStyle: { color: INK_COLOR },
          lineStyle: { color: INK_COLOR },
          data: objective_curve.map((p) => [p.date, p.vdot]),
        },
      ],
    }),
    [dates, garmin_vo2max, objective_curve],
  );

  const isEmpty =
    garmin_vo2max.length === 0 && objective_curve.length === 0;

  return (
    <section
      aria-label="客観フィットネス曲線"
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <h2 className="mb-1 font-display text-base font-semibold text-ink">
        客観フィットネス曲線 (実走VDOT vs Garmin VO2max)
      </h2>
      {isEmpty ? (
        <p className="py-8 text-center text-sm text-slate-500">
          データがありません
        </p>
      ) : (
        <>
          <p className="mb-1 text-sm text-slate-600">
            <span className="font-semibold text-ink">{GARMIN_SERIES}</span> と{" "}
            <span className="font-semibold text-ink">{OBJECTIVE_SERIES}</span>{" "}
            (rolling 90日 best-effort) の重ね描き。
          </p>
          {optimism_gap != null && (
            <p className="mb-1 text-sm text-amber-700">
              楽観ギャップ: {optimism_gap.gap_vdot.toFixed(1)} VDOT（実走比 約{" "}
              {optimism_gap.gap_pace_sec_per_km.toFixed(0)} s/km 速く見積もり）
            </p>
          )}
          <EChart
            option={option}
            ariaLabel="実走VDOTとGarmin VO2maxの推移グラフ"
          />
        </>
      )}
    </section>
  );
}
