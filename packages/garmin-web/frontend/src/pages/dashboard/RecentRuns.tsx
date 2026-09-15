import { Link } from "react-router-dom";
import type { ActivitySummary } from "../../types";
import {
  formatBpmValue,
  formatDate,
  formatDistanceKmValue,
  formatPaceValue,
} from "../../utils/format";
import { CARD_CLASS } from "../../components/Card";

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
      className={CARD_CLASS}
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-base font-semibold text-ink">
          最近のラン
        </h2>
        <Link
          to="/activities"
          className="text-sm font-medium text-accent hover:underline"
        >
          すべて見る →
        </Link>
      </div>

      {recent.length === 0 ? (
        <p className="py-6 text-center text-sm text-ink-muted">
          アクティビティがありません
        </p>
      ) : (
        <ul className="divide-y divide-hairline">
          {recent.map((activity) => (
            <li key={activity.activity_id}>
              <Link
                to={`/activities/${activity.activity_id}`}
                className="flex items-center gap-3 rounded-md px-2 py-2.5 transition-colors hover:bg-surface focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none"
              >
                <span className="shrink-0 rounded-md bg-well px-2 py-0.5 font-mono text-xs font-semibold text-ink">
                  {formatDate(activity.activity_date)}
                </span>
                <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink-soft">
                  {activity.activity_name ?? "-"}
                </span>
                <span className="flex shrink-0 items-baseline gap-3 font-mono text-sm text-ink-muted">
                  <span>
                    {formatDistanceKmValue(activity.total_distance_km)}
                    <span className="ml-0.5 text-xs text-ink-muted">km</span>
                  </span>
                  <span>
                    {formatPaceValue(activity.avg_pace_seconds_per_km)}
                    <span className="ml-0.5 text-xs text-ink-muted">/km</span>
                  </span>
                  <span>
                    {formatBpmValue(activity.avg_heart_rate)}
                    <span className="ml-0.5 text-xs text-ink-muted">bpm</span>
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
