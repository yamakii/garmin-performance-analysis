import {
  useActivities,
  useFormAnomalyFlags,
  useGoal,
  useRaceReadiness,
  useRecoveryStatus,
  useRecoveryTrend,
  useTrainingLoad,
  useWeeklyReviews,
  useWellnessBaselineDeviation,
} from "../api/hooks";
import CardSkeleton from "../components/CardSkeleton";
import SectionHeading from "../components/SectionHeading";
import RaceProgress from "./dashboard/RaceProgress";
import RecentRuns from "./dashboard/RecentRuns";
import SnapshotTiles from "./dashboard/SnapshotTiles";
import ThisWeekPlan, { toIsoDate } from "./dashboard/ThisWeekPlan";
import TodayHero from "./dashboard/TodayHero";
import { TodayPlanCard } from "./dashboard/TodayPlanCard";

/**
 * Home page: today's cockpit. Reads top-down as 状態 (verdict hero, snapshot
 * tiles) → 行動 (this week's plan + next actions) → 進捗 (race countdown,
 * recent runs). Every block is fed by an existing read-only endpoint; the
 * deep-dive pages (trends / weekly reviews / goal) stay one link away.
 */
export default function Dashboard() {
  // Each block is fed by an independent query so one slow endpoint never blocks
  // the whole cockpit; every card swaps its skeleton for content as its own
  // data lands.
  const recoveryStatusQuery = useRecoveryStatus();
  const reviewsQuery = useWeeklyReviews(1);
  const loadQuery = useTrainingLoad();
  const recoveryQuery = useRecoveryTrend();
  const flagsQuery = useFormAnomalyFlags();
  const activitiesQuery = useActivities();
  // Supplementary blocks (baseline / readiness / goal) fail silently: their
  // sections degrade instead of taking the home page down, so their errors are
  // never folded into the page-level banner.
  const baselineQuery = useWellnessBaselineDeviation();
  const readinessQuery = useRaceReadiness();
  const goalQuery = useGoal();

  const recoveryStatus = recoveryStatusQuery.data ?? null;
  const baseline = baselineQuery.data ?? null;
  const reviews = reviewsQuery.data ?? null;
  const load = loadQuery.data ?? null;
  const recovery = recoveryQuery.data ?? null;
  const flags = flagsQuery.data ?? null;
  const readiness = readinessQuery.data ?? null;
  const goal = goalQuery.data ?? null;
  const activities = activitiesQuery.data ?? null;

  // A failure in any core endpoint takes the page down with a banner; the
  // first error encountered wins.
  const error =
    recoveryStatusQuery.error ??
    reviewsQuery.error ??
    loadQuery.error ??
    recoveryQuery.error ??
    flagsQuery.error ??
    activitiesQuery.error ??
    null;

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

  const latestReview = reviews?.[0] ?? null;

  return (
    <div className="space-y-6">
      <SectionHeading eyebrow="Home" title="今日のコックピット" />

      <div className="stagger-in space-y-6">
        {/* ① 状態: 今日の判定 */}
        {recoveryStatus == null ? (
          <CardSkeleton label="今日の判定" />
        ) : (
          <TodayHero status={recoveryStatus} baseline={baseline} />
        )}

        {/* ① 状態: スナップショットタイル */}
        {load == null && recovery == null && flags == null ? (
          <CardSkeleton label="状態スナップショット" />
        ) : (
          <SnapshotTiles load={load} recovery={recovery} flags={flags} />
        )}

        {/* ② 行動: 今日の予定 vs 実績 */}
        <TodayPlanCard date={toIsoDate(new Date())} />

        {/* ② 行動: 今週のプラン + 次の行動 */}
        {reviews == null ? (
          <CardSkeleton label="今週のプランと次の行動" />
        ) : (
          <ThisWeekPlan review={latestReview} />
        )}

        {/* ③ 進捗: レースへの道 */}
        <RaceProgress readiness={readiness} goals={goal?.goals ?? null} />

        {/* ③ 進捗: 最近のラン */}
        {activities == null ? (
          <CardSkeleton label="最近のラン" />
        ) : (
          <RecentRuns activities={activities} />
        )}
      </div>
    </div>
  );
}
