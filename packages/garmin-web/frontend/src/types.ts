export interface ActivitySummary {
  activity_id: number;
  activity_date: string;
  activity_name: string | null;
  total_distance_km: number | null;
  total_time_seconds: number | null;
  avg_pace_seconds_per_km: number | null;
  avg_heart_rate: number | null;
}

// --- Goal page (Issue #282) ---

export interface GoalProfile {
  current_focus: string | null;
  focus_notes: string | null;
  updated_at: string | null;
}

export interface GoalRace {
  goal_id: number;
  race_name: string | null;
  race_date: string | null;
  priority: string | null;
  goal_type: string | null;
  distance_km: number | null;
  target_time_seconds: number | null;
  status: string | null;
  notes: string | null;
}

export interface SeasonRetrospective {
  retro_id: number;
  season_label: string | null;
  period_start: string | null;
  period_end: string | null;
  narrative: string | null;
  key_learnings: string | null;
}

export interface GoalResponse {
  profile: GoalProfile;
  goals: GoalRace[];
  retrospectives: SeasonRetrospective[];
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

export interface Vo2MaxData {
  value: number | null;
  date: string | null;
  [key: string]: unknown;
}

export interface LactateThresholdData {
  heart_rate: number | null;
  speed_mps: number | null;
  date_hr: string | null;
  [key: string]: unknown;
}

export interface ActivityDetailResponse {
  activity: ActivitySummary & Record<string, unknown>;
  splits: SplitRow[];
  form_efficiency: Record<string, unknown> | null;
  hr_zones: HrZoneRow[];
  performance_trends: Record<string, unknown> | null;
  form_evaluations: Record<string, unknown> | null;
  vo2_max: Vo2MaxData | null;
  lactate_threshold: LactateThresholdData | null;
}

export interface TimeSeriesResponse {
  timestamps: number[];
  metrics: Record<string, (number | null)[]>;
}

// --- GPS track (Issue #200) ---

export interface TrackPoint {
  seq_no: number;
  lat: number;
  lon: number;
}

export interface TrackResponse {
  points: TrackPoint[];
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
