export type Granularity = "week" | "month";

export interface VolumeTrendPoint {
  bucket: string;
  distance_km: number;
  duration_seconds: number;
  run_count: number;
}

export interface Vo2maxPoint {
  date: string;
  value: number | null;
}

export interface LactateThresholdPoint {
  date: string;
  heart_rate: number | null;
  speed_mps: number | null;
}

export interface PhysiologyTrend {
  vo2max: Vo2maxPoint[];
  lactate_threshold: LactateThresholdPoint[];
}

export interface FormTrendPoint {
  date: string;
  overall_score: number | null;
  gct_delta: number | null;
  vo_delta: number | null;
  vr_delta: number | null;
}

export interface EfficiencyTrendPoint {
  date: string;
  aerobic_efficiency: string | null;
  primary_zone: string | null;
  zone1_percentage: number | null;
  zone2_percentage: number | null;
  zone3_percentage: number | null;
  zone4_percentage: number | null;
  zone5_percentage: number | null;
}

export interface HeatAdjustedPoint {
  date: string;
  temp_c: number | null;
  raw_hr: number | null;
  heat_cost: number | null;
  neutral_hr: number | null;
}

export interface HeatAdjustedCoefficients {
  beta_heat: number;
  ref_temp_c: number;
  n: number;
}

export interface HeatAdjustedTrend {
  status: string;
  coefficients: HeatAdjustedCoefficients | null;
  neutral_hr_slope: number | null;
  points: HeatAdjustedPoint[];
}

export interface CriticalSpeedPoint {
  quarter: string;
  cs_mps: number;
  cs_pace_sec_per_km: number;
  r_squared: number;
  n: number;
  label: string;
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${url}: ${response.status}`);
  }
  return (await response.json()) as T;
}

export function fetchVolumeTrend(
  granularity: Granularity,
): Promise<VolumeTrendPoint[]> {
  return fetchJson(`/api/trends/volume?granularity=${granularity}`);
}

export function fetchPhysiologyTrend(): Promise<PhysiologyTrend> {
  return fetchJson("/api/trends/physiology");
}

export function fetchFormTrend(): Promise<FormTrendPoint[]> {
  return fetchJson("/api/trends/form");
}

export function fetchEfficiencyTrend(): Promise<EfficiencyTrendPoint[]> {
  return fetchJson("/api/trends/efficiency");
}

export function fetchHeatAdjustedTrend(
  days: number,
): Promise<HeatAdjustedTrend> {
  return fetchJson(`/api/trends/heat-adjusted?days=${days}`);
}

export function fetchCriticalSpeed(): Promise<CriticalSpeedPoint[]> {
  return fetchJson("/api/trends/critical-speed");
}
