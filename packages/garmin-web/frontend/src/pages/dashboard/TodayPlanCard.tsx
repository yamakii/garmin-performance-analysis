import type { JSX } from "react";
import { useActivities, usePlannedWorkoutToday } from "../../api/hooks";
import StatusBadge from "../../components/StatusBadge";
import type { ActivitySummary, PlannedWorkoutToday } from "../../types";

/** sec/km -> "M:SS" (no unit). */
function formatPace(secondsPerKm: number): string {
  const minutes = Math.floor(secondsPerKm / 60);
  const seconds = Math.round(secondsPerKm % 60);
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

/** A pace target as "M:SS〜M:SS/km", or a single value when the band collapses. */
function formatPaceTarget(
  low: number | null,
  high: number | null,
): string | null {
  if (low == null && high == null) return null;
  if (low != null && high != null && low !== high) {
    return `${formatPace(low)}〜${formatPace(high)}/km`;
  }
  const value = (low ?? high) as number;
  return `${formatPace(value)}/km`;
}

/** An HR target as "lo〜hi bpm", or a single value when the band collapses. */
function formatHrTarget(
  low: number | null,
  high: number | null,
): string | null {
  if (low == null && high == null) return null;
  if (low != null && high != null && low !== high) {
    return `${low}〜${high} bpm`;
  }
  return `${low ?? high} bpm`;
}

/**
 * In-band check shared by pace and HR (plan_achievement's判定式): the actual
 * value counts as 達成 when it lands within the prescribed target band. A
 * one-sided band treats the present bound as both edges' guide.
 */
function withinBand(
  actual: number | null,
  low: number | null,
  high: number | null,
): boolean | null {
  if (actual == null || (low == null && high == null)) return null;
  const lo = low ?? high;
  const hi = high ?? low;
  return (lo as number) <= actual && actual <= (hi as number);
}

/** A checkmark / cross achievement mark (matches PlanAchievement's marks). */
function Mark({ achieved }: { achieved: boolean | null }): JSX.Element | null {
  if (achieved == null) return null;
  return achieved ? (
    <span className="ml-1.5 font-semibold text-status-good">✓</span>
  ) : (
    <span className="ml-1.5 font-semibold text-status-warn">✗</span>
  );
}

/** One 目標→実績 comparison row with an optional achievement mark. */
function CompareRow({
  label,
  target,
  actual,
  achieved,
}: {
  label: string;
  target: string | null;
  actual: string | null;
  achieved: boolean | null;
}): JSX.Element | null {
  if (target == null && actual == null) return null;
  return (
    <p className="text-sm text-slate-700">
      <span className="font-semibold text-slate-500">{label}</span>
      <span className="ml-1.5 tabular-nums">
        {target != null && <span>目標 {target}</span>}
        {target != null && actual != null && (
          <span className="mx-1 text-slate-400">→</span>
        )}
        {actual != null && <span>実績 {actual}</span>}
      </span>
      <Mark achieved={achieved} />
    </p>
  );
}

function CardShell({ children }: { children: React.ReactNode }): JSX.Element {
  return (
    <section
      aria-label="今日の予定と実績"
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <h2 className="mb-3 font-display text-base font-semibold text-ink">
        今日の予定と実績
      </h2>
      {children}
    </section>
  );
}

/**
 * "今日の予定 vs 実績" card. Contrasts the day's planned session (from the
 * training plan) with the actual run:
 *  - plan + actual  → 目標→実績 comparison with 達成/未達 badges
 *  - plan, no actual → "本日の予定" targets only
 *  - no plan         → rest-day message
 */
export function TodayPlanCard({ date }: { date: string }): JSX.Element {
  const plannedQuery = usePlannedWorkoutToday(date);
  const activitiesQuery = useActivities();

  if (plannedQuery.isLoading || activitiesQuery.isLoading) {
    return (
      <CardShell>
        <p className="text-sm text-slate-400">読み込み中...</p>
      </CardShell>
    );
  }

  const planned: PlannedWorkoutToday | null = plannedQuery.data ?? null;
  const activities: ActivitySummary[] = activitiesQuery.data ?? [];
  const actual: ActivitySummary | null =
    activities.find((a) => a.activity_date === date) ?? null;

  // Rest day: nothing scheduled.
  if (planned == null) {
    return (
      <CardShell>
        <div className="flex items-center gap-2">
          <StatusBadge tone="info">休養日</StatusBadge>
          <p className="text-sm text-slate-500">
            本日の予定はありません。休養日です。
          </p>
        </div>
      </CardShell>
    );
  }

  const paceTarget = formatPaceTarget(
    planned.target_pace_low,
    planned.target_pace_high,
  );
  const hrTarget = formatHrTarget(planned.target_hr_low, planned.target_hr_high);

  // Planned but not yet run: show the prescription only.
  if (actual == null) {
    return (
      <CardShell>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <StatusBadge tone="info">本日の予定</StatusBadge>
          {planned.description_ja != null && (
            <span className="text-sm font-medium text-slate-800">
              {planned.description_ja}
            </span>
          )}
        </div>
        <div className="space-y-1.5">
          {planned.target_distance_km != null && (
            <p className="text-sm text-slate-700">
              <span className="font-semibold text-slate-500">距離</span>
              <span className="ml-1.5 tabular-nums">
                {planned.target_distance_km} km
              </span>
            </p>
          )}
          <CompareRow
            label="ペース"
            target={paceTarget}
            actual={null}
            achieved={null}
          />
          <CompareRow label="HR" target={hrTarget} actual={null} achieved={null} />
        </div>
      </CardShell>
    );
  }

  // Planned and run: compare target vs actual.
  const actualPace = actual.avg_pace_seconds_per_km;
  const actualHr = actual.avg_heart_rate;
  const paceAchieved = withinBand(
    actualPace,
    planned.target_pace_low,
    planned.target_pace_high,
  );
  const hrAchieved = withinBand(
    actualHr,
    planned.target_hr_low,
    planned.target_hr_high,
  );

  // Overall verdict prefers pace; falls back to HR when pace has no target.
  const overall = paceAchieved ?? hrAchieved;

  return (
    <CardShell>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        {overall != null &&
          (overall ? (
            <StatusBadge tone="good">達成</StatusBadge>
          ) : (
            <StatusBadge tone="warn">未達</StatusBadge>
          ))}
        {planned.description_ja != null && (
          <span className="text-sm font-medium text-slate-800">
            {planned.description_ja}
          </span>
        )}
      </div>
      <div className="space-y-1.5">
        <CompareRow
          label="ペース"
          target={paceTarget}
          actual={actualPace != null ? `${formatPace(actualPace)}/km` : null}
          achieved={paceAchieved}
        />
        <CompareRow
          label="HR"
          target={hrTarget}
          actual={actualHr != null ? `${actualHr} bpm` : null}
          achieved={hrAchieved}
        />
      </div>
    </CardShell>
  );
}

export default TodayPlanCard;
