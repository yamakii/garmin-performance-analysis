import { Link } from "react-router-dom";
import { useActivities } from "../api/hooks";
import SectionHeading from "../components/SectionHeading";
import type { ActivitySummary } from "../types";

export function formatPace(secondsPerKm: number | null): string {
  if (secondsPerKm == null || secondsPerKm <= 0) {
    return "-";
  }
  let minutes = Math.floor(secondsPerKm / 60);
  let seconds = Math.round(secondsPerKm % 60);
  if (seconds === 60) {
    minutes += 1;
    seconds = 0;
  }
  return `${minutes}:${String(seconds).padStart(2, "0")}/km`;
}

export function formatDistance(km: number | null): string {
  if (km == null) {
    return "-";
  }
  return `${km.toFixed(2)} km`;
}

export function formatCadence(cadence: number | null): string {
  if (cadence == null) {
    return "-";
  }
  return String(Math.round(cadence));
}

/** "N本 ・ 合計 XX.X km" summary for a month heading (Issue #214). */
export function monthSummary(activities: ActivitySummary[]): string {
  const totalKm = activities.reduce(
    (sum, activity) => sum + (activity.total_distance_km ?? 0),
    0,
  );
  return `${activities.length}本 ・ 合計 ${totalKm.toFixed(1)} km`;
}

function groupByMonth(
  activities: ActivitySummary[],
): Map<string, ActivitySummary[]> {
  const groups = new Map<string, ActivitySummary[]>();
  for (const activity of activities) {
    const month = activity.activity_date.slice(0, 7); // YYYY-MM
    const group = groups.get(month);
    if (group) {
      group.push(activity);
    } else {
      groups.set(month, [activity]);
    }
  }
  return groups;
}

export default function ActivityList() {
  const { data, isPending, error } = useActivities();
  const activities = data ?? [];

  if (isPending) {
    return (
      <div className="flex items-center justify-center gap-3 py-16 text-sm text-slate-500">
        <span
          aria-hidden="true"
          className="h-5 w-5 animate-spin rounded-full border-2 border-slate-300 border-t-ink"
        />
        読み込み中...
      </div>
    );
  }
  if (error) {
    return (
      <p
        role="alert"
        className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
      >
        エラー: {error.message}
      </p>
    );
  }
  if (activities.length === 0) {
    return (
      <p className="rounded-xl border border-slate-200 bg-white px-4 py-12 text-center text-sm text-slate-500 shadow-sm">
        アクティビティがありません
      </p>
    );
  }

  const groups = groupByMonth(activities);

  return (
    <div>
      <div className="mb-6">
        <SectionHeading eyebrow="Activities" title="アクティビティ一覧" />
      </div>
      {[...groups.entries()].map(([month, monthActivities]) => (
        <section key={month} className="mb-8">
          <h2 className="mb-2 flex items-baseline gap-3 text-sm font-semibold text-slate-500">
            <span className="font-numeric text-base text-ink">{month}</span>
            <span className="font-normal">{monthSummary(monthActivities)}</span>
          </h2>
          <ul className="stagger-in space-y-2">
            {monthActivities.map((activity) => (
              <li key={activity.activity_id}>
                <Link
                  to={`/activities/${activity.activity_id}`}
                  className="flex items-center gap-4 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm transition-[box-shadow,border-color] hover:border-signal/50 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal/50"
                >
                  <span className="shrink-0 rounded-md bg-ink/5 px-2 py-1 font-numeric text-sm font-semibold tabular-nums text-ink">
                    {activity.activity_date}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-sm font-medium text-slate-800">
                    {activity.activity_name ?? "-"}
                  </span>
                  <span className="flex shrink-0 items-baseline divide-x divide-slate-200 text-right font-numeric tabular-nums text-slate-700">
                    <span className="pr-3">
                      <span className="text-base font-semibold text-slate-800">
                        {formatDistance(activity.total_distance_km).replace(
                          " km",
                          "",
                        )}
                      </span>
                      <span className="ml-0.5 text-xs font-normal text-slate-400">
                        km
                      </span>
                    </span>
                    <span className="px-3">
                      <span className="text-base">
                        {formatPace(activity.avg_pace_seconds_per_km).replace(
                          "/km",
                          "",
                        )}
                      </span>
                      <span className="ml-0.5 text-xs text-slate-400">/km</span>
                    </span>
                    <span className="pl-3">
                      <span className="text-base">
                        {activity.avg_heart_rate ?? "-"}
                      </span>
                      <span className="ml-0.5 text-xs text-slate-400">bpm</span>
                    </span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
