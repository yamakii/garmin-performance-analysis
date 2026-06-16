import type {
  ActivityDetailResponse,
  ActivitySummary,
  GoalResponse,
  SectionsResponse,
  TimeSeriesResponse,
  TrackResponse,
  WeeklyReview,
} from "../types";

export async function fetchGoal(): Promise<GoalResponse> {
  const response = await fetch("/api/goal");
  if (!response.ok) {
    throw new Error(`Failed to fetch goal: ${response.status}`);
  }
  return (await response.json()) as GoalResponse;
}

export async function fetchWeeklyReviews(limit = 12): Promise<WeeklyReview[]> {
  const response = await fetch(`/api/weekly-reviews?limit=${limit}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch weekly reviews: ${response.status}`);
  }
  return (await response.json()) as WeeklyReview[];
}

export async function fetchWeeklyReview(
  weekStart: string,
): Promise<WeeklyReview> {
  const response = await fetch(`/api/weekly-reviews/${weekStart}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch weekly review: ${response.status}`);
  }
  return (await response.json()) as WeeklyReview;
}

export async function fetchWeeklyReviewVersions(
  weekStart: string,
): Promise<WeeklyReview[]> {
  const response = await fetch(`/api/weekly-reviews/${weekStart}/versions`);
  if (!response.ok) {
    throw new Error(
      `Failed to fetch weekly review versions: ${response.status}`,
    );
  }
  return (await response.json()) as WeeklyReview[];
}

export async function fetchActivities(params?: {
  from?: string;
  to?: string;
}): Promise<ActivitySummary[]> {
  const query = new URLSearchParams();
  if (params?.from) query.set("from", params.from);
  if (params?.to) query.set("to", params.to);
  const qs = query.toString();
  const response = await fetch(`/api/activities${qs ? `?${qs}` : ""}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch activities: ${response.status}`);
  }
  return (await response.json()) as ActivitySummary[];
}

export async function fetchActivityDetail(
  activityId: string | number,
): Promise<ActivityDetailResponse> {
  const response = await fetch(`/api/activities/${activityId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch activity detail: ${response.status}`);
  }
  return (await response.json()) as ActivityDetailResponse;
}

export async function fetchTimeSeries(
  activityId: string | number,
  metrics: string[],
  maxPoints = 500,
): Promise<TimeSeriesResponse> {
  const query = new URLSearchParams({
    metrics: metrics.join(","),
    max_points: String(maxPoints),
  });
  const response = await fetch(
    `/api/activities/${activityId}/time-series?${query.toString()}`,
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch time series: ${response.status}`);
  }
  return (await response.json()) as TimeSeriesResponse;
}

export async function fetchTrack(
  activityId: string | number,
): Promise<TrackResponse> {
  const response = await fetch(`/api/activities/${activityId}/track`);
  if (!response.ok) {
    throw new Error(`Failed to fetch track: ${response.status}`);
  }
  return (await response.json()) as TrackResponse;
}

export async function fetchSections(
  activityId: string | number,
): Promise<SectionsResponse> {
  const response = await fetch(`/api/activities/${activityId}/sections`);
  if (!response.ok) {
    throw new Error(`Failed to fetch sections: ${response.status}`);
  }
  return (await response.json()) as SectionsResponse;
}
