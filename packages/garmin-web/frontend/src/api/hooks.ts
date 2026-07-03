import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import {
  fetchActivities,
  fetchActivityDetail,
  fetchGoal,
  fetchRaceReadiness,
  fetchSections,
  fetchSectionVersions,
  fetchTimeSeries,
  fetchTrack,
  fetchWeeklyReviews,
  fetchWeeklyReviewVersions,
} from "./client";
import {
  fetchBodyCompositionTrend,
  fetchFormAnomalyFlags,
  fetchRecoveryStatus,
  fetchRecoveryTrend,
  fetchWeightEconomyCoupling,
  fetchWellnessBaselineDeviation,
} from "./recovery";
import { fetchDurabilityTrend } from "./durability";
import { fetchTrainingLoad } from "./training_load";
import {
  fetchCriticalSpeed,
  fetchEfficiencyTrend,
  fetchFormTrend,
  fetchHeatAdjustedTrend,
  fetchObjectiveFitnessTrend,
  fetchPhysiologyTrend,
  fetchTrendNarration,
  fetchTrendNarrationVersions,
  fetchVolumeTrend,
  type CriticalSpeedPoint,
  type EfficiencyTrendPoint,
  type FormTrendPoint,
  type Granularity,
  type HeatAdjustedTrend,
  type ObjectiveFitnessTrend,
  type PhysiologyTrend,
  type TrendNarration,
  type VolumeTrendPoint,
} from "./trends";
import type {
  AcwrTrend,
  ActivityDetailResponse,
  ActivitySummary,
  BodyCompositionTrend,
  DurabilityTrend,
  FormAnomalyFlagsResponse,
  GoalResponse,
  RaceReadiness,
  RecoveryStatus,
  RecoveryTrend,
  SectionsResponse,
  SectionVersion,
  TimeSeriesResponse,
  TrackResponse,
  WeeklyReview,
  WeightEconomyCoupling,
  WellnessBaselineDeviation,
} from "../types";

/**
 * TanStack Query hooks wrapping the plain `fetch*` API functions.
 *
 * Each hook keys its cache by the request's identifying parameters so the same
 * data is fetched once and shared across every component that reads it, and a
 * navigation round-trip re-uses the cached result instead of refetching. The
 * query keys follow a stable `[domain, ...params]` convention.
 */

// --- Activity detail ------------------------------------------------------

export function useActivityDetail(
  id: string | undefined,
): UseQueryResult<ActivityDetailResponse, Error> {
  return useQuery({
    queryKey: ["activity", id],
    queryFn: () => fetchActivityDetail(id as string),
    enabled: id != null,
  });
}

export function useSections(
  id: string | undefined,
  runId?: number,
): UseQueryResult<SectionsResponse, Error> {
  return useQuery({
    queryKey: ["sections", id, runId ?? null],
    queryFn: () => fetchSections(id as string, runId),
    enabled: id != null,
  });
}

export function useSectionVersions(
  id: string | undefined,
): UseQueryResult<SectionVersion[], Error> {
  return useQuery({
    queryKey: ["sectionVersions", id],
    queryFn: () => fetchSectionVersions(id as string),
    enabled: id != null,
  });
}

export function useTimeSeries(
  id: string | undefined,
  metrics: string[],
): UseQueryResult<TimeSeriesResponse, Error> {
  return useQuery({
    queryKey: ["timeSeries", id, metrics],
    queryFn: () => fetchTimeSeries(id as string, metrics),
    enabled: id != null && metrics.length > 0,
  });
}

export function useTrack(
  id: string | undefined,
): UseQueryResult<TrackResponse, Error> {
  return useQuery({
    queryKey: ["track", id],
    queryFn: () => fetchTrack(id as string),
    enabled: id != null,
  });
}

// --- Activity list --------------------------------------------------------

export function useActivities(): UseQueryResult<ActivitySummary[], Error> {
  return useQuery({
    queryKey: ["activities"],
    queryFn: () => fetchActivities(),
  });
}

// --- Goal / race readiness ------------------------------------------------

export function useGoal(): UseQueryResult<GoalResponse, Error> {
  return useQuery({ queryKey: ["goal"], queryFn: () => fetchGoal() });
}

export function useRaceReadiness(): UseQueryResult<RaceReadiness, Error> {
  return useQuery({
    queryKey: ["raceReadiness"],
    queryFn: () => fetchRaceReadiness(),
  });
}

// --- Weekly reviews -------------------------------------------------------

export function useWeeklyReviews(
  limit = 12,
): UseQueryResult<WeeklyReview[], Error> {
  return useQuery({
    queryKey: ["weeklyReviews", limit],
    queryFn: () => fetchWeeklyReviews(limit),
  });
}

export function useWeeklyReviewVersions(
  weekStart: string | undefined,
): UseQueryResult<WeeklyReview[], Error> {
  return useQuery({
    queryKey: ["weeklyReviewVersions", weekStart],
    queryFn: () => fetchWeeklyReviewVersions(weekStart as string),
    enabled: weekStart != null,
  });
}

// --- Trends ---------------------------------------------------------------

export function useVolumeTrend(
  granularity: Granularity,
): UseQueryResult<VolumeTrendPoint[], Error> {
  return useQuery({
    queryKey: ["volumeTrend", granularity],
    queryFn: () => fetchVolumeTrend(granularity),
  });
}

export function usePhysiologyTrend(): UseQueryResult<PhysiologyTrend, Error> {
  return useQuery({
    queryKey: ["physiologyTrend"],
    queryFn: () => fetchPhysiologyTrend(),
  });
}

export function useTrendNarration(
  granularity: Granularity,
): UseQueryResult<TrendNarration, Error> {
  return useQuery({
    queryKey: ["trendNarration", granularity],
    queryFn: () => fetchTrendNarration(granularity),
  });
}

export function useTrendNarrationVersions(
  granularity: Granularity,
  periodStart: string | undefined,
): UseQueryResult<TrendNarration[], Error> {
  return useQuery({
    queryKey: ["trendNarrationVersions", granularity, periodStart],
    queryFn: () => fetchTrendNarrationVersions(granularity, periodStart as string),
    enabled: periodStart != null,
  });
}

export function useFormTrend(): UseQueryResult<FormTrendPoint[], Error> {
  return useQuery({
    queryKey: ["formTrend"],
    queryFn: () => fetchFormTrend(),
  });
}

export function useEfficiencyTrend(): UseQueryResult<
  EfficiencyTrendPoint[],
  Error
> {
  return useQuery({
    queryKey: ["efficiencyTrend"],
    queryFn: () => fetchEfficiencyTrend(),
  });
}

export function useHeatAdjustedTrend(
  days: number,
): UseQueryResult<HeatAdjustedTrend, Error> {
  return useQuery({
    queryKey: ["heatAdjustedTrend", days],
    queryFn: () => fetchHeatAdjustedTrend(days),
  });
}

export function useCriticalSpeed(): UseQueryResult<CriticalSpeedPoint[], Error> {
  return useQuery({
    queryKey: ["criticalSpeed"],
    queryFn: () => fetchCriticalSpeed(),
  });
}

export function useObjectiveFitnessTrend(): UseQueryResult<
  ObjectiveFitnessTrend,
  Error
> {
  return useQuery({
    queryKey: ["objectiveFitnessTrend"],
    queryFn: () => fetchObjectiveFitnessTrend(),
  });
}

export function useTrainingLoad(
  lookbackWeeks = 12,
): UseQueryResult<AcwrTrend, Error> {
  return useQuery({
    queryKey: ["trainingLoad", lookbackWeeks],
    queryFn: () => fetchTrainingLoad(lookbackWeeks),
  });
}

export function useDurabilityTrend(
  lookbackDays = 180,
): UseQueryResult<DurabilityTrend, Error> {
  return useQuery({
    queryKey: ["durabilityTrend", lookbackDays],
    queryFn: () => fetchDurabilityTrend(lookbackDays),
  });
}

// --- Recovery / wellness --------------------------------------------------

export function useRecoveryTrend(
  weeks = 8,
): UseQueryResult<RecoveryTrend, Error> {
  return useQuery({
    queryKey: ["recoveryTrend", weeks],
    queryFn: () => fetchRecoveryTrend(weeks),
  });
}

export function useRecoveryStatus(): UseQueryResult<RecoveryStatus, Error> {
  return useQuery({
    queryKey: ["recoveryStatus"],
    queryFn: () => fetchRecoveryStatus(),
  });
}

export function useBodyCompositionTrend(
  weeks = 12,
): UseQueryResult<BodyCompositionTrend, Error> {
  return useQuery({
    queryKey: ["bodyCompositionTrend", weeks],
    queryFn: () => fetchBodyCompositionTrend(weeks),
  });
}

export function useWeightEconomyCoupling(
  weeks = 52,
): UseQueryResult<WeightEconomyCoupling, Error> {
  return useQuery({
    queryKey: ["weightEconomyCoupling", weeks],
    queryFn: () => fetchWeightEconomyCoupling(weeks),
  });
}

export function useWellnessBaselineDeviation(): UseQueryResult<
  WellnessBaselineDeviation,
  Error
> {
  return useQuery({
    queryKey: ["wellnessBaselineDeviation"],
    queryFn: () => fetchWellnessBaselineDeviation(),
  });
}

export function useFormAnomalyFlags(
  weeks = 2,
): UseQueryResult<FormAnomalyFlagsResponse, Error> {
  return useQuery({
    queryKey: ["formAnomalyFlags", weeks],
    queryFn: () => fetchFormAnomalyFlags(weeks),
  });
}
