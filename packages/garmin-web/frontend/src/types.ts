export interface ActivitySummary {
  activity_id: number;
  activity_date: string;
  activity_name: string | null;
  total_distance_km: number | null;
  total_time_seconds: number | null;
  avg_pace_seconds_per_km: number | null;
  avg_heart_rate: number | null;
}

// --- Activity detail (Issue #199) ---

export interface SplitRow {
  activity_id: number;
  split_index: number;
  distance: number | null;
  duration_seconds: number | null;
  pace_seconds_per_km: number | null;
  heart_rate: number | null;
  cadence: number | null;
  power: number | null;
  [key: string]: unknown;
}

export interface HrZoneRow {
  activity_id: number;
  zone_number: number;
  zone_low_boundary: number | null;
  zone_high_boundary: number | null;
  time_in_zone_seconds: number | null;
  zone_percentage: number | null;
}

export interface ActivityDetailResponse {
  activity: ActivitySummary & Record<string, unknown>;
  splits: SplitRow[];
  form_efficiency: Record<string, unknown> | null;
  hr_zones: HrZoneRow[];
  performance_trends: Record<string, unknown> | null;
  form_evaluations: Record<string, unknown> | null;
}

export interface TimeSeriesResponse {
  timestamps: number[];
  metrics: Record<string, (number | null)[]>;
}

export interface SectionResult {
  data: Record<string, unknown> | null;
  parse_error: boolean;
  raw: string | null;
}

export type SectionsResponse = Record<string, SectionResult>;

// --- Section analysis data types (from Spike #198) ---

export interface SectionMetadata {
  activity_id: string; // NOTE: string inside JSON (DB column is BIGINT)
  date: string; // "YYYY-MM-DD"
  analyst: string; // e.g. "summary-section-analyst"
  version: string; // currently always "1.0"
  timestamp: string; // ISO 8601
}

/** Markdown-style Japanese analysis text */
export type AnalysisText = string;

export interface SplitSectionData {
  metadata?: SectionMetadata;
  highlights?: AnalysisText;
  analyses?: Record<string, AnalysisText>; // keys "split_1".."split_N" (distance-dependent)
  [key: string]: unknown;
}

export interface PhaseSectionData {
  metadata?: SectionMetadata;
  warmup_evaluation?: AnalysisText;
  run_evaluation?: AnalysisText;
  cooldown_evaluation?: AnalysisText;
  evaluation_criteria?: AnalysisText;
  recovery_evaluation?: AnalysisText; // interval training only
  [key: string]: unknown;
}

export interface EfficiencySectionData {
  metadata?: SectionMetadata;
  efficiency?: AnalysisText;
  evaluation?: AnalysisText;
  form_trend?: AnalysisText;
  [key: string]: unknown;
}

export interface EnvironmentSectionData {
  metadata?: SectionMetadata;
  environmental?: AnalysisText;
  [key: string]: unknown;
}

export interface SummarySectionData {
  metadata?: SectionMetadata;
  star_rating?: string; // "★★★★☆ 4.3/5.0" format
  summary?: AnalysisText;
  key_strengths?: string[];
  improvement_areas?: string[];
  recommendations?: AnalysisText;
  // Fields added after 2026-02 without a version bump — render by key presence
  integrated_score?: number;
  next_action?: string;
  next_run_target?: Record<string, unknown>;
  plan_achievement?: Record<string, unknown>;
  [key: string]: unknown;
}
