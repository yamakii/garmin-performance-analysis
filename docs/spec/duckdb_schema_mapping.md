# DuckDB Schema Mapping Specification

**Version**: 2.3
**Last Updated**: 2026-06-20
**Database**: `garmin_performance.duckdb`
**Total Tables**: 19 domain tables (+ `schema_version` migration bookkeeping)

This document provides comprehensive schema documentation for all DuckDB tables in the Garmin performance analysis system. Every column name, type, and primary key below is verified against the live schema (`PRAGMA table_info`). Where prose describes derived/calculated logic, that logic lives in the inserters / form-baseline modules and is documented here because it is not otherwise discoverable from the column definitions.

> **Schema bookkeeping**: a 20th table, `schema_version` (`version INTEGER PK`, `name`, `applied_at`), tracks applied migrations and is **not** a domain table. The migration runner (`database/migrations/registry.py`) applies numbered migrations after `_ensure_tables()` and records them there.

## Change History

### Version 2.3 (2026-06-20)
- **`form_baselines` table dropped** (migration `phase0_power_prep`, schema version 1). Pace-corrected baselines now live solely in `form_baseline_history`, and `activities.body_mass_kg` was backfilled in the same migration.
- **All FOREIGN KEY constraints removed** (migration `remove_fk_constraints`, version 4, 2025-11-01). No table declares FK constraints; `_ensure_tables()` creates FK-free schemas. Referential integrity is maintained by the ingest pipeline, not the database.
- **Power-efficiency columns added** to `form_evaluations` (migration `phase1_power_efficiency`, version 2) and `integrated_score` / `training_mode` (migration `phase2_integrated_score`, version 3).
- **Cadence evaluation columns added** to `form_evaluations` (migration `add_cadence_columns`, version 6).
- **Plan versioning** added: `training_plans.version` and `planned_workouts.version` (migration `add_plan_versioning`, version 5).
- **Athlete-centric tables added**: `athlete_profile`, `athlete_goals`, `season_retrospectives`, `weekly_reviews` (migration `add_athlete_tables`, version 7). These back the `/set-goal`, `/plan-training`, and `/weekly-review` features. DDL for these tables is owned exclusively by the migration (not `_ensure_tables()`) to keep a single source of truth (issue #342).
- **`weekly_reviews` UNIQUE index dropped** (migration `drop_weekly_review_index`, version 8) to allow multiple revisions per week.
- **`body_composition` date index added** as a UNIQUE index (migration `add_body_composition_date_index`, version 9; also created in `_ensure_tables()`).
- **`form_baseline_history` extended** with `model_type` and power-model coefficients (`power_a`, `power_b`, `power_rmse`) alongside the existing `coef_alpha/d/a/b`.

### Version 2.2 (2025-10-28)
- Introduced the unified pace-corrected form evaluation system (`form_baseline_history`, `form_evaluations`, plus the now-dropped `form_baselines`) and MCP tools `get_form_evaluations()`, `get_form_baseline_trend()`.

### Version 2.1 (2025-10-24)
- Simplified `time_series_metrics` cadence to a single `cadence` column holding `directDoubleCadence` (both feet, ~180 spm), removing single-foot/total/fractional variants.

### Version 2.0 (2025-10-20)
- Removed device-unprovided NULL fields (`vo2_max.fitness_age`; `body_composition` metabolic fields) and added derived/evaluation fields across `splits`, `form_efficiency`, `hr_efficiency`, `performance_trends`.

---

## Table of Contents (19 domain tables by category)

| # | Table | Category | Primary Key | Row scale |
|---|-------|----------|-------------|-----------|
| 1 | [activities](#1-activities) | Metadata | `activity_id` | ~520 activities |
| 2 | [body_composition](#2-body_composition) | Metadata | `measurement_id` (UNIQUE on `date`) | daily measurements |
| 3 | [splits](#3-splits) | Performance | `(activity_id, split_index)` | ~9 splits/activity |
| 4 | [time_series_metrics](#4-time_series_metrics) | Performance | `(activity_id, seq_no)` | ~1,000–2,000 rows/activity |
| 5 | [performance_trends](#5-performance_trends) | Performance | `activity_id` | 1/activity |
| 6 | [form_efficiency](#6-form_efficiency) | Physiology | `activity_id` | 1/activity |
| 7 | [form_evaluations](#7-form_evaluations) | Physiology | `eval_id` | ~340/520 (fixable ceiling) |
| 8 | [form_baseline_history](#8-form_baseline_history) | Physiology | `history_id` | monthly × metrics |
| 9 | [hr_efficiency](#9-hr_efficiency) | Physiology | `activity_id` | 1/activity |
| 10 | [heart_rate_zones](#10-heart_rate_zones) | Physiology | `(activity_id, zone_number)` | 5 zones/activity |
| 11 | [vo2_max](#11-vo2_max) | Physiology | `activity_id` | ~78% of activities |
| 12 | [lactate_threshold](#12-lactate_threshold) | Physiology | `activity_id` | ~52% of activities |
| 13 | [training_plans](#13-training_plans) | Training | `plan_id` (+ `version`) | per generated plan |
| 14 | [planned_workouts](#14-planned_workouts) | Training | `workout_id` | per planned session |
| 15 | [section_analyses](#15-section_analyses) | Analysis | `analysis_id` (UNIQUE on `(activity_id, section_type)`) | 5/analyzed activity |
| 16 | [athlete_profile](#16-athlete_profile) | Athlete | `user_id` | 1/user |
| 17 | [athlete_goals](#17-athlete_goals) | Athlete | `goal_id` | per registered goal |
| 18 | [season_retrospectives](#18-season_retrospectives) | Athlete | `retro_id` | per season |
| 19 | [weekly_reviews](#19-weekly_reviews) | Athlete | `review_id` | per weekly review |

---

## 1. activities

**Purpose**: Core activity metadata and summary metrics
**Primary Key**: `activity_id`
**Source**: `data/raw/activity/{activity_id}/activity.json` (+ `weather.json` for weather fields)

### Schema (20 columns)

| Column | Type | Description |
|--------|------|-------------|
| activity_id | BIGINT (PK) | Unique activity identifier |
| activity_date | DATE | Activity date (YYYY-MM-DD) |
| activity_name | VARCHAR | Activity name/title |
| start_time_local | TIMESTAMP | Start time (local timezone) |
| start_time_gmt | TIMESTAMP | Start time (GMT) |
| location_name | VARCHAR | Activity location |
| total_distance_km | DOUBLE | Total distance (km) |
| total_time_seconds | INTEGER | Total duration (seconds) |
| avg_speed_ms | DOUBLE | Average speed (m/s) |
| avg_pace_seconds_per_km | DOUBLE | Average pace (sec/km) |
| avg_heart_rate | INTEGER | Average heart rate (bpm) |
| max_heart_rate | INTEGER | Maximum heart rate (bpm) |
| temp_celsius | DOUBLE | External temperature from `weather.json` (°C) |
| relative_humidity_percent | DOUBLE | Relative humidity from `weather.json` (%) |
| wind_speed_kmh | DOUBLE | Wind speed from `weather.json` (km/h) |
| wind_direction | VARCHAR | Wind direction (compass, e.g. N/NE/E) |
| gear_type | VARCHAR | Gear type |
| gear_model | VARCHAR | Shoe/gear model name |
| base_weight_kg | DOUBLE | Base/reference weight (kg) |
| body_mass_kg | DOUBLE | Body mass at activity time (kg), backfilled from `body_composition` (migration `phase0_power_prep`) |

> **Common name traps** (the live schema differs from older drafts): it is `activity_date` (not `date`); `temp_celsius` (not `external_temp_c`); `relative_humidity_percent` (not `humidity`); `wind_speed_kmh` (not `wind_speed_ms`); `gear_model` (not `gear_name`). There are **no** `created_at`/`updated_at`, and **no** cadence/power/training-effect columns on this table — cadence/power live on `splits`, `time_series_metrics`, and the phase columns of `performance_trends`.

---

## 2. body_composition

**Purpose**: Weight and body composition measurements
**Primary Key**: `measurement_id` — with a **UNIQUE index on `date`** (`idx_body_composition_date`), so one row per day, enabling idempotent date-keyed upsert (`INSERT OR REPLACE`) on cache backfill.
**Source**: `data/raw/weight/YYYY-MM-DD.json`

### Schema (9 columns)

| Column | Type | Description |
|--------|------|-------------|
| measurement_id | INTEGER (PK) | Unique measurement ID |
| date | DATE | Measurement date (UNIQUE) |
| weight_kg | DOUBLE | Weight (kg) |
| body_fat_percentage | DOUBLE | Body fat (%) |
| muscle_mass_kg | DOUBLE | Muscle mass (kg) |
| bone_mass_kg | DOUBLE | Bone mass (kg) |
| bmi | DOUBLE | Body mass index |
| hydration_percentage | DOUBLE | Hydration (%) |
| measurement_source | VARCHAR | Measurement device/source |

> 5 metabolic fields (basal/active metabolic rate, metabolic age, visceral fat rating, physique rating) were removed in v2.0 — the device does not provide them.

---

## 3. splits

**Purpose**: 1km lap/split-level performance data with environmental calculations
**Primary Key**: `(activity_id, split_index)`
**Source**: `data/raw/activity/{activity_id}/splits.json` (lapDTOs)

### Schema (34 columns)

| Column | Type | Source | Description |
|--------|------|--------|-------------|
| activity_id | BIGINT (PK) | activityId | Activity reference |
| split_index | INTEGER (PK) | lapIndex | Split number (1-based) |
| distance | DOUBLE | distance | Split distance (m) |
| duration_seconds | DOUBLE | duration | Split duration (s) |
| start_time_gmt | VARCHAR | startTimeGMT | Split start time |
| start_time_s | INTEGER | Calculated | Split start offset (s) |
| end_time_s | INTEGER | start_time_s + duration | Split end offset (s) |
| intensity_type | VARCHAR | intensityType | Garmin intensity (WARMUP/INTERVAL/RECOVERY/COOLDOWN/REST) |
| role_phase | VARCHAR | Derived from position | Workout phase classification (warmup/run/recovery/cooldown) |
| pace_str | VARCHAR | averageSpeed → mm:ss | Human-readable pace |
| pace_seconds_per_km | DOUBLE | 1000 / averageSpeed | Pace (sec/km) |
| heart_rate | INTEGER | averageHR | Average HR (bpm) |
| **hr_zone** | VARCHAR | **CALCULATED** | HR zone mapping (Zone1–5) |
| cadence | DOUBLE | averageRunCadence | Cadence (spm, both feet) |
| **cadence_rating** | VARCHAR | **CALCULATED** | Cadence quality (Excellent/Good/Fair/Low) |
| power | DOUBLE | avgPower | Average power (W) |
| **power_efficiency** | VARCHAR | **CALCULATED** | Power efficiency (Excellent/Good/Fair/Low) |
| stride_length | DOUBLE | strideLength | Stride length (cm) |
| ground_contact_time | DOUBLE | groundContactTime | GCT (ms) |
| vertical_oscillation | DOUBLE | verticalOscillation | VO (cm) |
| vertical_ratio | DOUBLE | verticalRatio | VR (%) |
| elevation_gain | DOUBLE | elevationGain | Elevation gain (m) |
| elevation_loss | DOUBLE | elevationLoss | Elevation loss (m) |
| terrain_type | VARCHAR | Calculated from elevation | Terrain classification |
| **environmental_conditions** | VARCHAR | **CALCULATED** | Weather summary |
| **wind_impact** | VARCHAR | **CALCULATED** | Wind impact (None/Light/Moderate/Strong) |
| **temp_impact** | VARCHAR | **CALCULATED** | Temperature impact band |
| **environmental_impact** | VARCHAR | **CALCULATED** | Combined environmental impact |
| max_heart_rate | INTEGER | maxHR | Max HR in split (bpm) |
| max_cadence | DOUBLE | maxRunCadence | Max cadence in split (spm) |
| max_power | DOUBLE | maxPower | Max power in split (W) |
| normalized_power | DOUBLE | normPower | Normalized power (W) |
| average_speed | DOUBLE | averageSpeed | Average speed (m/s) |
| grade_adjusted_speed | DOUBLE | gradeAdjustedSpeed | Grade-adjusted speed (m/s) |

### Calculation Logic (derived fields)

#### hr_zone
Maps `heart_rate` to a zone using `heart_rate_zones` boundaries:
- Zone 1: < zone2_low; Zone 2: zone2_low ≤ HR < zone3_low; Zone 3: zone3_low ≤ HR < zone4_low; Zone 4: zone4_low ≤ HR < zone5_low; Zone 5: ≥ zone5_low

#### cadence_rating (both-feet spm)
- Excellent: ≥190 · Good: 180–189 · Fair: 170–179 · Low: <170

#### power_efficiency (W/kg)
- Excellent: ≥4.0 · Good: 3.0–3.9 · Fair: 2.0–2.9 · Low: <2.0

#### environmental_conditions
Combines temperature, humidity, wind from `weather.json` (e.g. `"18.5°C, 65%, Wind: 3.2km/h NE"`).

#### wind_impact (by wind speed)
- None: light · Light · Moderate · Strong — thresholds scale with the unit recorded in `weather.json`.

#### temp_impact (training-type-aware)
- Recovery: 15–22°C = Good (wider tolerance)
- Base Run: 10–18°C = Ideal, 18–23°C = Acceptable
- Tempo/Threshold: 8–15°C = Ideal, 15–20°C = Good, 20–25°C = Slightly hot
- Interval/Sprint: 8–15°C = Ideal, 20–23°C = Slightly hot, >23°C = Dangerous

#### environmental_impact
Combines wind + temperature bands: Negligible (both ideal) → Low → Moderate → High (strong wind or hot/dangerous temp).

> **Temperature note**: split-level environmental fields derive from `weather.json` (external station), **not** device temperature in `time_series_metrics.air_temperature` (which runs +5–8°C from body heat).

### MCP Tools for Splits Data
- `get_splits_comprehensive(activity_id, statistics_only=True/False)` — 12-field one-call view; ~67% token reduction with `statistics_only=True`.
- Lightweight: `get_splits_pace_hr()`, `get_splits_form_metrics()`, `get_splits_elevation()`.

---

## 4. time_series_metrics

**Purpose**: Second-by-second detailed metrics
**Primary Key**: `(activity_id, seq_no)` — note the PK is on `seq_no`, **not** `timestamp_s`. A non-unique secondary index `idx_time_series_timestamp` exists on `(activity_id, timestamp_s)`, plus `idx_time_series_activity` on `(activity_id)`.
**Source**: `data/raw/activity/{activity_id}/metrics.json`

### Schema (26 columns)

| Column | Type | Description |
|--------|------|-------------|
| activity_id | BIGINT (PK) | Activity reference |
| seq_no | INTEGER (PK) | Sequence number |
| timestamp_s | INTEGER | Timestamp offset (seconds) |
| sum_moving_duration | DOUBLE | Cumulative moving duration |
| sum_duration | DOUBLE | Cumulative total duration |
| sum_elapsed_duration | DOUBLE | Cumulative elapsed duration |
| sum_distance | DOUBLE | Cumulative distance (m) |
| sum_accumulated_power | DOUBLE | Cumulative power |
| heart_rate | DOUBLE | Instantaneous HR (bpm) |
| speed | DOUBLE | Instantaneous speed (m/s) |
| grade_adjusted_speed | DOUBLE | Grade-adjusted speed (m/s) |
| cadence | DOUBLE | Both-feet cadence from `directDoubleCadence` (~180 spm, raw from Garmin API) |
| power | DOUBLE | Instantaneous power (W) |
| ground_contact_time | DOUBLE | GCT (ms) |
| vertical_oscillation | DOUBLE | VO (cm) |
| vertical_ratio | DOUBLE | VR (%) |
| stride_length | DOUBLE | Stride length (cm) |
| vertical_speed | DOUBLE | Vertical speed (m/s) |
| elevation | DOUBLE | Elevation (m) |
| air_temperature | DOUBLE | Device temperature (°C, +5–8°C body heat) |
| latitude | DOUBLE | GPS latitude |
| longitude | DOUBLE | GPS longitude |
| available_stamina | DOUBLE | Available stamina |
| potential_stamina | DOUBLE | Potential stamina |
| body_battery | DOUBLE | Body battery level |
| performance_condition | DOUBLE | Performance condition |

> There is a single `cadence` column. The legacy `cadence_single_foot` / `cadence_total` / `fractional_cadence` columns are **not present** (removed v2.1).

---

## 5. performance_trends

**Purpose**: Performance patterns and 4-phase workout analysis (warmup / run / recovery / cooldown)
**Primary Key**: `activity_id`
**Source**: Calculated from `splits.json`

### Schema (33 columns)

| Column | Type | Description |
|--------|------|-------------|
| activity_id | BIGINT (PK) | Activity reference |
| pace_consistency | DOUBLE | Pace consistency score |
| hr_drift_percentage | DOUBLE | HR drift (%) |
| cadence_consistency | VARCHAR | Cadence consistency rating |
| fatigue_pattern | VARCHAR | Fatigue pattern classification |
| warmup_splits | VARCHAR | Comma-separated warmup split indices |
| warmup_avg_pace_seconds_per_km | DOUBLE | Warmup avg pace (sec/km) |
| warmup_avg_pace_str | VARCHAR | Warmup pace (mm:ss) |
| warmup_avg_hr | DOUBLE | Warmup avg HR |
| warmup_avg_cadence | DOUBLE | Warmup avg cadence |
| warmup_avg_power | DOUBLE | Warmup avg power |
| warmup_evaluation | VARCHAR | Warmup quality evaluation |
| run_splits | VARCHAR | Comma-separated run split indices |
| run_avg_pace_seconds_per_km | DOUBLE | Run avg pace (sec/km) |
| run_avg_pace_str | VARCHAR | Run pace (mm:ss) |
| run_avg_hr | DOUBLE | Run avg HR |
| run_avg_cadence | DOUBLE | Run avg cadence |
| run_avg_power | DOUBLE | Run avg power |
| run_evaluation | VARCHAR | Run quality evaluation |
| recovery_splits | VARCHAR | Comma-separated recovery split indices |
| recovery_avg_pace_seconds_per_km | DOUBLE | Recovery avg pace (sec/km) |
| recovery_avg_pace_str | VARCHAR | Recovery pace (mm:ss) |
| recovery_avg_hr | DOUBLE | Recovery avg HR |
| recovery_avg_cadence | DOUBLE | Recovery avg cadence |
| recovery_avg_power | DOUBLE | Recovery avg power |
| recovery_evaluation | VARCHAR | Recovery quality evaluation |
| cooldown_splits | VARCHAR | Comma-separated cooldown split indices |
| cooldown_avg_pace_seconds_per_km | DOUBLE | Cooldown avg pace (sec/km) |
| cooldown_avg_pace_str | VARCHAR | Cooldown pace (mm:ss) |
| cooldown_avg_hr | DOUBLE | Cooldown avg HR |
| cooldown_avg_cadence | DOUBLE | Cooldown avg cadence |
| cooldown_avg_power | DOUBLE | Cooldown avg power |
| cooldown_evaluation | VARCHAR | Cooldown quality evaluation |

### Calculation Logic

#### Phase detection (from `splits.intensity_type`)
Warmup = `WARMUP` · Run = `INTERVAL` / active (main work) · Recovery = `RECOVERY` · Cooldown = `COOLDOWN`. Per-phase pace/HR/cadence/power are averages of the splits in that phase (power NULL if no power data).

#### Phase evaluations
- **warmup**: Excellent = gradual pace increase + steady HR rise; Good = ≥5 min; Needs Improvement = <3 min or missing.
- **run** (training-type-aware): Excellent = consistent pace (CV <5%), stable HR; Good = CV 5–10%; Needs Improvement = CV >10%.
- **recovery**: Excellent = HR drops ≥20 bpm and cadence drops ≥10 spm vs run; Good = HR drops 10–19 bpm; Needs Improvement = HR drop <10 bpm.
- **cooldown**: Excellent = gradual pace decrease + steady HR fall; Good = ≥5 min; Needs Improvement = <3 min or missing.

---

## 6. form_efficiency

**Purpose**: Running form efficiency summary (GCT/VO/VR), aggregated from splits
**Primary Key**: `activity_id`
**Source**: Aggregated from `splits.json` (lapDTOs)

### Schema (21 columns)

| Column | Type | Description |
|--------|------|-------------|
| activity_id | BIGINT (PK) | Activity reference |
| gct_average | DOUBLE | Average GCT (ms) |
| gct_min | DOUBLE | Minimum GCT (ms) |
| gct_max | DOUBLE | Maximum GCT (ms) |
| gct_std | DOUBLE | GCT standard deviation |
| gct_variability | DOUBLE | GCT variability `(std/avg)*100` (%) |
| gct_rating | VARCHAR | GCT quality rating (★) |
| gct_evaluation | VARCHAR | GCT quality evaluation text |
| vo_average | DOUBLE | Average VO (cm) |
| vo_min | DOUBLE | Minimum VO (cm) |
| vo_max | DOUBLE | Maximum VO (cm) |
| vo_std | DOUBLE | VO standard deviation |
| vo_trend | VARCHAR | VO trend (increasing/stable/decreasing) |
| vo_rating | VARCHAR | VO quality rating (★) |
| vo_evaluation | VARCHAR | VO quality evaluation text |
| vr_average | DOUBLE | Average VR (%) |
| vr_min | DOUBLE | Minimum VR (%) |
| vr_max | DOUBLE | Maximum VR (%) |
| vr_std | DOUBLE | VR standard deviation |
| vr_rating | VARCHAR | VR quality rating (★) |
| vr_evaluation | VARCHAR | VR quality evaluation text |

### Calculation Logic
- **gct_evaluation** (by `gct_average`): Excellent <200ms · Good 200–250ms · Fair 250–300ms · Poor >300ms
- **vo_evaluation** (by `vo_average`): Excellent <7cm · Good 7–10cm · Fair 10–12cm · Poor >12cm
- **vr_evaluation** (by `vr_average`): Excellent <7% · Good 7–8% · Fair 8–10% · Poor >10%
- **vo_trend**: Increasing = VO worsens >5% start→end · Stable = ≤5% · Decreasing = improves >5%

> These fixed-threshold ratings are the simple aggregate view. The pace-corrected (speed-aware) evaluation lives in `form_evaluations`, which is the authoritative source for star ratings and needs-improvement flags.

---

## 7. form_evaluations

**Purpose**: Pace-corrected per-activity form evaluation with star ratings and needs-improvement flags
**Primary Key**: `eval_id` (one row per `activity_id`)
**Source**: Generated by the form-baseline evaluator (`form_baseline/evaluator.py`) using coefficients from `form_baseline_history`.

### Schema (46 columns)

| Column | Type | Description |
|--------|------|-------------|
| eval_id | INTEGER (PK) | Unique evaluation ID |
| activity_id | BIGINT | Activity reference (one per activity) |
| gct_ms_expected | FLOAT | Expected GCT from pace (ms) |
| vo_cm_expected | FLOAT | Expected VO from pace (cm) |
| vr_pct_expected | FLOAT | Expected VR from pace (%) |
| gct_ms_actual | FLOAT | Actual GCT (ms) |
| vo_cm_actual | FLOAT | Actual VO (cm) |
| vr_pct_actual | FLOAT | Actual VR (%) |
| gct_delta_pct | FLOAT | GCT deviation (%) |
| vo_delta_cm | FLOAT | VO deviation (cm) |
| vr_delta_pct | FLOAT | VR deviation (%) |
| gct_penalty | FLOAT | GCT penalty score |
| gct_star_rating | VARCHAR | GCT rating (★★★★★ ~ ★☆☆☆☆) |
| gct_score | FLOAT | GCT score (0–5.0) |
| gct_needs_improvement | BOOLEAN | GCT needs-improvement flag |
| gct_evaluation_text | VARCHAR | GCT evaluation text (Japanese) |
| vo_penalty | FLOAT | VO penalty score |
| vo_star_rating | VARCHAR | VO rating |
| vo_score | FLOAT | VO score (0–5.0) |
| vo_needs_improvement | BOOLEAN | VO needs-improvement flag |
| vo_evaluation_text | VARCHAR | VO evaluation text (Japanese) |
| vr_penalty | FLOAT | VR penalty score |
| vr_star_rating | VARCHAR | VR rating |
| vr_score | FLOAT | VR score (0–5.0) |
| vr_needs_improvement | BOOLEAN | VR needs-improvement flag |
| vr_evaluation_text | VARCHAR | VR evaluation text (Japanese) |
| cadence_actual | FLOAT | Actual cadence (spm) |
| cadence_minimum | INTEGER | Minimum cadence threshold (spm) |
| cadence_achieved | BOOLEAN | Cadence achievement flag |
| overall_score | FLOAT | Overall form score (0–5.0) |
| overall_star_rating | VARCHAR | Overall rating |
| power_avg_w | FLOAT | Average power (W) |
| power_wkg | FLOAT | Power-to-weight (W/kg) |
| speed_actual_mps | FLOAT | Actual speed (m/s) |
| speed_expected_mps | FLOAT | Expected speed from power model (m/s) |
| power_efficiency_score | FLOAT | Power efficiency score |
| power_efficiency_rating | VARCHAR | Power efficiency rating |
| power_efficiency_needs_improvement | BOOLEAN | Power efficiency needs-improvement flag |
| integrated_score | FLOAT | Integrated form+power score (migration v3) |
| training_mode | VARCHAR | Training mode classification (migration v3) |
| evaluated_at | TIMESTAMP | Evaluation timestamp |
| cadence_expected | DOUBLE | Expected cadence (spm) (migration v6) |
| cadence_delta_pct | DOUBLE | Cadence deviation (%) (migration v6) |
| cadence_star_rating | VARCHAR | Cadence rating (migration v6) |
| cadence_score | DOUBLE | Cadence score (0–5.0) (migration v6) |
| cadence_needs_improvement | BOOLEAN | Cadence needs-improvement flag (migration v6) |
| cadence_evaluation_text | VARCHAR | Cadence evaluation text (Japanese) (migration v6) |

### Evaluation Logic
- **Score**: start at perfect (100), apply penalty by deviation from the pace-expected value, then map to 0–5.0. Roughly: ±2% → ★★★★★ 5.0; 2–5% → ~★★★★☆ 4.0; 5–10% → ~★★★☆☆ 3.0; >10% → ★★☆☆☆ / ★☆☆☆☆.
- **needs_improvement**: true when deviation > ~5% from expected.
- **overall_score**: combines GCT/VO/VR (GCT weighted highest); `integrated_score` further folds in power efficiency.

> **Authoritative source**: when an agent reports a star rating or "needs improvement", `form_evaluations` is the source of truth — it is pace-corrected, unlike the fixed-threshold `form_efficiency` ratings.

> **Population ceiling**: ~340/520 runs. The remainder lack recorded GCT/VO/VR or have no preceding baseline period and are permanently un-fixable; repeated backfill does not raise coverage.

---

## 8. form_baseline_history

**Purpose**: Rolling-window pace-corrected baseline coefficients for trend analysis (replaces the dropped `form_baselines`)
**Primary Key**: `history_id`
**Source**: Monthly baseline training (rolling window) over splits data.

### Schema (19 columns)

| Column | Type | Description |
|--------|------|-------------|
| history_id | INTEGER (PK) | Unique history ID |
| user_id | VARCHAR | User identifier (default `'default'`) |
| condition_group | VARCHAR | Terrain group (default `'flat_road'`) |
| metric | VARCHAR | Metric name (`gct`, `vo`, `vr`) |
| model_type | VARCHAR | Model family (power vs linear) |
| coef_alpha | FLOAT | GCT power model: `log(v)` intercept (α) |
| coef_d | FLOAT | GCT power model: exponent (d < 0, monotonic) |
| coef_a | FLOAT | VO/VR linear model: intercept (a) |
| coef_b | FLOAT | VO/VR linear model: slope (b) |
| period_start | DATE | Training window start |
| period_end | DATE | Training window end (inclusive) |
| trained_at | TIMESTAMP | Training timestamp |
| n_samples | INTEGER | Training samples in window |
| rmse | FLOAT | Root mean squared error |
| speed_range_min | FLOAT | Minimum training speed (m/s) |
| speed_range_max | FLOAT | Maximum training speed (m/s) |
| power_a | FLOAT | Power model coefficient a (speed-from-power) |
| power_b | FLOAT | Power model coefficient b |
| power_rmse | FLOAT | Power model RMSE |

### Model Types
- **GCT**: power regression `v = exp((log(GCT) - α) / d)`, constrained `d < 0` so faster pace → shorter GCT. Trained with Huber regression + IQR outlier removal.
- **VO / VR**: linear regression `y = a + b·v` (Huber + IQR outlier removal).
- **Power**: speed-from-power relationship (`power_a`, `power_b`) used for power-efficiency scoring in `form_evaluations`.

### Trend Usage
`get_form_baseline_trend(activity_id, activity_date)`:
1. Retrieves the baseline whose `[period_start, period_end]` contains `activity_date`.
2. Retrieves the ~1-month-earlier baseline.
3. Computes Δd (GCT) / Δb (VO/VR); negative deltas = improvement (shorter GCT / less bounce at the same pace).

> Baselines are **not** generated automatically — monthly backfill is required, and "No baseline found" usually means no trained window covers the year/period of the activity.

---

## 9. hr_efficiency

**Purpose**: Heart-rate efficiency and training-quality analysis
**Primary Key**: `activity_id`
**Source**: HR-zone data + activity metadata

### Schema (14 columns)

| Column | Type | Description |
|--------|------|-------------|
| activity_id | BIGINT (PK) | Activity reference |
| primary_zone | VARCHAR | Zone with most time |
| zone_distribution_rating | VARCHAR | Distribution quality |
| hr_stability | VARCHAR | HR stability rating |
| aerobic_efficiency | VARCHAR | Aerobic efficiency rating |
| training_quality | VARCHAR | Overall training quality |
| zone2_focus | BOOLEAN | Zone 2 focus indicator |
| zone4_threshold_work | BOOLEAN | Zone 4+ threshold-work indicator |
| training_type | VARCHAR | Training type (aerobic_base/tempo/threshold/…) |
| zone1_percentage | DOUBLE | Zone 1 time (%) |
| zone2_percentage | DOUBLE | Zone 2 time (%) |
| zone3_percentage | DOUBLE | Zone 3 time (%) |
| zone4_percentage | DOUBLE | Zone 4 time (%) |
| zone5_percentage | DOUBLE | Zone 5 time (%) |

### Calculation Logic
- **primary_zone**: zone with max time.
- **zone_distribution_rating** (training-type-aware): Recovery Z1+Z2 ≥80%; Base Z2 ≥60%; Tempo Z3+Z4 ≥50%; Threshold Z4 ≥40%; Interval Z4+Z5 ≥60% = Excellent.
- **aerobic_efficiency** (by Z1+Z2 %): Excellent ≥80% · Good 60–79% · Fair 40–59% · Poor <40%.
- **training_quality**: combines distribution rating + primary zone + training type.
- **zone2_focus**: true if Z2 ≥50%. **zone4_threshold_work**: true if Z4+Z5 ≥20%.

> Zone percentages use Garmin-native HR zones from `heart_rate_zones` — never a computed formula (e.g. 220−age).

---

## 10. heart_rate_zones

**Purpose**: HR zone boundaries and time distribution
**Primary Key**: `(activity_id, zone_number)` (composite)
**Source**: HR-zone JSON

### Schema (6 columns)

| Column | Type | Description |
|--------|------|-------------|
| activity_id | BIGINT (PK) | Activity reference |
| zone_number | INTEGER (PK) | Zone number (1–5) |
| zone_low_boundary | INTEGER | Zone lower HR boundary (bpm) |
| zone_high_boundary | INTEGER | Zone upper HR boundary (bpm) |
| time_in_zone_seconds | DOUBLE | Time spent in zone (s) |
| zone_percentage | DOUBLE | Time in zone (%) |

---

## 11. vo2_max

**Purpose**: VO2 max estimates
**Primary Key**: `activity_id`
**Source**: VO2-max JSON

### Schema (5 columns)

| Column | Type | Description |
|--------|------|-------------|
| activity_id | BIGINT (PK) | Activity reference |
| precise_value | DOUBLE | Precise VO2 max (ml/kg/min) |
| value | DOUBLE | Rounded VO2 max (ml/kg/min) |
| date | DATE | Measurement date |
| category | INTEGER | Fitness category (0–6) |

> `fitness_age` removed in v2.0. Population ~78% — Garmin provides VO2 max only for certain activity types.

---

## 12. lactate_threshold

**Purpose**: Lactate-threshold and FTP estimates
**Primary Key**: `activity_id`
**Source**: Lactate-threshold JSON

### Schema (8 columns)

| Column | Type | Description |
|--------|------|-------------|
| activity_id | BIGINT (PK) | Activity reference |
| heart_rate | INTEGER | Lactate-threshold HR (bpm) |
| speed_mps | DOUBLE | Lactate-threshold speed (m/s) |
| date_hr | TIMESTAMP | HR-threshold measurement timestamp |
| functional_threshold_power | INTEGER | FTP (W) |
| power_to_weight | DOUBLE | FTP / weight (W/kg) |
| weight | DOUBLE | Weight at measurement (kg) |
| date_power | TIMESTAMP | FTP measurement timestamp |

> Population ~52% — requires sufficient training history for Garmin to estimate.

---

## 13. training_plans

**Purpose**: Generated training-plan headers (backs `/plan-training`). Versioned — one plan_id can have multiple `version` rows.
**Primary Key**: logically `(plan_id, version)`; the live table declares no PK constraint (FK/PK constraints removed; uniqueness enforced by the writer).
**Source**: `save_training_plan` MCP tool / training-plan generator.

### Schema (16 columns)

| Column | Type | Description |
|--------|------|-------------|
| plan_id | VARCHAR | Plan identifier |
| version | INTEGER | Plan revision (migration `add_plan_versioning`) |
| goal_type | VARCHAR | Goal/race type |
| target_race_date | DATE | Target race date |
| target_time_seconds | INTEGER | Target finish time (s) |
| vdot | DOUBLE | VDOT fitness estimate |
| pace_zones_json | VARCHAR | JSON of derived pace zones |
| total_weeks | INTEGER | Plan length (weeks) |
| start_date | DATE | Plan start date |
| weekly_volume_start_km | DOUBLE | Initial weekly volume (km) |
| weekly_volume_peak_km | DOUBLE | Peak weekly volume (km) |
| runs_per_week | INTEGER | Runs per week |
| frequency_progression_json | VARCHAR | JSON frequency progression |
| personalization_notes | VARCHAR | Personalization narrative |
| status | VARCHAR | Plan status (active/archived/…) |
| created_at | TIMESTAMP | Creation timestamp |

---

## 14. planned_workouts

**Purpose**: Individual planned sessions belonging to a training plan; links plan → actual activity and tracks adherence.
**Primary Key**: `workout_id`
**Source**: Training-plan generator / Garmin upload flow.

### Schema (21 columns)

| Column | Type | Description |
|--------|------|-------------|
| workout_id | VARCHAR (PK) | Workout identifier |
| plan_id | VARCHAR | Parent plan reference |
| week_number | INTEGER | Plan week (1-based) |
| day_of_week | INTEGER | Day of week |
| workout_date | DATE | Scheduled date |
| workout_type | VARCHAR | Workout type (easy/tempo/interval/long/…) |
| description_ja | VARCHAR | Japanese description |
| target_distance_km | DOUBLE | Target distance (km) |
| target_duration_minutes | DOUBLE | Target duration (min) |
| target_pace_low | DOUBLE | Target pace low bound (sec/km) |
| target_pace_high | DOUBLE | Target pace high bound (sec/km) |
| target_hr_low | INTEGER | Target HR low (bpm) |
| target_hr_high | INTEGER | Target HR high (bpm) |
| intervals_json | VARCHAR | JSON interval structure |
| phase | VARCHAR | Plan phase (base/build/peak/taper) |
| garmin_workout_id | BIGINT | Uploaded Garmin workout ID |
| uploaded_at | TIMESTAMP | Upload timestamp |
| actual_activity_id | BIGINT | Matched executed activity |
| adherence_score | DOUBLE | Plan-vs-actual adherence |
| completed_at | TIMESTAMP | Completion timestamp |
| version | INTEGER | Plan-version link (migration `add_plan_versioning`) |

---

## 15. section_analyses

**Purpose**: Agent-generated analysis results (5 section types per analyzed activity)
**Primary Key**: `analysis_id` — with a **UNIQUE index on `(activity_id, section_type)`** (`idx_activity_section`), so re-analysis replaces rather than duplicates a section.
**Source**: Section-analysis agents (`unified-section-analyst`, `split-section-analyst`).

### Schema (8 columns)

| Column | Type | Description |
|--------|------|-------------|
| analysis_id | INTEGER (PK) | Unique analysis ID |
| activity_id | BIGINT | Activity reference |
| activity_date | DATE | Activity date |
| section_type | VARCHAR | Section (split/phase/summary/efficiency/environment) |
| analysis_data | VARCHAR | JSON analysis payload (Japanese narrative + English keys) |
| created_at | TIMESTAMP | Creation timestamp |
| agent_name | VARCHAR | Agent identifier |
| agent_version | VARCHAR | Agent version |

### Section Types
1. **split** — 1km split analysis (pace/HR/form), from `split-section-analyst`.
2. **phase** — warmup/run/cooldown[/recovery] evaluation, training-type-aware.
3. **summary** — activity-type classification + 4-axis overall assessment.
4. **efficiency** — form (GCT/VO/VR) + power + cadence + HR efficiency.
5. **environment** — environmental impact (temperature, humidity, wind, terrain).

---

## 16. athlete_profile

**Purpose**: Athlete's current training focus (read by `/plan-training` and `/weekly-review`; written by `/set-goal`)
**Primary Key**: `user_id`
**Source**: `save_athlete_profile` / `/set-goal`. Owned by migration `add_athlete_tables` (version 7).

### Schema (4 columns)

| Column | Type | Description |
|--------|------|-------------|
| user_id | VARCHAR (PK) | User identifier |
| current_focus | VARCHAR | Current training focus |
| focus_notes | VARCHAR | Focus notes (rendered as `【見出し】` sections in the Web app) |
| updated_at | TIMESTAMP | Last update timestamp |

---

## 17. athlete_goals

**Purpose**: Registered race goals (target races, priorities, target times)
**Primary Key**: `goal_id`
**Source**: `/set-goal`. Owned by migration `add_athlete_tables`.

### Schema (12 columns)

| Column | Type | Description |
|--------|------|-------------|
| goal_id | INTEGER (PK) | Goal identifier |
| user_id | VARCHAR | User identifier |
| race_name | VARCHAR | Race name |
| race_date | DATE | Race date |
| priority | VARCHAR | Goal priority (A/B/C) |
| goal_type | VARCHAR | Goal type |
| distance_km | DOUBLE | Race distance (km) |
| target_time_seconds | INTEGER | Target finish time (s) |
| status | VARCHAR | Goal status |
| notes | VARCHAR | Free-form notes |
| created_at | TIMESTAMP | Creation timestamp |
| updated_at | TIMESTAMP | Last update timestamp |

---

## 18. season_retrospectives

**Purpose**: Last-season retrospective narrative used as context by `/plan-training` and `/weekly-review`
**Primary Key**: `retro_id`
**Source**: `/set-goal`. Owned by migration `add_athlete_tables`.

### Schema (8 columns)

| Column | Type | Description |
|--------|------|-------------|
| retro_id | INTEGER (PK) | Retrospective identifier |
| user_id | VARCHAR | User identifier |
| season_label | VARCHAR | Season label |
| period_start | DATE | Season start |
| period_end | DATE | Season end |
| narrative | VARCHAR | Retrospective narrative |
| key_learnings | VARCHAR | Key learnings |
| created_at | TIMESTAMP | Creation timestamp |

---

## 19. weekly_reviews

**Purpose**: Coach-perspective weekly training reviews (backs `/weekly-review`)
**Primary Key**: `review_id` — the former UNIQUE index was **dropped** (migration `drop_weekly_review_index`, version 8) to allow multiple revisions of the same week.
**Source**: `save_weekly_review` / `/weekly-review`. Owned by migration `add_athlete_tables`.

### Schema (9 columns)

| Column | Type | Description |
|--------|------|-------------|
| review_id | INTEGER (PK) | Review identifier |
| user_id | VARCHAR | User identifier |
| week_start_date | DATE | Review week start |
| week_end_date | DATE | Review week end |
| review_date | DATE | Date the review was written |
| review_data | VARCHAR | JSON review payload |
| created_at | TIMESTAMP | Creation timestamp |
| agent_name | VARCHAR | Agent identifier |
| agent_version | VARCHAR | Agent version |

---

## Indexes & Constraints Summary

- **No FOREIGN KEY constraints** anywhere (removed 2025-11-01, migration `remove_fk_constraints`). Referential integrity is enforced by the ingest pipeline.
- UNIQUE: `idx_body_composition_date` on `body_composition(date)`; `idx_activity_section` on `section_analyses(activity_id, section_type)`.
- Composite PKs: `splits(activity_id, split_index)`, `time_series_metrics(activity_id, seq_no)`, `heart_rate_zones(activity_id, zone_number)`.
- Secondary indexes on `time_series_metrics`: `idx_time_series_activity(activity_id)`, `idx_time_series_timestamp(activity_id, timestamp_s)`.
- Sequences back the surrogate keys for `form_evaluations` (`form_evaluations_seq`), `form_baseline_history` (`form_baseline_history_seq`), and `section_analyses` (`seq_section_analyses_id`).

---

## Data Pipeline

```
Raw Data (API)
    ↓
data/raw/activity/{id}/
    ├── activity.json          → activities, hr_efficiency
    ├── splits.json            → splits, form_efficiency, performance_trends
    ├── hr_zones.json          → heart_rate_zones, hr_efficiency
    ├── vo2_max.json           → vo2_max
    ├── lactate_threshold.json → lactate_threshold
    ├── weather.json           → activities (weather fields), splits (env fields)
    └── metrics.json           → time_series_metrics
data/raw/weight/YYYY-MM-DD.json → body_composition
    ↓
DuckDB Inserters (13 table-specific inserters)
    ↓
garmin_performance.duckdb (19 domain tables + schema_version)
    ↓
Form Baseline System
    ├── monthly baseline training → form_baseline_history (rolling window)
    └── evaluator.py              → form_evaluations (per activity)
    ↓
MCP Tools (46 tools, token-optimized)
    ↓
Analysis Agents (unified-section-analyst + split-section-analyst)
    → section_analyses (5 sections/activity)
    ↓
Web App (read-only viewer; goals/plans/reviews stored via skills)
```

---

## Maintenance Notes

### Surgical regeneration
```bash
uv run python -m garmin_mcp.scripts.regenerate_duckdb \
  --tables splits form_efficiency hr_efficiency performance_trends \
  --activity-ids <ids> --force
```

### Migrations
Numbered migrations live in `database/migrations/` and are registered in `registry.py`; they run after `_ensure_tables()` during `GarminDBWriter` init. `backup_if_pending` snapshots the production DB before applying pending migrations (2 generations; raises on failure).

### Backup Policy
`data/` and `result/` are **git-untracked — deletion is unrecoverable**. Verify contents and confirm with the user before any destructive operation; keep timestamped backups before schema changes.

### Testing Requirements
- No production-DB dependence; all tests carry a pytest marker (`unit`/`integration`/`performance`/`garmin_api`).
- Use the `initialized_db_path` fixture rather than constructing a writer per test.

---

**End of Schema Documentation**
