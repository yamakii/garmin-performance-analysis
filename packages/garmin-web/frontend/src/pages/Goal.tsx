import { useEffect, useState } from "react";
import { fetchGoal } from "../api/client";
import type { GoalResponse } from "../types";

/** Format a target time in seconds as H:MM:SS (e.g. 16200 -> "4:30:00"). */
export function formatTargetTime(seconds: number | null): string {
  if (seconds == null || seconds < 0) {
    return "-";
  }
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  return `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(
    2,
    "0",
  )}`;
}

function formatDistanceKm(km: number | null): string {
  if (km == null) {
    return "-";
  }
  return `${km.toFixed(2)} km`;
}

export default function Goal() {
  const [goal, setGoal] = useState<GoalResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetchGoal()
      .then((data) => {
        if (!cancelled) {
          setGoal(data);
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
        エラー: {error}
      </p>
    );
  }
  if (goal == null) {
    return null;
  }

  const { profile, goals, retrospectives } = goal;
  const hasProfile = profile.current_focus != null || profile.focus_notes != null;

  return (
    <div className="stagger-in space-y-6">
      <h1 className="font-display text-2xl font-bold tracking-tight text-ink">
        目標
      </h1>

      {/* Current phase */}
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="mb-3 font-display text-base font-semibold text-ink">
          現フェーズ
        </h2>
        {hasProfile ? (
          <div className="space-y-1">
            {profile.current_focus != null && (
              <p className="text-sm font-medium text-slate-800">
                {profile.current_focus}
              </p>
            )}
            {profile.focus_notes != null && (
              <p className="text-sm text-slate-600">{profile.focus_notes}</p>
            )}
            {profile.updated_at != null && (
              <p className="text-xs text-slate-400">
                更新: {profile.updated_at}
              </p>
            )}
          </div>
        ) : (
          <p className="py-4 text-center text-sm text-slate-500">
            現フェーズが登録されていません
          </p>
        )}
      </section>

      {/* Target races */}
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="mb-3 font-display text-base font-semibold text-ink">
          目標レース
        </h2>
        {goals.length > 0 ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs tracking-wide text-slate-500 uppercase">
                <th className="px-2 py-2 text-left font-medium">優先度</th>
                <th className="px-2 py-2 text-left font-medium">レース</th>
                <th className="px-2 py-2 text-left font-medium">日付</th>
                <th className="px-2 py-2 text-left font-medium">種別</th>
                <th className="px-2 py-2 text-right font-medium">目標タイム</th>
                <th className="px-2 py-2 text-right font-medium">距離</th>
                <th className="px-2 py-2 text-left font-medium">状態</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-[15px]">
              {goals.map((race) => (
                <tr key={race.goal_id} className="hover:bg-slate-50">
                  <td className="px-2 py-2 text-left">
                    <span className="rounded-md bg-ink/5 px-2 py-0.5 font-numeric text-sm font-semibold text-ink">
                      {race.priority ?? "-"}
                    </span>
                  </td>
                  <td className="px-2 py-2 text-left font-medium text-slate-800">
                    {race.race_name ?? "-"}
                  </td>
                  <td className="px-2 py-2 text-left font-numeric tabular-nums text-slate-700">
                    {race.race_date ?? "未定"}
                  </td>
                  <td className="px-2 py-2 text-left text-slate-700">
                    {race.goal_type ?? "-"}
                  </td>
                  <td className="px-2 py-2 text-right font-numeric tabular-nums text-slate-700">
                    {formatTargetTime(race.target_time_seconds)}
                  </td>
                  <td className="px-2 py-2 text-right font-numeric tabular-nums text-slate-700">
                    {formatDistanceKm(race.distance_km)}
                  </td>
                  <td className="px-2 py-2 text-left text-slate-700">
                    {race.status ?? "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="py-4 text-center text-sm text-slate-500">
            目標レースが登録されていません
          </p>
        )}
      </section>

      {/* Season retrospectives */}
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="mb-3 font-display text-base font-semibold text-ink">
          昨季の振り返り
        </h2>
        {retrospectives.length > 0 ? (
          <ul className="space-y-4">
            {retrospectives.map((retro) => (
              <li key={retro.retro_id} className="space-y-1">
                <div className="flex items-baseline gap-3">
                  <span className="font-display text-sm font-semibold text-ink">
                    {retro.season_label ?? "シーズン"}
                  </span>
                  {(retro.period_start != null || retro.period_end != null) && (
                    <span className="font-numeric text-xs tabular-nums text-slate-400">
                      {retro.period_start ?? "?"} 〜 {retro.period_end ?? "?"}
                    </span>
                  )}
                </div>
                {retro.narrative != null && (
                  <p className="text-sm text-slate-700">{retro.narrative}</p>
                )}
                {retro.key_learnings != null && (
                  <p className="text-sm text-slate-600">
                    <span className="font-medium text-slate-500">学び: </span>
                    {retro.key_learnings}
                  </p>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="py-4 text-center text-sm text-slate-500">
            振り返りが登録されていません
          </p>
        )}
      </section>
    </div>
  );
}
