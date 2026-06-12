import type {
  ActivityDetailResponse,
  ActivitySummary,
  SectionsResponse,
  TimeSeriesResponse,
} from "../types";

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

export async function fetchSections(
  activityId: string | number,
): Promise<SectionsResponse> {
  const response = await fetch(`/api/activities/${activityId}/sections`);
  if (!response.ok) {
    throw new Error(`Failed to fetch sections: ${response.status}`);
  }
  return (await response.json()) as SectionsResponse;
}
