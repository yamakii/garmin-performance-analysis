import type {
  BodyCompositionTrend,
  RecoveryStatus,
  RecoveryTrend,
} from "../types";

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${url}: ${response.status}`);
  }
  return (await response.json()) as T;
}

/** RHR / HRV recovery trend over the trailing N weeks (#499). */
export function fetchRecoveryTrend(weeks = 8): Promise<RecoveryTrend> {
  return fetchJson(`/api/recovery-trend?weeks=${weeks}`);
}

/** Latest-day go/no-go recovery status (#500). */
export function fetchRecoveryStatus(): Promise<RecoveryStatus> {
  return fetchJson("/api/recovery-status");
}

/** Body-composition trend over the trailing N weeks (#501). */
export function fetchBodyCompositionTrend(
  weeks = 12,
): Promise<BodyCompositionTrend> {
  return fetchJson(`/api/body-composition-trend?weeks=${weeks}`);
}
