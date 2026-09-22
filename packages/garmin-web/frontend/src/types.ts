/** The activities-table columns every activity response carries. */
export interface ActivityCore {
  activity_id: number;
  activity_date: string;
  activity_name: string | null;
  total_distance_km: number | null;
  total_time_seconds: number | null;
  avg_pace_seconds_per_km: number | null;
  avg_heart_rate: number | null;
}

/**
 * A list row: the core columns plus the run report's headline and the opening
 * sentence of the coach review, joined in by the list query so the home page
 * can say what the run was without a second request (#1254). A single run is
 * no longer graded (#1247), so there is no star rating here. The detail
 * response uses `ActivityCore` — it reads the activities table only and does
 * not derive these.
 */
export interface ActivitySummary extends ActivityCore {
  /**
   * The plan verdict of the run report headline, e.g. "処方どおり" / "処方なし".
   * Only the newest rows carry it (computing a report per row is too heavy);
   * older rows are null.
   */
  plan_label: string | null;
  /** Adverse signals of the headline, e.g. ["接地時間が長め"]; empty when none. */
  flag_labels: string[];
  /** First sentence of the coach review (the legacy summary as fallback). */
  story_lead: string | null;
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
  /**
   * The fitness `current_vdot` came from: `objective` (performance VDOT from
   * splits, the same curve the prediction history plots) or the optimistic
   * `garmin_vo2max` fallback. Null exactly when `current_vdot` is null.
   */
  vdot_source: "objective" | "garmin_vo2max" | null;
  predicted_times: RaceReadinessPredictedTimes;
  goal: RaceReadinessGoal | null;
  progress: RaceReadinessProgress | null;
}

// --- Race prediction history (Issue #1133) ---

/** One day's fitness and the goal-race time it implies. */
export interface RacePredictionPoint {
  date: string;
  vdot: number;
  predicted_time_seconds: number;
  /** predicted − target: positive means slower than the target. */
  gap_seconds: number;
}

/**
 * The derived prediction series. `source` names the fitness it rests on:
 * `objective` (performance VDOT from splits) or the optimistic
 * `garmin_vo2max` fallback. Both are null when there is nothing to plot.
 */
export interface RacePredictionHistory {
  goal: RaceReadinessGoal | null;
  source: "objective" | "garmin_vo2max" | null;
  series: RacePredictionPoint[];
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
  /** How long the night lasted; the score says how good it was (#1153). */
  sleep_seconds: number | null;
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

/**
 * A Garmin calendar item that contradicts the training block (#980): only
 * conflicts are saved, so the list is the whole story the reader needs.
 */
export interface WeeklyReviewGarminConflict {
  date?: string;
  garmin_title?: string;
  reason?: string;
  [key: string]: unknown;
}

export interface WeeklyReviewData {
  plan_week_start?: string | null;
  actuals_week_start?: string | null;
  this_week?: WeeklyReviewThisWeek;
  garmin_conflicts?: WeeklyReviewGarminConflict[];
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
  activity: ActivityCore & Record<string, unknown>;
  splits: SplitRow[];
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

/**
 * One split whose form metrics moved (`GET /api/activities/{id}/split-anomalies`).
 *
 * `material` counts the anomalies with an identifiable cause and |z| > 3.5 —
 * the ones worth the reader's eye; `metrics` are the short names (`gct` / `vo`
 * / `vr`) of whatever moved.
 */
export interface SplitAnomalyRow {
  split_index: number;
  anomalies: number;
  material: number;
  severity_high: number;
  max_z: number;
  metrics: string[];
}

/** Per-split form-anomaly counts for one activity (#1132). */
export interface SplitAnomaliesResponse {
  activity_id: number;
  total: number;
  material: number;
  splits: SplitAnomalyRow[];
}

/** One saved analysis run (a version); run_id groups its sections (#776). */
export interface SectionVersion {
  run_id: number;
  created_at: string;
  section_types: string[];
}

// --- Deterministic run report (`GET /api/activities/{id}/report`, #1250) ---

/** One axis of the plan card: what was asked, what happened, on plan or not. */
export interface PlanCheckRow {
  /** "intensity" | "volume" | "hr_ceiling" | "rest". */
  axis: string;
  target: string;
  actual: string;
  status: "on_plan" | "off_plan";
  on_plan: boolean;
}

/** The prescribed HR cap and the time actually spent above it. */
export interface HrCeiling {
  bpm: number;
  seconds_over: number;
  pct_over: number;
}

export interface RunPlan {
  /** ✅ / 🟡 / 🔴, as `compute_prescription_verdict` decided it. */
  verdict: string;
  title: string;
  checks: PlanCheckRow[];
  hr_ceiling: HrCeiling | null;
}

/**
 * One metric judged against the athlete's own normal range.
 *
 * `z > 0` is always the *unfavourable* side, whichever way the metric itself
 * reads — which is why `higher_is_worse` (cadence and power efficiency are
 * worse when *low*) is what names the side in prose, not the sign of `z`.
 */
export interface RunSignal {
  family: "form" | "cardio";
  metric: string;
  label_ja: string;
  unit: string;
  today: number | null;
  expected: number | null;
  normal_low: number | null;
  normal_high: number | null;
  z: number | null;
  status: "within" | "edge" | "outside" | "insufficient";
  adverse: boolean;
  streak: number;
  reason: string | null;
  /** Served only by newer reports; derived from `metric` when absent. */
  higher_is_worse?: boolean;
  direction?: string | null;
  n?: number;
}

/** Share of the run spent in one Garmin native HR zone. */
export interface RunZoneShare {
  zone: number;
  pct: number;
}

/**
 * The numbers a scene is allowed to quote.
 *
 * A walk break carries the laps it happened on (`split_list`) and where they
 * were (`km_list`): the break is several short stops, not one slab of road,
 * and the chart draws one band per stop (#1269).
 */
export interface RunMomentFacts {
  split_list?: number[];
  km_list?: number[];
  [key: string]: unknown;
}

/**
 * A turning point of the run: where it happened and what moved (#1249).
 *
 * Where it is drawn and what it is called are two different things (#1268):
 * the positions (`km_from`/`km_to`, `t_from_s`/`t_to_s`) are real cumulative
 * quantities that count every split including fragments, while `label_ja` and
 * `unit` name the scene in the unit the athlete thinks in — kilometres on a
 * steady run, steps ("1本目", "レスト1") on a rep session. `split_from` /
 * `split_to` are the lap numbers behind it, which is how the splits table
 * matches a row to a scene.
 */
export interface RunMoment {
  id: string;
  kind: string;
  unit: "km" | "step";
  label_ja: string;
  step_id: string;
  rep_no: number | null;
  km_from: number;
  km_to: number;
  t_from_s: number;
  t_to_s: number;
  split_from: number;
  split_to: number;
  facts: RunMomentFacts;
}

/**
 * One drawn step of the flow chart: a split of a long step, or a whole short
 * one. The report decides which splits are drawn, so the chart cannot apply a
 * different fragment rule to pace than to heart rate (#1269).
 */
export interface RunFlowSegment {
  split_from: number;
  split_to: number;
  step_id: string;
  start_km: number;
  end_km: number;
  start_s: number;
  end_s: number;
  pace_s_per_km: number | null;
  avg_hr: number | null;
  max_hr: number | null;
}

/** A step of the session: warmup, a rep, a rest, the main set, the cooldown. */
export interface RunFlowStep {
  id: string;
  role: string;
  label_ja: string;
  short_ja: string;
  rep_no: number | null;
  split_from: number;
  split_to: number;
  start_km: number;
  end_km: number;
  start_s: number;
  end_s: number;
  distance_km: number;
  duration_s: number;
  pace_s_per_km: number | null;
  avg_hr: number | null;
  max_hr: number | null;
  is_long: boolean;
}

/**
 * What the flow chart draws, and the axis it is drawn on: kilometres for a
 * steady run, elapsed minutes for a rep session (where a 120 s rest covers
 * 0.18 km and would be invisible on a distance axis).
 */
export interface RunFlowData {
  axis: "distance" | "time";
  total_km: number;
  total_s: number;
  segments: RunFlowSegment[];
  steps: RunFlowStep[];
  fragments: { count: number; distance_km: number };
}

/** A scene that keeps coming back at the same point of the run. */
export interface RunRecurrence {
  kind: string;
  km: number;
  count: number;
  of: number;
  dates: string[];
}

export interface RunPhaseRow {
  phase: string;
  pace_s_per_km: number | null;
  avg_hr: number | null;
}

export interface RunConditions {
  temp_c: number | null;
  humidity_pct: number | null;
  wind_mps: number | null;
  terrain: string | null;
  elevation_gain_m: number | null;
}

/**
 * What the athlete actually does next (#1273).
 *
 * `next_run_target` answers "what should the next run *of this kind* look
 * like"; this answers the calendar's question instead. `source` says how much
 * is known: a written prescription, the block's long-run ladder, or — with no
 * date at all — today's family projected forward (`same_type`).
 */
export interface NextSession {
  date: string | null;
  days_ahead: number | null;
  session_type: string;
  session_label_ja: string;
  title: string | null;
  target_km: number | null;
  target_minutes: number | null;
  hr_low: number | null;
  hr_high: number | null;
  source: "prescription" | "ladder" | "same_type";
}

export interface RunReport {
  activity_id: number;
  activity_date: string;
  intensity_category: string;
  headline: { plan_label: string; flag_count: number; flag_labels: string[] };
  plan: RunPlan | null;
  signals: RunSignal[];
  zones: RunZoneShare[];
  moments: RunMoment[];
  /** Null only when the report was served by a build older than #1268. */
  flow: RunFlowData | null;
  recurrence: RunRecurrence[];
  phases: RunPhaseRow[];
  conditions: RunConditions;
  vs_previous: Record<string, unknown> | null;
  next_run_target: Record<string, unknown> | null;
  /** Null only when the report was served by a build older than #1273. */
  next_session: NextSession | null;
}

// --- The coach's note: the one LLM-written section (#1251) ---

/** A sentence and the report key it is allowed to lean on. */
export interface GroundedPoint {
  text: string;
  evidence: string;
}

export interface RunNoteTimelineItem {
  moment_id: string;
  text: string;
}

export interface RunNoteSignalNote {
  signal: string;
  text: string;
}

export interface RunNote {
  story: string;
  good_points: GroundedPoint[];
  growth_points: GroundedPoint[];
  next_challenge: string;
  timeline: RunNoteTimelineItem[];
  notes: RunNoteSignalNote[];
  question?: string | null;
}

// --- Section analysis data types (from Spike #198) ---

export interface SectionMetadata {
  activity_id: string; // NOTE: string inside JSON (DB column is BIGINT)
  date: string; // "YYYY-MM-DD"
  analyst: string; // e.g. "run-note-analyst"
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

/**
 * Weighted star-rating payload emitted by the section agents (Issue #706):
 * per-axis 0-5 scores, the weight each axis carries, and the weighted total.
 * `weights` / `star_rating` are optional because older saved analyses predate
 * them, and the index signature keeps forward-compatible keys readable.
 */
export interface StarRatingBreakdown {
  axis_scores: Record<string, number>;
  weights?: Record<string, number>;
  star_rating?: number;
  [key: string]: unknown;
}

export interface SummarySectionData {
  metadata?: SectionMetadata;
  star_rating?: string; // "★★★★☆ 4.3/5.0" format
  star_rating_breakdown?: StarRatingBreakdown;
  summary?: AnalysisText;
  key_strengths?: string[];
  improvement_areas?: string[];
  recommendations?: AnalysisText;
  // Fields added after 2026-02 without a version bump — render by key presence
  integrated_score?: number;
  next_action?: string;
  next_run_target?: Record<string, unknown>;
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

// --- Monthly plan (Issue #983) ---

/** Lifecycle of a prescribed session (`weekly_prescriptions.status`). */
export type PrescriptionStatus =
  | "prescribed"
  | "registered"
  | "done"
  | "replaced"
  | "skipped";

/** The strides add-on of an easy prescription (`weekly_prescriptions.strides`). */
export interface PrescriptionStrides {
  reps: number;
  run_seconds?: number | null;
  recovery_seconds?: number | null;
}

export interface Prescription {
  prescription_id: number;
  session_type: string;
  title: string;
  target_km: number | null;
  target_minutes: number | null;
  hr_high: number | null;
  /** Strides riding on an easy row (#1294); null / absent when there are none. */
  strides?: PrescriptionStrides | null;
  /** Coach verdict of the prescribed session (✅ / 🟡 / 🔴), the canonical one. */
  rating?: string | null;
  /** The coach's one-line comment on the session. */
  rationale?: string | null;
  status: PrescriptionStatus | string;
}

/** The run that actually happened on a plan day. */
export interface PlanActivity {
  activity_id: number;
  activity_name: string | null;
  total_distance_km: number | null;
  avg_pace_seconds_per_km: number | null;
  avg_heart_rate: number | null;
}

export interface PlanDay {
  date: string;
  in_month: boolean;
  prescriptions: Prescription[];
  activities: PlanActivity[];
}

/** How a set of prescriptions ended up. `prescribed` is the row count. */
export interface Adherence {
  prescribed: number;
  done: number;
  replaced: number;
  skipped: number;
  pending: number;
}

/** One week of a block's long-run ladder (#977). */
export interface LadderStep {
  week_start?: string;
  target_km?: number | null;
  target_minutes?: number | null;
  hr_ceiling?: number | null;
  kind?: string | null;
  note?: string | null;
}

export interface PlanWeek {
  week_start: string;
  week_end: string;
  in_month: boolean;
  ladder_step: LadderStep | null;
  review_exists: boolean;
  adherence: Adherence;
  days: PlanDay[];
}

export interface TrainingBlock {
  block_id: number;
  phase: string | null;
  title: string | null;
  start_date: string | null;
  end_date: string | null;
  weight_mode: string | null;
  quality_sessions_per_week: number | null;
}

export interface MonthPlan {
  month: string;
  /** 0=Mon .. 6=Sun, the athlete's configured week start (#605). */
  week_start_day: number;
  weeks: PlanWeek[];
  blocks: TrainingBlock[];
  adherence: Adherence;
}
