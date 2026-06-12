import { useEffect, useState } from "react";
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
    return <p>読み込み中...</p>;
  }
  if (error) {
    return <p role="alert">エラー: {error}</p>;
  }
  if (activities.length === 0) {
    return <p>アクティビティがありません</p>;
  }

  const groups = groupByMonth(activities);

  return (
    <div>
      <h1>アクティビティ一覧</h1>
      {[...groups.entries()].map(([month, monthActivities]) => (
        <section key={month}>
          <h2>{month}</h2>
          <table>
            <thead>
              <tr>
                <th>日付</th>
                <th>名前</th>
                <th>距離</th>
                <th>ペース</th>
                <th>平均HR</th>
              </tr>
            </thead>
            <tbody>
              {monthActivities.map((activity) => (
                <tr key={activity.activity_id}>
                  <td>{activity.activity_date}</td>
                  <td>{activity.activity_name ?? "-"}</td>
                  <td>{formatDistance(activity.total_distance_km)}</td>
                  <td>{formatPace(activity.avg_pace_seconds_per_km)}</td>
                  <td>{activity.avg_heart_rate ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
    </div>
  );
}
