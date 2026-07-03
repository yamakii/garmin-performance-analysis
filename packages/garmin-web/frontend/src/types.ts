export interface ActivitySummary {
  activity_id: number;
  activity_date: string;
  activity_name: string | null;
  total_distance_km: number | null;
  total_time_seconds: number | null;
  avg_pace_seconds_per_km: number | null;
  avg_heart_rate: number | null;
}

// --- Today's planned workout (Issue #721) ---
// `/api/planned-workouts/today` returns the planned session for a day, or null
// on a rest day. Pace targets are sec/km; HR targets are bpm.
export interface PlannedWorkoutToday {
  workout_id: string;
  workout_type: string | null;
  description_ja: string | null;
  target_distance_km: number | null;
  target_pace_low: number | null;
  target_pace_high: number | null;
  target_hr_low: number | null;
  target_hr_high: number | null;
  actual_activity_id: number | null;
  adherence_score: number | null;
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

// --- Race readiness (Issue #362) ---

export interface RaceReadinessPredictedTimes {
  race_5k?: number;
  race_10k?: number;
  half?: number;
  full?: number;
  [key: string]: number | undefined;
}

export interface RaceReadinessGoal {
  race_name: string | null;
  race_date: string | null;
  distance_km: number | null;
  target_time_seconds: number | null;
}

export interface RaceReadinessProgress {
  predicted_time_seconds: number;
  gap_seconds: number;
  pace_gap_sec_per_km: number;
  weeks_remaining: number | null;
  status: "ahead" | "on_track" | "behind";
}

export interface RaceReadiness {
  current_vdot: number | null;
  predicted_times: RaceReadinessPredictedTimes;
  goal: RaceReadinessGoal | null;
  progress: RaceReadinessProgress | null;
}

// --- Training load / ACWR (Issue #363) ---

export type AcwrStatus =
  | "undertraining"
  | "optimal"
  | "caution"
  | "high_risk"
  | "insufficient_data";

export interface AcwrCurrent {
  end_date: string | null;
  acute_load_7d: number;
  chronic_load_28d_weekly: number;
  acwr: number | null;
  status: AcwrStatus;
  load_metric: string;
}

export interface AcwrWeek {
  week_start: string;
  load_km: number;
  acwr: number | null;
  status: AcwrStatus;
}

export interface AcwrTrend {
  current: AcwrCurrent;
  trend: {
    weeks: AcwrWeek[];
    load_metric: string;
  };
}

// --- Durability (cardiac decoupling) (Issue #364) ---

export type DurabilityDirection =
  | "improving"
  | "worsening"
  | "stable"
  | "insufficient_data";

export interface DurabilityActivity {
  activity_id: number;
  activity_date: string;
  distance_km: number;
  decoupling_pct: number;
  pace_fade_pct: number;
  // Second-half form fades (#368): nullable on devices lacking the metric.
  gct_fade_pct: number | null;
  vo_fade_pct: number | null;
  vr_fade_pct: number | null;
}

export interface DurabilityTrend {
  activities: DurabilityActivity[];
  trend: {
    decoupling_slope_per_day: number;
    data_points: number;
    direction: DurabilityDirection;
    // GCT-fade trend (#368): slope is null when <2 runs have form data.
    gct_fade_slope_per_day: number | null;
    form_direction: DurabilityDirection;
  };
}

// --- Recovery / body composition (Issue #502) ---

export type RhrTrend = "improving" | "stable" | "fatigued" | null;

export type HrvStatus = "low" | "balanced" | "high" | null;

export type RecoveryRecommendation =
  | "rest"
  | "easy"
  | "moderate"
  | "quality"
  | "unknown";

export interface RecoverySeriesPoint {
  date: string;
  resting_hr: number | null;
  hrv_overnight_ms: number | null;
}

export interface RecoveryTrend {
  weeks: number;
  rhr: {
    median_7d: number | null;
    median_30d: number | null;
    rhr_trend: RhrTrend;
  };
  hrv: {
    latest_ms: number | null;
    status: HrvStatus;
    hrv_below_baseline_days: number;
    under_recovery: boolean;
  };
  series: RecoverySeriesPoint[];
}

export interface RecoveryStatus {
  date: string | null;
  recommendation: RecoveryRecommendation;
  score: number | null;
  reasons: string[];
  training_readiness: number | null;
  body_battery_high: number | null;
  sleep_score: number | null;
}

/** One metric's personal baseline band and today's position within it (#555). */
export interface MetricBaseline {
  metric: "hrv" | "readiness" | "rhr";
  mean: number | null;
  std: number | null;
  today: number | null;
  z: number | null;
  flag: "low" | "high" | "within" | "insufficient";
  adverse: boolean;
  n: number;
}

/** Personal-baseline deviation for HRV / readiness / RHR on a target day (#555). */
export interface WellnessBaselineDeviation {
  date: string | null;
  hrv: MetricBaseline;
  readiness: MetricBaseline;
  rhr: MetricBaseline;
  overall_flag: boolean;
}

// --- Form anomaly "今週の注意点" flags (Issue #636) ---

export interface FormAnomalyFlag {
  activity_id: number;
  activity_date: string;
  anomalies_detected: number;
  severity_high: number;
  top_recommendation: string | null;
}

export interface FormAnomalyFlagsResponse {
  weeks: number;
  scanned: number;
  limited: boolean;
  flags: FormAnomalyFlag[];
}

export interface BodyCompositionSeriesPoint {
  date: string;
  weight_kg: number | null;
  fat_mass: number | null;
  lean_mass: number | null;
}

export interface BodyCompositionChange {
  delta_weight: number | null;
  delta_fat: number | null;
  delta_lean: number | null;
  lean_loss_ratio: number | null;
  muscle_loss_warning: boolean;
}

export interface BodyCompositionTrend {
  weeks: number;
  series: BodyCompositionSeriesPoint[];
  change: BodyCompositionChange;
  lean_pwr: number | null;
}

// --- Weekly reviews (Issue #283) ---

export interface WeeklyReviewVerdict {
  date?: string;
  session?: string;
  rating?: string; // "✅" | "🟡" | "🔴"
  comment?: string;
  [key: string]: unknown;
}

export interface WeeklyReviewPeriodization {
  weeks_to_a_race?: number | null;
  a_race?: string | null;
  weeks_to_b_race?: number | null;
  b_race?: string | null;
  expected_phase?: string | null;
  garmin_phase?: string | null;
  gap?: string | null;
  [key: string]: unknown;
}

export interface WeeklyReviewThisWeek {
  volume_km?: number | null;
  run_count?: number | null;
  intensity_distribution?: Record<string, unknown>;
  hr_discipline?: string | null;
  highlights?: string[];
  [key: string]: unknown;
}

export interface WeeklyReviewPlanItem {
  date?: string;
  title?: string;
  type?: string;
  [key: string]: unknown;
}

export interface WeeklyReviewWeightTracking {
  recent_median_kg?: number | null;
  bmi?: number | null;
  trend?: string | null;
  week_classification?: string | null;
  flag?: string | null;
  target_first?: string | null;
  [key: string]: unknown;
}

export interface WeeklyReviewData {
  plan_week_start?: string | null;
  actuals_week_start?: string | null;
  this_week?: WeeklyReviewThisWeek;
  garmin_next_week?: WeeklyReviewPlanItem[];
  periodization?: WeeklyReviewPeriodization;
  verdict?: WeeklyReviewVerdict[];
  goal_alignment?: string | null;
  recommendations?: string[];
  overall?: string | null;
  weight_tracking?: WeeklyReviewWeightTracking;
  recovery?: unknown;
  continuity_note?: string | null;
  weekly_ramp?: unknown;
  [key: string]: unknown;
}

export interface WeeklyReview {
  review_id: number;
  user_id: string;
  week_start_date: string;
  week_end_date: string;
  review_date: string | null;
  review_data: WeeklyReviewData | null;
  created_at: string | null;
  agent_name: string | null;
  agent_version: string | null;
}

export type WeeklyReviewListResponse = WeeklyReview[];

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

/** One saved analysis batch (a run = rows sharing created_at), from #720. */
export interface SectionVersion {
  created_at: string;
  section_types: string[];
}

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

// --- Weight ↔ running-economy coupling (Issue #556) ---
// Faithful to the backend reader output (#554): ``model`` is the
// dataclasses.asdict of WeightEconomyModel, whose covariates are nested
// (``weight: {coef, p_value, vif}``), so the TS type mirrors that shape and
// avoids a mapping layer.

export interface WeightEconomySeriesPoint {
  activity_id: number;
  run_date: string;
  weight_kg: number;
  ef: number;
  weight_gap_days: number;
}

export interface WeightEconomyCovariate {
  coef: number;
  p_value: number;
  vif: number;
}

export interface WeightEconomyModel {
  n: number;
  r_squared: number;
  weight: WeightEconomyCovariate;
  days: WeightEconomyCovariate;
  fitness: WeightEconomyCovariate | null;
  delta_ef_per_5kg_loss: number;
  collinearity_flag: boolean;
  note: string;
}

export interface WeightEconomyCoupling {
  weeks: number;
  n_matched: number;
  weight_spread_kg: number;
  model: WeightEconomyModel | null;
  series: WeightEconomySeriesPoint[];
  note: string;
}
