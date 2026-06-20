# DuckDB Schema Mapping Specification

**Version**: 2.3
**Last Updated**: 2026-06-20
**Database**: `garmin_performance.duckdb`
**Total Tables**: 19 domain tables (+ `schema_version` migration bookkeeping)

This document provides comprehensive schema documentation for all DuckDB tables in the Garmin performance analysis system. Every column name, type, and primary key below is verified against the live schema (`PRAGMA table_info`). Where prose describes derived/calculated logic, that logic lives in the inserters / form-baseline modules and is documented here because it is not otherwise discoverable from the column definitions.

> **Half-generated**: the per-table `| Column | Type |` tables (PK marked `(PK)`) between
> `<!-- BEGIN GENERATED: schema:<table> -->` / `<!-- END GENERATED: schema:<table> -->`
> markers are rendered from the live schema by
> `garmin_mcp.scripts.generate_schema_doc`. Do not edit them by hand. The surrounding
> prose (units, sources, calculation logic, change history) is hand-written and preserved
> verbatim. Regenerate with:
> ```bash
> uv run --directory packages/garmin-mcp-server \
>   python -m garmin_mcp.scripts.generate_schema_doc
> ```
> A drift test (`tests/scripts/test_generate_schema_doc.py`) fails CI if a schema change
> lands without regenerating.

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

### Schema

<!-- BEGIN GENERATED: schema:activities -->
| Column | Type |
|--------|------|
| activity_id (PK) | BIGINT |
| activity_date | DATE |
| activity_name | VARCHAR |
| start_time_local | TIMESTAMP |
| start_time_gmt | TIMESTAMP |
| location_name | VARCHAR |
| total_distance_km | DOUBLE |
| total_time_seconds | INTEGER |
| avg_speed_ms | DOUBLE |
| avg_pace_seconds_per_km | DOUBLE |
| avg_heart_rate | INTEGER |
| max_heart_rate | INTEGER |
| temp_celsius | DOUBLE |
| relative_humidity_percent | DOUBLE |
| wind_speed_kmh | DOUBLE |
| wind_direction | VARCHAR |
| gear_type | VARCHAR |
| gear_model | VARCHAR |
| base_weight_kg | DOUBLE |
| body_mass_kg | DOUBLE |
<!-- END GENERATED: schema:activities -->

**Units & sources** (not derivable from column names): `total_distance_km` (km); `total_time_seconds` (s); `avg_speed_ms` (m/s); `avg_pace_seconds_per_km` (sec/km); `avg_heart_rate` / `max_heart_rate` (bpm). Weather fields come from `weather.json`: `temp_celsius` (°C), `relative_humidity_percent` (%), `wind_speed_kmh` (km/h), `wind_direction` (compass, e.g. N/NE/E). `gear_model` is the shoe/gear model name. `body_mass_kg` is the body mass at activity time, backfilled from `body_composition` (migration `phase0_power_prep`); `base_weight_kg` is the base/reference weight.

> **Common name traps** (the live schema differs from older drafts): it is `activity_date` (not `date`); `temp_celsius` (not `external_temp_c`); `relative_humidity_percent` (not `humidity`); `wind_speed_kmh` (not `wind_speed_ms`); `gear_model` (not `gear_name`). There are **no** `created_at`/`updated_at`, and **no** cadence/power/training-effect columns on this table — cadence/power live on `splits`, `time_series_metrics`, and the phase columns of `performance_trends`.

---

## 2. body_composition

**Purpose**: Weight and body composition measurements
**Primary Key**: `measurement_id` — with a **UNIQUE index on `date`** (`idx_body_composition_date`), so one row per day, enabling idempotent date-keyed upsert (`INSERT OR REPLACE`) on cache backfill.
**Source**: `data/raw/weight/YYYY-MM-DD.json`

### Schema

<!-- BEGIN GENERATED: schema:body_composition -->
| Column | Type |
|--------|------|
| measurement_id (PK) | INTEGER |
| date | DATE |
| weight_kg | DOUBLE |
| body_fat_percentage | DOUBLE |
| muscle_mass_kg | DOUBLE |
| bone_mass_kg | DOUBLE |
| bmi | DOUBLE |
| hydration_percentage | DOUBLE |
| measurement_source | VARCHAR |
<!-- END GENERATED: schema:body_composition -->

**Units & notes**: `date` carries a UNIQUE index (one row per day); `weight_kg` / `muscle_mass_kg` / `bone_mass_kg` in kg; `body_fat_percentage` / `hydration_percentage` in %; `bmi` is the body mass index; `measurement_source` is the device/source.

> 5 metabolic fields (basal/active metabolic rate, metabolic age, visceral fat rating, physique rating) were removed in v2.0 — the device does not provide them.

---

## 3. splits

**Purpose**: 1km lap/split-level performance data with environmental calculations
**Primary Key**: `(activity_id, split_index)`
**Source**: `data/raw/activity/{activity_id}/splits.json` (lapDTOs)

### Schema

<!-- BEGIN GENERATED: schema:splits -->
| Column | Type |
|--------|------|
| activity_id (PK) | BIGINT |
| split_index (PK) | INTEGER |
| distance | DOUBLE |
| duration_seconds | DOUBLE |
| start_time_gmt | VARCHAR |
| start_time_s | INTEGER |
| end_time_s | INTEGER |
| intensity_type | VARCHAR |
| role_phase | VARCHAR |
| pace_str | VARCHAR |
| pace_seconds_per_km | DOUBLE |
| heart_rate | INTEGER |
| hr_zone | VARCHAR |
| cadence | DOUBLE |
| cadence_rating | VARCHAR |
| power | DOUBLE |
| power_efficiency | VARCHAR |
| stride_length | DOUBLE |
| ground_contact_time | DOUBLE |
| vertical_oscillation | DOUBLE |
| vertical_ratio | DOUBLE |
| elevation_gain | DOUBLE |
| elevation_loss | DOUBLE |
| terrain_type | VARCHAR |
| environmental_conditions | VARCHAR |
| wind_impact | VARCHAR |
| temp_impact | VARCHAR |
| environmental_impact | VARCHAR |
| max_heart_rate | INTEGER |
| max_cadence | DOUBLE |
| max_power | DOUBLE |
| normalized_power | DOUBLE |
| average_speed | DOUBLE |
| grade_adjusted_speed | DOUBLE |
<!-- END GENERATED: schema:splits -->

**Sources** (raw lapDTO field → column): `activityId`→`activity_id`, `lapIndex`→`split_index`, `distance`→`distance` (m), `duration`→`duration_seconds` (s), `startTimeGMT`→`start_time_gmt`, `intensityType`→`intensity_type` (WARMUP/INTERVAL/RECOVERY/COOLDOWN/REST), `averageSpeed`→`pace_str`/`pace_seconds_per_km`/`average_speed`, `averageHR`→`heart_rate`, `averageRunCadence`→`cadence` (spm, both feet), `avgPower`→`power` (W), `strideLength`→`stride_length` (cm), `groundContactTime`→`ground_contact_time` (ms), `verticalOscillation`→`vertical_oscillation` (cm), `verticalRatio`→`vertical_ratio` (%), `elevationGain`/`elevationLoss`→`elevation_gain`/`elevation_loss` (m), `maxHR`→`max_heart_rate`, `maxRunCadence`→`max_cadence`, `maxPower`→`max_power`, `normPower`→`normalized_power`, `gradeAdjustedSpeed`→`grade_adjusted_speed` (m/s). `start_time_s` / `end_time_s` are computed offsets; `role_phase` is derived from split position.

**Calculated columns** (see Calculation Logic below): `hr_zone`, `cadence_rating`, `power_efficiency`, `terrain_type`, `environmental_conditions`, `wind_impact`, `temp_impact`, `environmental_impact`.

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

### Schema

<!-- BEGIN GENERATED: schema:time_series_metrics -->
| Column | Type |
|--------|------|
| activity_id (PK) | BIGINT |
| seq_no (PK) | INTEGER |
| timestamp_s | INTEGER |
| sum_moving_duration | DOUBLE |
| sum_duration | DOUBLE |
| sum_elapsed_duration | DOUBLE |
| sum_distance | DOUBLE |
| sum_accumulated_power | DOUBLE |
| heart_rate | DOUBLE |
| speed | DOUBLE |
| grade_adjusted_speed | DOUBLE |
| cadence | DOUBLE |
| cadence_single_foot | DOUBLE |
| cadence_total | DOUBLE |
| power | DOUBLE |
| ground_contact_time | DOUBLE |
| vertical_oscillation | DOUBLE |
| vertical_ratio | DOUBLE |
| stride_length | DOUBLE |
| vertical_speed | DOUBLE |
| elevation | DOUBLE |
| air_temperature | DOUBLE |
| latitude | DOUBLE |
| longitude | DOUBLE |
| available_stamina | DOUBLE |
| potential_stamina | DOUBLE |
| body_battery | DOUBLE |
| performance_condition | DOUBLE |
<!-- END GENERATED: schema:time_series_metrics -->

**Units & notes**: `timestamp_s` is a seconds offset; `sum_*` columns are cumulative (`sum_distance` in m); `heart_rate` (bpm); `speed` / `grade_adjusted_speed` / `vertical_speed` (m/s); `cadence` is both-feet cadence from `directDoubleCadence` (~180 spm, raw from Garmin API); `power` (W); `ground_contact_time` (ms); `vertical_oscillation` / `stride_length` (cm); `vertical_ratio` (%); `elevation` (m); `air_temperature` is **device** temperature (°C, +5–8°C body heat); `latitude` / `longitude` are GPS coordinates.

> There is a single `cadence` column. The legacy `cadence_single_foot` / `cadence_total` / `fractional_cadence` columns are **not present** (removed v2.1).

---

## 5. performance_trends

**Purpose**: Performance patterns and 4-phase workout analysis (warmup / run / recovery / cooldown)
**Primary Key**: `activity_id`
**Source**: Calculated from `splits.json`

### Schema

<!-- BEGIN GENERATED: schema:performance_trends -->
| Column | Type |
|--------|------|
| activity_id (PK) | BIGINT |
| pace_consistency | DOUBLE |
| hr_drift_percentage | DOUBLE |
| cadence_consistency | VARCHAR |
| fatigue_pattern | VARCHAR |
| warmup_splits | VARCHAR |
| warmup_avg_pace_seconds_per_km | DOUBLE |
| warmup_avg_pace_str | VARCHAR |
| warmup_avg_hr | DOUBLE |
| warmup_avg_cadence | DOUBLE |
| warmup_avg_power | DOUBLE |
| warmup_evaluation | VARCHAR |
| run_splits | VARCHAR |
| run_avg_pace_seconds_per_km | DOUBLE |
| run_avg_pace_str | VARCHAR |
| run_avg_hr | DOUBLE |
| run_avg_cadence | DOUBLE |
| run_avg_power | DOUBLE |
| run_evaluation | VARCHAR |
| recovery_splits | VARCHAR |
| recovery_avg_pace_seconds_per_km | DOUBLE |
| recovery_avg_pace_str | VARCHAR |
| recovery_avg_hr | DOUBLE |
| recovery_avg_cadence | DOUBLE |
| recovery_avg_power | DOUBLE |
| recovery_evaluation | VARCHAR |
| cooldown_splits | VARCHAR |
| cooldown_avg_pace_seconds_per_km | DOUBLE |
| cooldown_avg_pace_str | VARCHAR |
| cooldown_avg_hr | DOUBLE |
| cooldown_avg_cadence | DOUBLE |
| cooldown_avg_power | DOUBLE |
| cooldown_evaluation | VARCHAR |
<!-- END GENERATED: schema:performance_trends -->

**Units & notes**: `hr_drift_percentage` (%); `*_splits` columns are comma-separated split indices; `*_avg_pace_seconds_per_km` (sec/km); `*_avg_pace_str` (mm:ss); `*_avg_hr` / `*_avg_cadence` / `*_avg_power` are per-phase averages (power NULL when no power data). The four phase prefixes are `warmup` / `run` / `recovery` / `cooldown`, each with a `*_evaluation` quality string.

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

### Schema

<!-- BEGIN GENERATED: schema:form_efficiency -->
| Column | Type |
|--------|------|
| activity_id (PK) | BIGINT |
| gct_average | DOUBLE |
| gct_min | DOUBLE |
| gct_max | DOUBLE |
| gct_std | DOUBLE |
| gct_variability | DOUBLE |
| gct_rating | VARCHAR |
| gct_evaluation | VARCHAR |
| vo_average | DOUBLE |
| vo_min | DOUBLE |
| vo_max | DOUBLE |
| vo_std | DOUBLE |
| vo_trend | VARCHAR |
| vo_rating | VARCHAR |
| vo_evaluation | VARCHAR |
| vr_average | DOUBLE |
| vr_min | DOUBLE |
| vr_max | DOUBLE |
| vr_std | DOUBLE |
| vr_rating | VARCHAR |
| vr_evaluation | VARCHAR |
<!-- END GENERATED: schema:form_efficiency -->

**Units & notes**: per metric (`gct` in ms, `vo` in cm, `vr` in %) the table carries `*_average` / `*_min` / `*_max` / `*_std`, plus a `*_rating` (★) and `*_evaluation` text. `gct_variability` is `(std/avg)*100` (%); `vo_trend` is increasing/stable/decreasing.

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

### Schema

<!-- BEGIN GENERATED: schema:form_evaluations -->
| Column | Type |
|--------|------|
| eval_id (PK) | INTEGER |
| activity_id | BIGINT |
| gct_ms_expected | FLOAT |
| vo_cm_expected | FLOAT |
| vr_pct_expected | FLOAT |
| gct_ms_actual | FLOAT |
| vo_cm_actual | FLOAT |
| vr_pct_actual | FLOAT |
| gct_delta_pct | FLOAT |
| vo_delta_cm | FLOAT |
| vr_delta_pct | FLOAT |
| gct_penalty | FLOAT |
| gct_star_rating | VARCHAR |
| gct_score | FLOAT |
| gct_needs_improvement | BOOLEAN |
| gct_evaluation_text | VARCHAR |
| vo_penalty | FLOAT |
| vo_star_rating | VARCHAR |
| vo_score | FLOAT |
| vo_needs_improvement | BOOLEAN |
| vo_evaluation_text | VARCHAR |
| vr_penalty | FLOAT |
| vr_star_rating | VARCHAR |
| vr_score | FLOAT |
| vr_needs_improvement | BOOLEAN |
| vr_evaluation_text | VARCHAR |
| cadence_actual | FLOAT |
| cadence_minimum | INTEGER |
| cadence_achieved | BOOLEAN |
| cadence_expected | DOUBLE |
| cadence_delta_pct | DOUBLE |
| cadence_star_rating | VARCHAR |
| cadence_score | DOUBLE |
| cadence_needs_improvement | BOOLEAN |
| cadence_evaluation_text | VARCHAR |
| overall_score | FLOAT |
| overall_star_rating | VARCHAR |
| power_avg_w | FLOAT |
| power_wkg | FLOAT |
| speed_actual_mps | FLOAT |
| speed_expected_mps | FLOAT |
| power_efficiency_score | FLOAT |
| power_efficiency_rating | VARCHAR |
| power_efficiency_needs_improvement | BOOLEAN |
| integrated_score | FLOAT |
| training_mode | VARCHAR |
| evaluated_at | TIMESTAMP |
<!-- END GENERATED: schema:form_evaluations -->

**Units & notes**: `eval_id` is the surrogate PK; one row per `activity_id`. Per form metric (`gct`/`vo`/`vr`) the table carries `*_expected` and `*_actual` values (gct ms, vo cm, vr %), a deviation (`gct_delta_pct` / `vo_delta_cm` / `vr_delta_pct`), a `*_penalty`, `*_star_rating`, `*_score` (0–5.0), `*_needs_improvement` flag, and `*_evaluation_text` (Japanese). Cadence columns: `cadence_actual` / `cadence_minimum` / `cadence_achieved`, plus the migration-v6 set `cadence_expected` / `cadence_delta_pct` / `cadence_star_rating` / `cadence_score` / `cadence_needs_improvement` / `cadence_evaluation_text`. Power columns: `power_avg_w` (W), `power_wkg` (W/kg), `speed_actual_mps` / `speed_expected_mps` (m/s), `power_efficiency_score` / `power_efficiency_rating` / `power_efficiency_needs_improvement`. `overall_score` / `overall_star_rating` summarize form; `integrated_score` / `training_mode` are migration v3; `evaluated_at` is the evaluation timestamp.

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

### Schema

<!-- BEGIN GENERATED: schema:form_baseline_history -->
| Column | Type |
|--------|------|
| history_id (PK) | INTEGER |
| user_id | VARCHAR |
| condition_group | VARCHAR |
| metric | VARCHAR |
| model_type | VARCHAR |
| coef_alpha | FLOAT |
| coef_d | FLOAT |
| coef_a | FLOAT |
| coef_b | FLOAT |
| power_a | FLOAT |
| power_b | FLOAT |
| power_rmse | FLOAT |
| period_start | DATE |
| period_end | DATE |
| trained_at | TIMESTAMP |
| n_samples | INTEGER |
| rmse | FLOAT |
| speed_range_min | FLOAT |
| speed_range_max | FLOAT |
<!-- END GENERATED: schema:form_baseline_history -->

**Units & notes**: `user_id` defaults to `'default'`, `condition_group` to `'flat_road'`; `metric` is `gct` / `vo` / `vr`; `model_type` distinguishes power vs linear. GCT power-model coefficients `coef_alpha` (α, `log(v)` intercept) and `coef_d` (exponent, d < 0); VO/VR linear-model `coef_a` (intercept) and `coef_b` (slope). `period_start`/`period_end` bound the (inclusive) training window; `n_samples` is the sample count; `rmse` the error; `speed_range_min`/`speed_range_max` (m/s). `power_a`/`power_b` are the speed-from-power coefficients and `power_rmse` its error.

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

### Schema

<!-- BEGIN GENERATED: schema:hr_efficiency -->
| Column | Type |
|--------|------|
| activity_id (PK) | BIGINT |
| primary_zone | VARCHAR |
| zone_distribution_rating | VARCHAR |
| hr_stability | VARCHAR |
| aerobic_efficiency | VARCHAR |
| training_quality | VARCHAR |
| zone2_focus | BOOLEAN |
| zone4_threshold_work | BOOLEAN |
| training_type | VARCHAR |
| zone1_percentage | DOUBLE |
| zone2_percentage | DOUBLE |
| zone3_percentage | DOUBLE |
| zone4_percentage | DOUBLE |
| zone5_percentage | DOUBLE |
<!-- END GENERATED: schema:hr_efficiency -->

**Units & notes**: `primary_zone` is the zone with most time; `zone_distribution_rating` / `hr_stability` / `aerobic_efficiency` / `training_quality` are rating strings; `zone2_focus` / `zone4_threshold_work` are boolean indicators; `training_type` is aerobic_base/tempo/threshold/…; `zone1_percentage`…`zone5_percentage` are per-zone time (%).

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

### Schema

<!-- BEGIN GENERATED: schema:heart_rate_zones -->
| Column | Type |
|--------|------|
| activity_id (PK) | BIGINT |
| zone_number (PK) | INTEGER |
| zone_low_boundary | INTEGER |
| zone_high_boundary | INTEGER |
| time_in_zone_seconds | DOUBLE |
| zone_percentage | DOUBLE |
<!-- END GENERATED: schema:heart_rate_zones -->

**Units & notes**: `zone_number` 1–5; `zone_low_boundary` / `zone_high_boundary` (bpm); `time_in_zone_seconds` (s); `zone_percentage` (%).

---

## 11. vo2_max

**Purpose**: VO2 max estimates
**Primary Key**: `activity_id`
**Source**: VO2-max JSON

### Schema

<!-- BEGIN GENERATED: schema:vo2_max -->
| Column | Type |
|--------|------|
| activity_id (PK) | BIGINT |
| precise_value | DOUBLE |
| value | DOUBLE |
| date | DATE |
| category | INTEGER |
<!-- END GENERATED: schema:vo2_max -->

**Units & notes**: `precise_value` / `value` are precise vs rounded VO2 max (ml/kg/min); `category` is the fitness category (0–6).

> `fitness_age` removed in v2.0. Population ~78% — Garmin provides VO2 max only for certain activity types.

---

## 12. lactate_threshold

**Purpose**: Lactate-threshold and FTP estimates
**Primary Key**: `activity_id`
**Source**: Lactate-threshold JSON

### Schema

<!-- BEGIN GENERATED: schema:lactate_threshold -->
| Column | Type |
|--------|------|
| activity_id (PK) | BIGINT |
| heart_rate | INTEGER |
| speed_mps | DOUBLE |
| date_hr | TIMESTAMP |
| functional_threshold_power | INTEGER |
| power_to_weight | DOUBLE |
| weight | DOUBLE |
| date_power | TIMESTAMP |
<!-- END GENERATED: schema:lactate_threshold -->

**Units & notes**: `heart_rate` is the lactate-threshold HR (bpm); `speed_mps` (m/s); `date_hr` is the HR-threshold timestamp; `functional_threshold_power` is FTP (W); `power_to_weight` is FTP/weight (W/kg); `weight` (kg) at measurement; `date_power` is the FTP timestamp.

> Population ~52% — requires sufficient training history for Garmin to estimate.

---

## 13. training_plans

**Purpose**: Generated training-plan headers (backs `/plan-training`). Versioned — one plan_id can have multiple `version` rows.
**Primary Key**: logically `(plan_id, version)`; the live table declares no PK constraint (FK/PK constraints removed; uniqueness enforced by the writer).
**Source**: `save_training_plan` MCP tool / training-plan generator.

### Schema

<!-- BEGIN GENERATED: schema:training_plans -->
| Column | Type |
|--------|------|
| plan_id | VARCHAR |
| version | INTEGER |
| goal_type | VARCHAR |
| target_race_date | DATE |
| target_time_seconds | INTEGER |
| vdot | DOUBLE |
| pace_zones_json | VARCHAR |
| total_weeks | INTEGER |
| start_date | DATE |
| weekly_volume_start_km | DOUBLE |
| weekly_volume_peak_km | DOUBLE |
| runs_per_week | INTEGER |
| frequency_progression_json | VARCHAR |
| personalization_notes | VARCHAR |
| status | VARCHAR |
| created_at | TIMESTAMP |
<!-- END GENERATED: schema:training_plans -->

**Units & notes**: the live table declares **no PK constraint** (uniqueness `(plan_id, version)` enforced by the writer); `version` is the revision (migration `add_plan_versioning`). `target_time_seconds` (s); `vdot` is the fitness estimate; `pace_zones_json` / `frequency_progression_json` are JSON strings; `total_weeks` (weeks); `weekly_volume_start_km` / `weekly_volume_peak_km` (km); `status` is active/archived/….

---

## 14. planned_workouts

**Purpose**: Individual planned sessions belonging to a training plan; links plan → actual activity and tracks adherence.
**Primary Key**: `workout_id`
**Source**: Training-plan generator / Garmin upload flow.

### Schema

<!-- BEGIN GENERATED: schema:planned_workouts -->
| Column | Type |
|--------|------|
| workout_id (PK) | VARCHAR |
| plan_id | VARCHAR |
| version | INTEGER |
| week_number | INTEGER |
| day_of_week | INTEGER |
| workout_date | DATE |
| workout_type | VARCHAR |
| description_ja | VARCHAR |
| target_distance_km | DOUBLE |
| target_duration_minutes | DOUBLE |
| target_pace_low | DOUBLE |
| target_pace_high | DOUBLE |
| target_hr_low | INTEGER |
| target_hr_high | INTEGER |
| intervals_json | VARCHAR |
| phase | VARCHAR |
| garmin_workout_id | BIGINT |
| uploaded_at | TIMESTAMP |
| actual_activity_id | BIGINT |
| adherence_score | DOUBLE |
| completed_at | TIMESTAMP |
<!-- END GENERATED: schema:planned_workouts -->

**Units & notes**: `week_number` 1-based; `workout_type` is easy/tempo/interval/long/…; `description_ja` is the Japanese description; `target_distance_km` (km); `target_duration_minutes` (min); `target_pace_low` / `target_pace_high` (sec/km); `target_hr_low` / `target_hr_high` (bpm); `intervals_json` is the JSON interval structure; `phase` is base/build/peak/taper; `garmin_workout_id` is the uploaded ID; `actual_activity_id` links the matched executed activity; `adherence_score` is the plan-vs-actual score; `version` links the plan version (migration `add_plan_versioning`).

---

## 15. section_analyses

**Purpose**: Agent-generated analysis results (5 section types per analyzed activity)
**Primary Key**: `analysis_id` — with a **UNIQUE index on `(activity_id, section_type)`** (`idx_activity_section`), so re-analysis replaces rather than duplicates a section.
**Source**: Section-analysis agents (`unified-section-analyst`, `split-section-analyst`).

### Schema

<!-- BEGIN GENERATED: schema:section_analyses -->
| Column | Type |
|--------|------|
| analysis_id (PK) | INTEGER |
| activity_id | BIGINT |
| activity_date | DATE |
| section_type | VARCHAR |
| analysis_data | VARCHAR |
| created_at | TIMESTAMP |
| agent_name | VARCHAR |
| agent_version | VARCHAR |
<!-- END GENERATED: schema:section_analyses -->

**Units & notes**: `analysis_id` is the surrogate PK with a UNIQUE index on `(activity_id, section_type)`; `section_type` is split/phase/summary/efficiency/environment; `analysis_data` is the JSON payload (Japanese narrative + English keys); `agent_name` / `agent_version` identify the producing agent.

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

### Schema

<!-- BEGIN GENERATED: schema:athlete_profile -->
| Column | Type |
|--------|------|
| user_id (PK) | VARCHAR |
| current_focus | VARCHAR |
| focus_notes | VARCHAR |
| updated_at | TIMESTAMP |
<!-- END GENERATED: schema:athlete_profile -->

**Units & notes**: `current_focus` is the current training focus; `focus_notes` is rendered as `【見出し】` sections in the Web app.

---

## 17. athlete_goals

**Purpose**: Registered race goals (target races, priorities, target times)
**Primary Key**: `goal_id`
**Source**: `/set-goal`. Owned by migration `add_athlete_tables`.

### Schema

<!-- BEGIN GENERATED: schema:athlete_goals -->
| Column | Type |
|--------|------|
| goal_id (PK) | INTEGER |
| user_id | VARCHAR |
| race_name | VARCHAR |
| race_date | DATE |
| priority | VARCHAR |
| goal_type | VARCHAR |
| distance_km | DOUBLE |
| target_time_seconds | INTEGER |
| status | VARCHAR |
| notes | VARCHAR |
| created_at | TIMESTAMP |
| updated_at | TIMESTAMP |
<!-- END GENERATED: schema:athlete_goals -->

**Units & notes**: `priority` is A/B/C; `distance_km` (km); `target_time_seconds` (s); `notes` is free-form.

---

## 18. season_retrospectives

**Purpose**: Last-season retrospective narrative used as context by `/plan-training` and `/weekly-review`
**Primary Key**: `retro_id`
**Source**: `/set-goal`. Owned by migration `add_athlete_tables`.

### Schema

<!-- BEGIN GENERATED: schema:season_retrospectives -->
| Column | Type |
|--------|------|
| retro_id (PK) | INTEGER |
| user_id | VARCHAR |
| season_label | VARCHAR |
| period_start | DATE |
| period_end | DATE |
| narrative | VARCHAR |
| key_learnings | VARCHAR |
| created_at | TIMESTAMP |
<!-- END GENERATED: schema:season_retrospectives -->

**Units & notes**: `season_label` names the season; `period_start` / `period_end` bound it; `narrative` and `key_learnings` are free-form prose.

---

## 19. weekly_reviews

**Purpose**: Coach-perspective weekly training reviews (backs `/weekly-review`)
**Primary Key**: `review_id` — the former UNIQUE index was **dropped** (migration `drop_weekly_review_index`, version 8) to allow multiple revisions of the same week.
**Source**: `save_weekly_review` / `/weekly-review`. Owned by migration `add_athlete_tables`.

### Schema

<!-- BEGIN GENERATED: schema:weekly_reviews -->
| Column | Type |
|--------|------|
| review_id (PK) | INTEGER |
| user_id | VARCHAR |
| week_start_date | DATE |
| week_end_date | DATE |
| review_date | DATE |
| review_data | VARCHAR |
| created_at | TIMESTAMP |
| agent_name | VARCHAR |
| agent_version | VARCHAR |
<!-- END GENERATED: schema:weekly_reviews -->

**Units & notes**: `week_start_date` / `week_end_date` bound the reviewed week; `review_date` is when it was written; `review_data` is the JSON payload; `agent_name` / `agent_version` identify the producing agent. The former UNIQUE index was dropped (migration `drop_weekly_review_index`) to allow multiple revisions per week.

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
