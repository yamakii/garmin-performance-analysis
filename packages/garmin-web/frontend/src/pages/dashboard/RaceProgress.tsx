import { Link } from "react-router-dom";
import StatusBadge, { type StatusTone } from "../../components/StatusBadge";
import type { GoalRace, RaceReadiness } from "../../types";
import { daysUntil, formatTargetTime } from "../../utils/race";

type RaceStatus = NonNullable<RaceReadiness["progress"]>["status"];

const STATUS_META: Record<RaceStatus, { label: string; tone: StatusTone }> = {
  ahead: { label: "前倒し", tone: "good" },
  on_track: { label: "順調", tone: "info" },
  behind: { label: "遅れ", tone: "warn" },
};

function priorityOf(race: GoalRace): string {
  return (race.priority ?? "").toUpperCase();
}

/**
 * The one race the home page counts down to: the A race if there is one,
 * otherwise the nearest upcoming race, otherwise the first registered goal.
 */
function pickFeaturedRace(goals: GoalRace[]): GoalRace | null {
  if (goals.length === 0) {
    return null;
  }
  const aRace = goals.find((race) => priorityOf(race) === "A");
  if (aRace != null) {
    return aRace;
  }
  const upcoming = goals
    .filter((race) => (daysUntil(race.race_date) ?? -1) >= 0)
    .sort(
      (a, b) => (daysUntil(a.race_date) ?? 0) - (daysUntil(b.race_date) ?? 0),
    );
  return upcoming[0] ?? goals[0];
}

interface RaceProgressProps {
  readiness: RaceReadiness | null;
  goals: GoalRace[] | null;
}

/**
 * One-line "レースへの道" strip: countdown to the featured race plus the VDOT
 * prediction against the goal time, wrapped in a single link to `/goal`.
 *
 * Deliberately just a teaser (#895): the per-race tiles and the four-metric
 * prediction grid it used to duplicate now live only on the Goal page, so the
 * home page keeps answering "今日どう動く?" instead of restating the goal.
 */
export default function RaceProgress({ readiness, goals }: RaceProgressProps) {
  const featured = pickFeaturedRace(goals ?? []);
  const progress = readiness?.progress ?? null;
  const statusMeta = progress != null ? STATUS_META[progress.status] : null;
  const targetSeconds =
    featured?.target_time_seconds ?? readiness?.goal?.target_time_seconds ?? null;

  if (featured == null && readiness?.current_vdot == null) {
    return null;
  }

  return (
    // No `aria-label` (#912): it replaced the whole strip's accessible name
    // with three words, hiding the countdown, VDOT and prediction from anyone
    // navigating by link. The content names the link instead.
    <Link
      to="/goal"
      className="block rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition-[box-shadow,border-color] hover:border-signal/50 hover:shadow-md focus-visible:ring-2 focus-visible:ring-signal/50 focus-visible:outline-none"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <h2 className="font-display text-xs font-semibold text-slate-500">
          レースへの道
        </h2>

        {featured != null && (
          <>
            <Countdown days={daysUntil(featured.race_date)} />
            <span className="truncate text-sm font-semibold text-ink">
              {featured.race_name ?? "-"}
            </span>
          </>
        )}

        {readiness?.current_vdot != null && (
          <p className="text-xs text-slate-500">
            VDOT{" "}
            <span className="font-numeric font-semibold tabular-nums text-ink">
              {readiness.current_vdot.toFixed(1)}
            </span>
            {progress != null && (
              <>
                {" ・ 予測 "}
                <span className="font-numeric font-semibold tabular-nums text-ink">
                  {formatTargetTime(progress.predicted_time_seconds)}
                </span>
              </>
            )}
            {targetSeconds != null && (
              <>
                {" / 目標 "}
                <span className="font-numeric font-semibold tabular-nums text-ink">
                  {formatTargetTime(targetSeconds)}
                </span>
              </>
            )}
          </p>
        )}

        {statusMeta != null && (
          <StatusBadge tone={statusMeta.tone}>{statusMeta.label}</StatusBadge>
        )}

        <span className="ml-auto text-sm font-medium text-status-info">
          目標へ →
        </span>
      </div>
    </Link>
  );
}

function Countdown({ days }: { days: number | null }) {
  if (days == null) {
    return <span className="text-sm font-medium text-slate-500">日程未定</span>;
  }
  if (days < 0) {
    return <span className="text-sm font-medium text-slate-500">開催済み</span>;
  }
  return (
    <span className="flex items-baseline gap-1">
      <span className="text-xs text-slate-500">あと</span>
      <span className="font-numeric text-2xl leading-none font-bold tabular-nums text-signal">
        {days}
      </span>
      <span className="text-sm font-semibold text-ink">日</span>
    </span>
  );
}
