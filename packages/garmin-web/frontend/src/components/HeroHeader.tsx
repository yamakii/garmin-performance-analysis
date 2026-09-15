import type { ActivityDetailResponse } from "../types";
import {
  formatBpm,
  formatBpmValue,
  formatDate,
  formatDistanceKmValue,
  formatDuration,
  formatPaceValue,
  PACE_UNIT,
} from "../utils/format";
import StarRating from "./report/StarRating";

/**
 * Editorial Sport report hero (Issue #214): display headline, inline date +
 * gold star rating, and a rhythmic strip of big condensed KPI numerals with
 * small units — like a record table in a sports yearbook. Physiology
 * metrics (VO2max / lactate threshold) appear as a quiet sub-row; the
 * threshold shown there is the configured one, not Garmin's estimate (#1098).
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
    {
      label: "距離",
      value: formatDistanceKmValue(activity.total_distance_km),
      unit: "km",
    },
    {
      label: "時間",
      value: formatDuration(activity.total_time_seconds),
      unit: null,
    },
    {
      label: "平均ペース",
      value: formatPaceValue(activity.avg_pace_seconds_per_km),
      unit: PACE_UNIT,
    },
    {
      label: "平均心拍",
      value: formatBpmValue(activity.avg_heart_rate),
      unit: "bpm",
    },
  ];

  const subMetrics: { label: string; value: string }[] = [];
  if (detail.vo2_max?.value != null) {
    subMetrics.push({ label: "VO2 Max", value: detail.vo2_max.value.toFixed(1) });
  }
  // The threshold worth showing is the one configured on the watch — the value
  // the zones, the prescriptions and the athlete all run to. The zone table
  // records it as the lower bound of zone 5, which starts at 100% LTHR.
  //
  // Garmin's own auto-detected estimate in `lactate_threshold` is deliberately
  // NOT shown: it disagrees with the configured value (164 vs 170), it can sit
  // frozen for months (date_hr stuck at 2026-07-11), and displaying it next to
  // a zone table built from 170 leaves the reader unable to tell which number
  // is their threshold (#1098).
  const configuredLthr = detail.hr_zones.find(
    (zone) => zone.zone_number === 5,
  )?.zone_low_boundary;
  if (configuredLthr != null) {
    subMetrics.push({
      label: "乳酸閾値（設定値）",
      value: formatBpm(configuredLthr),
    });
  }

  return (
    <header className="relative overflow-hidden rounded-md border border-hairline">
      <div className="relative px-6 py-6 md:px-8 md:py-7">
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <h1 className="text-3xl font-bold tracking-tight text-ink md:text-4xl">
            {activity.activity_name ?? "アクティビティ"}
          </h1>
          <span className="font-mono text-lg text-ink-muted">
            {formatDate(activity.activity_date)}
          </span>
          {starRating && <StarRating text={starRating} />}
        </div>
        <dl className="mt-6 flex flex-wrap gap-x-10 gap-y-4">
          {kpis.map(({ label, value, unit }) => (
            <div key={label}>
              <dt className="text-xs font-medium tracking-widest text-ink-muted">
                {label}
              </dt>
              <dd className="mt-1 font-mono text-5xl leading-none font-semibold text-ink">
                {value}
                {unit && (
                  <span className="ml-1 align-baseline font-mono text-lg font-normal text-ink-muted">
                    {unit}
                  </span>
                )}
              </dd>
            </div>
          ))}
        </dl>
        {subMetrics.length > 0 && (
          <p className="mt-5 flex flex-wrap gap-x-6 gap-y-1 text-sm text-ink-muted">
            {subMetrics.map(({ label, value }) => (
              <span key={label}>
                {label}{" "}
                <span className="font-mono text-base font-semibold text-ink">
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
