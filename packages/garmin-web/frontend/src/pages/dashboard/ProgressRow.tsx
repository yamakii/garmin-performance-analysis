import type { JSX, ReactNode } from "react";
import { Link } from "react-router-dom";
import type { ActivitySummary, GoalRace, RaceReadiness } from "../../types";
import {
  formatBpmValue,
  formatDateLabel,
  formatDistanceKmValue,
  formatPaceValue,
} from "../../utils/format";
import {
  daysUntil,
  formatGap,
  formatTargetTime,
  pickFeaturedRace,
} from "../../utils/race";

/**
 * 進捗: where the season stands and what the last run was.
 *
 * Two columns, one number each — the countdown to the race the plan is built
 * around, and the run the reader just did. Both are teasers: the four-metric
 * prediction grid lives on /goal and the month-grouped list on /activities, so
 * the home page states the fact and links to the page that owns it instead of
 * restating either (#895).
 */
export default function ProgressRow({
  readiness,
  goals,
  activities,
}: {
  readiness: RaceReadiness | null;
  goals: GoalRace[] | null;
  activities: ActivitySummary[] | null;
}): JSX.Element {
  return (
    <section
      aria-label="進捗"
      className="grid gap-8 border-t border-hairline pt-6 md:grid-cols-2"
    >
      <RaceColumn readiness={readiness} goals={goals} />
      <div className="md:border-l md:border-hairline md:pl-8">
        <LastRun activity={activities?.[0] ?? null} />
      </div>
    </section>
  );
}

function RaceColumn({
  readiness,
  goals,
}: {
  readiness: RaceReadiness | null;
  goals: GoalRace[] | null;
}): JSX.Element | null {
  const featured = pickFeaturedRace(goals ?? []);
  const vdot = readiness?.current_vdot ?? null;
  if (featured == null && vdot == null) {
    return null;
  }

  const progress = readiness?.progress ?? null;
  const targetSeconds =
    featured?.target_time_seconds ??
    readiness?.goal?.target_time_seconds ??
    null;
  const priority = featured?.priority ?? null;

  const body: ReactNode = (
    <>
      <p className="font-mono text-xs text-ink-muted">
        {featured != null
          ? `${featured.race_name ?? "-"}${priority != null ? ` · ${priority}` : ""}`
          : "VDOT"}
      </p>
      {featured != null ? (
        <Countdown days={daysUntil(featured.race_date)} />
      ) : (
        <p className="font-mono text-[44px] leading-none font-medium text-ink">
          {vdot?.toFixed(1)}
        </p>
      )}
      {(progress != null || targetSeconds != null) && (
        <p className="font-mono text-[13px] text-ink-soft">
          {progress != null && (
            <>予測 {formatTargetTime(progress.predicted_time_seconds)}</>
          )}
          {progress != null && targetSeconds != null && " · "}
          {targetSeconds != null && <>目標 {formatTargetTime(targetSeconds)}</>}
          {progress?.gap_seconds != null && (
            <>
              {" · "}
              <span className="font-semibold text-ink">
                {formatGap(progress.gap_seconds)}
              </span>
            </>
          )}
        </p>
      )}
    </>
  );

  return featured != null ? (
    // The content names the link (#912): an aria-label here would hide the
    // race, the countdown and the prediction from anyone browsing by link.
    <Link
      to="/goal"
      className="flex flex-col gap-2 text-inherit hover:no-underline"
    >
      {body}
    </Link>
  ) : (
    <div className="flex flex-col gap-2">{body}</div>
  );
}

function Countdown({ days }: { days: number | null }): JSX.Element {
  if (days == null) {
    return <p className="text-sm text-ink-muted">日程未定</p>;
  }
  if (days < 0) {
    return <p className="text-sm text-ink-muted">開催済み</p>;
  }
  return (
    <p className="font-mono text-[44px] leading-none font-medium text-ink">
      {days}
      <span className="text-[15px] font-bold">日</span>
    </p>
  );
}

function LastRun({
  activity,
}: {
  activity: ActivitySummary | null;
}): JSX.Element {
  if (activity == null) {
    return <p className="text-sm text-ink-muted">アクティビティがありません</p>;
  }
  return (
    <div className="flex flex-col gap-2">
      <p className="font-mono text-xs text-ink-muted">
        前回 · {formatDateLabel(activity.activity_date)} ·{" "}
        {activity.activity_name ?? "-"}
      </p>
      <Link
        to={`/activities/${activity.activity_id}`}
        className="flex flex-col gap-2 text-inherit hover:no-underline"
      >
        <span className="font-mono text-[44px] leading-none font-medium text-ink">
          {formatDistanceKmValue(activity.total_distance_km, 1)}
          <span className="ml-[3px] font-sans text-[15px] font-bold">km</span>
        </span>
        <span className="font-mono text-[15px] text-ink-soft">
          {formatPaceValue(activity.avg_pace_seconds_per_km)}/km ·{" "}
          {formatBpmValue(activity.avg_heart_rate)}bpm
        </span>
      </Link>
      <p>
        <Link to="/activities" className="font-mono text-xs">
          すべてのラン →
        </Link>
      </p>
    </div>
  );
}
