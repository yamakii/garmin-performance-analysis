import type { ActivityDetailResponse } from "../types";
import StarRating from "./report/StarRating";

/**
 * Faint topographic-contour pattern (inline SVG data URI) for the hero
 * background. Stroked in ink and rendered at ~4% opacity so it reads as
 * paper texture, not decoration.
 */
const CONTOUR_PATTERN = `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='280' height='280' viewBox='0 0 280 280' fill='none' stroke='%2316213a' stroke-width='1'%3E%3Cpath d='M0 40c46-22 94 16 140-6s94-26 140-2'/%3E%3Cpath d='M0 90c46-24 94 18 140-8s94-28 140-2'/%3E%3Cpath d='M0 140c46-20 94 14 140-6s94-24 140-2'/%3E%3Cpath d='M0 190c46-26 94 20 140-8s94-30 140-2'/%3E%3Cpath d='M0 240c46-22 94 16 140-6s94-26 140-2'/%3E%3Cellipse cx='70' cy='66' rx='34' ry='13'/%3E%3Cellipse cx='70' cy='66' rx='20' ry='7'/%3E%3Cellipse cx='204' cy='214' rx='38' ry='15'/%3E%3Cellipse cx='204' cy='214' rx='22' ry='8'/%3E%3C/svg%3E")`;

/** "5.66" — number only; the unit is rendered small next to it. */
function kpiDistance(km: number | null): string {
  return km == null ? "-" : km.toFixed(2);
}

/** "36:26" or "1:02:13" */
function kpiDuration(totalSeconds: number | null): string {
  if (totalSeconds == null || totalSeconds < 0) {
    return "-";
  }
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = Math.floor(totalSeconds % 60);
  const mmss = `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  return hours > 0 ? `${hours}:${mmss}` : mmss;
}

/** "6:26" — without the "/km" suffix (rendered as the small unit). */
function kpiPace(secondsPerKm: number | null): string {
  if (secondsPerKm == null || secondsPerKm <= 0) {
    return "-";
  }
  let minutes = Math.floor(secondsPerKm / 60);
  let seconds = Math.round(secondsPerKm % 60);
  if (seconds === 60) {
    minutes += 1;
    seconds = 0;
  }
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

/**
 * Editorial Sport report hero (Issue #214): display headline, inline date +
 * gold star rating, and a rhythmic strip of big condensed KPI numerals with
 * small units — like a record table in a sports yearbook. Physiology
 * metrics (VO2max / lactate threshold) appear as a quiet sub-row.
 */
export default function HeroHeader({
  detail,
  starRating,
}: {
  detail: ActivityDetailResponse;
  starRating: string | null;
}) {
  const { activity } = detail;

  const kpis: { label: string; value: string; unit: string | null }[] = [
    { label: "距離", value: kpiDistance(activity.total_distance_km), unit: "km" },
    { label: "時間", value: kpiDuration(activity.total_time_seconds), unit: null },
    {
      label: "平均ペース",
      value: kpiPace(activity.avg_pace_seconds_per_km),
      unit: "/km",
    },
    {
      label: "平均心拍",
      value: activity.avg_heart_rate != null ? String(activity.avg_heart_rate) : "-",
      unit: "bpm",
    },
  ];

  const subMetrics: { label: string; value: string }[] = [];
  if (detail.vo2_max?.value != null) {
    subMetrics.push({ label: "VO2 Max", value: detail.vo2_max.value.toFixed(1) });
  }
  const lt = detail.lactate_threshold;
  if (lt && (lt.heart_rate != null || lt.speed_mps != null)) {
    const parts: string[] = [];
    if (lt.heart_rate != null) {
      parts.push(`${lt.heart_rate} bpm`);
    }
    if (lt.speed_mps != null && lt.speed_mps > 0) {
      parts.push(`${kpiPace(1000 / lt.speed_mps)}/km`);
    }
    subMetrics.push({ label: "乳酸閾値", value: parts.join(" / ") });
  }

  return (
    <header className="relative overflow-hidden rounded-2xl border border-slate-200 bg-gradient-to-br from-white via-slate-50 to-slate-100 shadow-sm">
      <div
        aria-hidden="true"
        className="absolute inset-0 opacity-[0.04]"
        style={{ backgroundImage: CONTOUR_PATTERN }}
      />
      <div className="relative px-6 py-6 md:px-8 md:py-7">
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <h1 className="font-display text-3xl font-bold tracking-tight text-ink md:text-4xl">
            {activity.activity_name ?? "アクティビティ"}
          </h1>
          <span className="font-numeric text-lg tabular-nums text-slate-500">
            {activity.activity_date}
          </span>
          {starRating && <StarRating text={starRating} />}
        </div>
        <dl className="mt-6 flex flex-wrap gap-x-10 gap-y-4">
          {kpis.map(({ label, value, unit }) => (
            <div key={label}>
              <dt className="text-xs font-medium tracking-widest text-slate-500">
                {label}
              </dt>
              <dd className="mt-1 font-numeric text-5xl leading-none font-semibold tabular-nums text-ink">
                {value}
                {unit && (
                  <span className="ml-1 align-baseline font-numeric text-lg font-normal text-slate-500">
                    {unit}
                  </span>
                )}
              </dd>
            </div>
          ))}
        </dl>
        {subMetrics.length > 0 && (
          <p className="mt-5 flex flex-wrap gap-x-6 gap-y-1 text-sm text-slate-600">
            {subMetrics.map(({ label, value }) => (
              <span key={label}>
                {label}{" "}
                <span className="font-numeric text-base font-semibold tabular-nums text-ink">
                  {value}
                </span>
              </span>
            ))}
          </p>
        )}
      </div>
    </header>
  );
}
