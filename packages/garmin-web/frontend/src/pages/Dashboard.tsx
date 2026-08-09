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
import QueryBoundary, { type QueryLike } from "../components/QueryBoundary";
import SectionHeading from "../components/SectionHeading";
import { usePageTitle } from "../hooks/usePageTitle";
import type {
  AcwrTrend,
  FormAnomalyFlagsResponse,
  RecoveryTrend,
} from "../types";
import RaceProgress from "./dashboard/RaceProgress";
import RecentRuns from "./dashboard/RecentRuns";
import SnapshotTiles from "./dashboard/SnapshotTiles";
import ThisWeekPlan from "./dashboard/ThisWeekPlan";
import TodayHero from "./dashboard/TodayHero";

/** The three endpoints behind the snapshot row, as one card's worth of data. */
interface SnapshotData {
  load: AcwrTrend | null;
  recovery: RecoveryTrend | null;
  flags: FormAnomalyFlagsResponse | null;
}

/**
 * Home page: today's cockpit. Reads top-down as 状態 (verdict hero, snapshot
 * tiles) → 行動 (this week's plan + next actions) → 進捗 (race countdown,
 * recent runs). Every block is fed by an existing read-only endpoint; the
 * deep-dive pages (condition / performance / weekly reviews / goal) stay one
 * link away.
 *
 * Failures are per card, not per page (#895): each block sits behind its own
 * `QueryBoundary`, so a single broken endpoint degrades into a retryable
 * in-card alert instead of replacing the whole cockpit with one banner.
 */
export default function Dashboard() {
  usePageTitle("ホーム");
  // Each block is fed by an independent query so one slow endpoint never blocks
  // the whole cockpit; every card swaps its skeleton for content as its own
  // data lands.
  const recoveryStatusQuery = useRecoveryStatus();
  const reviewsQuery = useWeeklyReviews(1);
  const loadQuery = useTrainingLoad();
  const recoveryQuery = useRecoveryTrend();
  const flagsQuery = useFormAnomalyFlags();
  const activitiesQuery = useActivities();
  // Supplementary blocks (baseline / readiness / goal) fail silently: they
  // enrich a card rather than being one, so they degrade away instead of
  // showing an alert where the reader expects content.
  const baselineQuery = useWellnessBaselineDeviation();
  const readinessQuery = useRaceReadiness();
  const goalQuery = useGoal();

  // The snapshot row reads as one card, so it gets one boundary: it shows the
  // first tile failure (retrying all three) and otherwise renders as soon as
  // any tile's data lands, letting the rest fill in behind their placeholders.
  const snapshotQuery: QueryLike<SnapshotData> = {
    data:
      loadQuery.data === undefined &&
      recoveryQuery.data === undefined &&
      flagsQuery.data === undefined
        ? undefined
        : {
            load: loadQuery.data ?? null,
            recovery: recoveryQuery.data ?? null,
            flags: flagsQuery.data ?? null,
          },
    error: loadQuery.error ?? recoveryQuery.error ?? flagsQuery.error,
    refetch: () => {
      loadQuery.refetch();
      recoveryQuery.refetch();
      flagsQuery.refetch();
    },
  };

  return (
    <div className="space-y-6">
      <SectionHeading eyebrow="Home" title="今日のコックピット" />

      <div className="stagger-in space-y-6">
        {/* ① 状態: 今日の判定 */}
        <QueryBoundary label="今日の判定" query={recoveryStatusQuery}>
          {(status) => (
            <TodayHero status={status} baseline={baselineQuery.data ?? null} />
          )}
        </QueryBoundary>

        {/* ① 状態: スナップショットタイル */}
        <QueryBoundary label="状態スナップショット" query={snapshotQuery}>
          {({ load, recovery, flags }) => (
            <SnapshotTiles load={load} recovery={recovery} flags={flags} />
          )}
        </QueryBoundary>

        {/* ② 行動: 今週のプラン + 次の行動 */}
        <QueryBoundary label="今週のプランと次の行動" query={reviewsQuery}>
          {(reviews) => <ThisWeekPlan review={reviews[0] ?? null} />}
        </QueryBoundary>

        {/* ③ 進捗: レースへの道 (supplementary — degrades away on failure) */}
        <RaceProgress
          readiness={readinessQuery.data ?? null}
          goals={goalQuery.data?.goals ?? null}
        />

        {/* ③ 進捗: 最近のラン */}
        <QueryBoundary label="最近のラン" query={activitiesQuery}>
          {(activities) => <RecentRuns activities={activities} />}
        </QueryBoundary>
      </div>
    </div>
  );
}
