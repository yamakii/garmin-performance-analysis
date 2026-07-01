import { useEffect, useState } from "react";
import { fetchActivities, fetchGoal, fetchRaceReadiness, fetchWeeklyReviews } from "../api/client";
import {
  fetchFormAnomalyFlags,
  fetchRecoveryStatus,
  fetchRecoveryTrend,
  fetchWellnessBaselineDeviation,
} from "../api/recovery";
import { fetchTrainingLoad } from "../api/training_load";
import CardSkeleton from "../components/CardSkeleton";
import SectionHeading from "../components/SectionHeading";
import type {
  AcwrTrend,
  ActivitySummary,
  FormAnomalyFlagsResponse,
  GoalResponse,
  RaceReadiness,
  RecoveryStatus,
  RecoveryTrend,
  WeeklyReview,
  WellnessBaselineDeviation,
} from "../types";
import RaceProgress from "./dashboard/RaceProgress";
import RecentRuns from "./dashboard/RecentRuns";
import SnapshotTiles from "./dashboard/SnapshotTiles";
import ThisWeekPlan from "./dashboard/ThisWeekPlan";
import TodayHero from "./dashboard/TodayHero";

/**
 * Home page: today's cockpit. Reads top-down as 状態 (verdict hero, snapshot
 * tiles) → 行動 (this week's plan + next actions) → 進捗 (race countdown,
 * recent runs). Every block is fed by an existing read-only endpoint; the
 * deep-dive pages (trends / weekly reviews / goal) stay one link away.
 */
export default function Dashboard() {
  const [recoveryStatus, setRecoveryStatus] = useState<RecoveryStatus | null>(
    null,
  );
  const [baseline, setBaseline] = useState<WellnessBaselineDeviation | null>(
    null,
  );
  const [reviews, setReviews] = useState<WeeklyReview[] | null>(null);
  const [load, setLoad] = useState<AcwrTrend | null>(null);
  const [recovery, setRecovery] = useState<RecoveryTrend | null>(null);
  const [flags, setFlags] = useState<FormAnomalyFlagsResponse | null>(null);
  const [readiness, setReadiness] = useState<RaceReadiness | null>(null);
  const [goal, setGoal] = useState<GoalResponse | null>(null);
  const [activities, setActivities] = useState<ActivitySummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    // Wire each fetch independently (TrendsDashboard pattern) so one slow
    // endpoint never blocks the whole cockpit.
    const wire = <T,>(promise: Promise<T>, set: (value: T) => void): void => {
      promise
        .then((value) => {
          if (!cancelled) set(value);
        })
        .catch((err: unknown) => {
          if (!cancelled)
            setError(err instanceof Error ? err.message : String(err));
        });
    };
    // Supplementary blocks (readiness / goal / baseline) fail silently: their
    // sections degrade instead of taking the home page down.
    const wireOptional = <T,>(
      promise: Promise<T>,
      set: (value: T) => void,
    ): void => {
      promise
        .then((value) => {
          if (!cancelled) set(value);
        })
        .catch(() => {
          /* non-fatal */
        });
    };
    wire(fetchRecoveryStatus(), setRecoveryStatus);
    wire(fetchWeeklyReviews(1), setReviews);
    wire(fetchTrainingLoad(), setLoad);
    wire(fetchRecoveryTrend(), setRecovery);
    wire(fetchFormAnomalyFlags(), setFlags);
    wire(fetchActivities(), setActivities);
    wireOptional(fetchWellnessBaselineDeviation(), setBaseline);
    wireOptional(fetchRaceReadiness(), setReadiness);
    wireOptional(fetchGoal(), setGoal);
    return () => {
      cancelled = true;
    };
  }, []);

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
