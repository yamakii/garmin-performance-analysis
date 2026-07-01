import { Link } from "react-router-dom";
import type { ActivitySummary } from "../../types";
import { formatDistance, formatPace } from "../ActivityList";

/** How many recent runs the home page shows. */
export const RECENT_RUNS_LIMIT = 5;

interface RecentRunsProps {
  activities: ActivitySummary[] | null;
}

/**
 * The last few runs as compact link rows; the full month-grouped list lives
 * at /activities.
 */
export default function RecentRuns({ activities }: RecentRunsProps) {
  const recent = (activities ?? []).slice(0, RECENT_RUNS_LIMIT);

  return (
    <section
      aria-label="最近のラン"
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="font-display text-base font-semibold text-ink">
          最近のラン
        </h2>
        <Link
          to="/activities"
          className="text-sm font-medium text-status-info hover:underline"
        >
          すべて見る →
        </Link>
      </div>

      {recent.length === 0 ? (
        <p className="py-6 text-center text-sm text-slate-500">
          アクティビティがありません
        </p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {recent.map((activity) => (
            <li key={activity.activity_id}>
              <Link
                to={`/activities/${activity.activity_id}`}
                className="flex items-center gap-3 rounded-lg px-2 py-2.5 transition-colors hover:bg-slate-50 focus-visible:ring-2 focus-visible:ring-signal/50 focus-visible:outline-none"
              >
                <span className="shrink-0 rounded-md bg-ink/5 px-2 py-0.5 font-numeric text-xs font-semibold tabular-nums text-ink">
                  {activity.activity_date}
                </span>
                <span className="min-w-0 flex-1 truncate text-sm font-medium text-slate-800">
                  {activity.activity_name ?? "-"}
                </span>
                <span className="flex shrink-0 items-baseline gap-3 font-numeric text-sm tabular-nums text-slate-600">
                  <span>
                    {formatDistance(activity.total_distance_km).replace(
                      " km",
                      "",
                    )}
                    <span className="ml-0.5 text-xs text-slate-400">km</span>
                  </span>
                  <span>
                    {formatPace(activity.avg_pace_seconds_per_km).replace(
                      "/km",
                      "",
                    )}
                    <span className="ml-0.5 text-xs text-slate-400">/km</span>
                  </span>
                  <span>
                    {activity.avg_heart_rate ?? "-"}
                    <span className="ml-0.5 text-xs text-slate-400">bpm</span>
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
