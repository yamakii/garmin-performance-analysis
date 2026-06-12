import type { ActivitySummary } from "../types";

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
