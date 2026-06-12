import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchActivities } from "../api/client";
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
  const navigate = useNavigate();
  const [activities, setActivities] = useState<ActivitySummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetchActivities()
      .then((data) => {
        if (!cancelled) {
          setActivities(data);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-3 py-16 text-sm text-slate-500">
        <span
          aria-hidden="true"
          className="h-5 w-5 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-600"
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
        エラー: {error}
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
      <h1 className="mb-6 text-xl font-bold text-slate-900">
        アクティビティ一覧
      </h1>
      {[...groups.entries()].map(([month, monthActivities]) => (
        <section key={month} className="mb-8">
          <h2 className="mb-2 text-sm font-semibold text-slate-500">{month}</h2>
          <ul className="space-y-2">
            {monthActivities.map((activity) => (
              <li
                key={activity.activity_id}
                onClick={() => navigate(`/activities/${activity.activity_id}`)}
                className="flex cursor-pointer items-center gap-4 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm transition-shadow hover:shadow-md"
              >
                <span className="shrink-0 rounded-md bg-indigo-50 px-2 py-1 text-xs font-semibold tabular-nums text-indigo-700">
                  {activity.activity_date}
                </span>
                <span className="min-w-0 flex-1 truncate text-sm font-medium text-slate-800">
                  {activity.activity_name ?? "-"}
                </span>
                <span className="flex shrink-0 items-baseline gap-4 text-right text-sm tabular-nums text-slate-600">
                  <span>{formatDistance(activity.total_distance_km)}</span>
                  <span>{formatPace(activity.avg_pace_seconds_per_km)}</span>
                  <span>
                    {activity.avg_heart_rate ?? "-"}
                    <span className="ml-0.5 text-xs text-slate-400">bpm</span>
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
