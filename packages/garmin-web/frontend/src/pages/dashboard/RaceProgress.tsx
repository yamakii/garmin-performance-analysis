import { Link } from "react-router-dom";
import StatusBadge, { type StatusTone } from "../../components/StatusBadge";
import type { GoalRace, RaceReadiness } from "../../types";
import { daysUntil, formatGap, formatTargetTime } from "../Goal";

type RaceStatus = NonNullable<RaceReadiness["progress"]>["status"];

const STATUS_META: Record<RaceStatus, { label: string; tone: StatusTone }> = {
  ahead: { label: "前倒し", tone: "good" },
  on_track: { label: "順調", tone: "info" },
  behind: { label: "遅れ", tone: "warn" },
};

function priorityOf(race: GoalRace): string {
  return (race.priority ?? "").toUpperCase();
}

interface RaceProgressProps {
  readiness: RaceReadiness | null;
  goals: GoalRace[] | null;
}

/**
 * Compact "レースへの道" strip: countdown to the A/B races plus the VDOT
 * prediction vs the goal time. The full breakdown lives on the Goal page.
 */
export default function RaceProgress({ readiness, goals }: RaceProgressProps) {
  const featured = [
    (goals ?? []).find((g) => priorityOf(g) === "A") ?? null,
    (goals ?? []).find((g) => priorityOf(g) === "B") ?? null,
  ].filter((g): g is GoalRace => g != null);

  const progress = readiness?.progress ?? null;
  const statusMeta = progress != null ? STATUS_META[progress.status] : null;

  if (featured.length === 0 && readiness?.current_vdot == null) {
    return null;
  }

  return (
    <section
      aria-label="レースへの道"
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="font-display text-base font-semibold text-ink">
          レースへの道
        </h2>
        <Link
          to="/goal"
          className="text-sm font-medium text-status-info hover:underline"
        >
          目標ページ →
        </Link>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {featured.map((race) => {
          const days = daysUntil(race.race_date);
          const accent =
            priorityOf(race) === "A" ? "text-signal" : "text-gold";
          return (
            <div
              key={race.goal_id}
              className="rounded-lg border border-slate-100 bg-slate-50 p-3"
            >
              <div className="flex items-center gap-2">
                <span className="rounded-md bg-ink/5 px-1.5 py-0.5 font-numeric text-xs font-bold text-ink">
                  {race.priority ?? "?"}
                </span>
                <span className="truncate text-sm font-semibold text-ink">
                  {race.race_name ?? "-"}
                </span>
              </div>
              <div className="mt-2 flex items-end gap-1.5">
                {days == null ? (
                  <span className="text-sm font-medium text-slate-500">
                    日程未定
                  </span>
                ) : days >= 0 ? (
                  <>
                    <span className="text-xs text-slate-400">あと</span>
                    <span
                      className={`font-numeric text-4xl leading-[0.85] font-bold tabular-nums ${accent}`}
                    >
                      {days}
                    </span>
                    <span className="text-sm font-semibold text-ink">日</span>
                  </>
                ) : (
                  <span className="text-sm font-medium text-slate-500">
                    開催済み
                  </span>
                )}
              </div>
              <p className="mt-1.5 text-xs text-slate-500">
                目標{" "}
                <span className="font-numeric font-semibold tabular-nums text-slate-700">
                  {formatTargetTime(race.target_time_seconds)}
                </span>
                {race.race_date != null && (
                  <span className="ml-2 font-numeric tabular-nums">
                    {race.race_date}
                  </span>
                )}
              </p>
            </div>
          );
        })}
      </div>

      {readiness?.current_vdot != null && (
        <dl className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-slate-100 pt-3 text-sm">
          <div>
            <dt className="inline text-xs text-slate-400">現在 VDOT </dt>
            <dd className="inline font-numeric font-semibold tabular-nums text-ink">
              {readiness.current_vdot.toFixed(1)}
            </dd>
          </div>
          {progress != null && (
            <>
              <div>
                <dt className="inline text-xs text-slate-400">予測 </dt>
                <dd className="inline font-numeric font-semibold tabular-nums text-ink">
                  {formatTargetTime(progress.predicted_time_seconds)}
                </dd>
              </div>
              <div>
                <dt className="inline text-xs text-slate-400">目標との差 </dt>
                <dd className="inline font-numeric font-semibold tabular-nums text-ink">
                  {formatGap(progress.gap_seconds)}
                </dd>
              </div>
            </>
          )}
          {statusMeta != null && (
            <StatusBadge tone={statusMeta.tone}>{statusMeta.label}</StatusBadge>
          )}
        </dl>
      )}
    </section>
  );
}
