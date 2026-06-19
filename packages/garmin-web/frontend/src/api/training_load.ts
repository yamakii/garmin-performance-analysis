import type { AcwrTrend } from "../types";

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${url}: ${response.status}`);
  }
  return (await response.json()) as T;
}

export function fetchTrainingLoad(lookbackWeeks = 12): Promise<AcwrTrend> {
  return fetchJson(`/api/training-load?lookback_weeks=${lookbackWeeks}`);
}
