import type {
  BodyCompositionTrend,
  FormAnomalyFlagsResponse,
  RecoveryStatus,
  RecoveryTrend,
  WeightEconomyCoupling,
  WellnessBaselineDeviation,
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

/** Weight ↔ easy-run economy (EF) coupling over the trailing N weeks (#554). */
export function fetchWeightEconomyCoupling(
  weeks = 52,
): Promise<WeightEconomyCoupling> {
  return fetchJson(`/api/weight-economy-coupling?weeks=${weeks}`);
}

/** Personal-baseline deviation for HRV / readiness / RHR on the latest day (#555). */
export function fetchWellnessBaselineDeviation(): Promise<WellnessBaselineDeviation> {
  return fetchJson("/api/wellness-baseline-deviation");
}

/** Form-anomaly "今週の注意点" flags across the trailing N weeks of runs (#636). */
export function fetchFormAnomalyFlags(
  weeks = 2,
): Promise<FormAnomalyFlagsResponse> {
  return fetchJson(`/api/form-anomaly-flags?weeks=${weeks}`);
}
