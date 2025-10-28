# DuckDB Schema Mapping Specification

**Version**: 2.2
**Last Updated**: 2025-10-28
**Database**: `garmin_performance.duckdb`
**Total Tables**: 14

This document provides comprehensive schema documentation for all DuckDB tables in the Garmin performance analysis system.

## Change History

### Version 2.2 (2025-10-28)
- **Unified Form Evaluation System**: Added 3 new tables for pace-corrected form evaluation
  - `form_baselines`: Statistical model coefficients (power regression for GCT, linear for VO/VR)
  - `form_baseline_history`: 2-month rolling window baseline history for trend analysis
  - `form_evaluations`: Activity-level evaluation results with star ratings and needs_improvement flags
- **New MCP Tools**: `get_form_evaluations()`, `get_form_baseline_trend()`
- **Benefit**: Eliminates evaluation contradictions between agents, provides data-driven pace-corrected standards

### Version 2.1 (2025-10-24)
- **Cadence Column Cleanup**: Simplified time_series_metrics cadence columns
  - Removed 4 redundant cadence columns: `cadence` (old single-foot), `cadence_single_foot`, `cadence_total`, `fractional_cadence`
  - Kept single `cadence` column containing `directDoubleCadence` (both feet, directly from Garmin API)
  - Migration: 260,304 rows updated, backward-incompatible change
  - Reason: Eliminated confusion between single-foot (90 spm) and both-feet (180 spm) cadence values

### Version 2.0 (2025-10-20)
- **Schema Cleanup**: Removed 6 device-unprovided NULL fields
  - `vo2_max.fitness_age` (0% population)
  - `body_composition`: basal_metabolic_rate, active_metabolic_rate, metabolic_age, visceral_fat_rating, physique_rating (all 0%)
- **Phase 2 Enhancements**: Added 28 calculation fields across 4 tables
  - `splits`: 7 calculation fields (hr_zone, cadence_rating, power_efficiency, environmental_conditions, wind_impact, temp_impact, environmental_impact)
  - `form_efficiency`: 4 evaluation fields (gct_evaluation, vo_evaluation, vr_evaluation, vo_trend)
  - `hr_efficiency`: 6 evaluation fields (primary_zone, zone_distribution_rating, aerobic_efficiency, training_quality, zone2_focus, zone4_threshold_work)
  - `performance_trends`: 12 phase-based fields (warmup/run/recovery/cooldown × 3 fields each)

---

## Table of Contents

1. [activities](#1-activities) - Activity metadata
2. [splits](#2-splits) - 1km lap/split data
3. [time_series_metrics](#3-time_series_metrics) - Second-by-second metrics
4. [form_efficiency](#4-form_efficiency) - Running form metrics (GCT/VO/VR)
5. [form_baselines](#5-form_baselines) - Statistical model coefficients for pace-corrected evaluation
6. [form_baseline_history](#6-form_baseline_history) - 2-month rolling window baseline history
7. [form_evaluations](#7-form_evaluations) - Pace-corrected activity evaluation results
8. [hr_efficiency](#8-hr_efficiency) - Heart rate efficiency analysis
9. [heart_rate_zones](#9-heart_rate_zones) - HR zone boundaries and distribution
10. [performance_trends](#10-performance_trends) - Performance and fatigue patterns
11. [vo2_max](#11-vo2_max) - VO2 max estimates
12. [lactate_threshold](#12-lactate_threshold) - Lactate threshold data
13. [body_composition](#13-body_composition) - Weight and body metrics
14. [section_analyses](#14-section_analyses) - Agent analysis results

---

## 1. activities

**Purpose**: Core activity metadata and summary metrics

**Primary Key**: `activity_id`
**Row Count**: ~231 activities
**Source**: `data/raw/activity/{activity_id}/activity.json`

### Schema

| Column | Type | Nullable | Source | Description |
|--------|------|----------|--------|-------------|
| activity_id | BIGINT | NO | summaryDTO.activityId | Unique activity identifier |
| date | DATE | NO | summaryDTO.startTimeLocal | Activity date (YYYY-MM-DD) |
| activity_name | VARCHAR | YES | summaryDTO.activityName | Activity name/title |
| start_time_local | TIMESTAMP | YES | summaryDTO.startTimeLocal | Start time (local timezone) |
| start_time_gmt | TIMESTAMP | YES | summaryDTO.startTimeGMT | Start time (GMT) |
| total_time_seconds | INTEGER | YES | summaryDTO.duration | Total duration (seconds) |
| total_distance_km | DOUBLE | YES | summaryDTO.distance / 1000 | Total distance (km) |
| avg_pace_seconds_per_km | DOUBLE | YES | Calculated from distance/duration | Average pace (sec/km) |
| avg_heart_rate | INTEGER | YES | summaryDTO.averageHR | Average heart rate (bpm) |
| max_heart_rate | INTEGER | YES | summaryDTO.maxHR | Maximum heart rate (bpm) |
| avg_cadence | INTEGER | YES | summaryDTO.averageRunCadence | Average cadence (spm, total) |
| avg_power | INTEGER | YES | summaryDTO.avgPower | Average power (W) |
| normalized_power | INTEGER | YES | summaryDTO.normPower | Normalized power (W) |
| cadence_stability | DOUBLE | YES | Calculated | Cadence stability score |
| power_efficiency | DOUBLE | YES | Calculated | Power efficiency metric |
| pace_variability | DOUBLE | YES | Calculated | Pace variability coefficient |
| aerobic_te | DOUBLE | YES | summaryDTO.aerobicTrainingEffect | Aerobic training effect (0-5) |
| anaerobic_te | DOUBLE | YES | summaryDTO.anaerobicTrainingEffect | Anaerobic training effect (0-5) |
| training_effect_source | VARCHAR | YES | summaryDTO.trainingEffectLabel | Training type classification |
| power_to_weight | DOUBLE | YES | avg_power / weight_kg | Power-to-weight ratio (W/kg) |
| weight_kg | DOUBLE | YES | 7-day median | Weight (kg, statistical) |
| weight_source | VARCHAR | YES | Calculated | Weight data source |
| weight_method | VARCHAR | YES | Calculated | Weight calculation method |
| stability_score | DOUBLE | YES | Calculated | Overall stability metric |
| external_temp_c | DOUBLE | YES | weather.json temp | External temperature (°C) |
| external_temp_f | DOUBLE | YES | Calculated from temp_c | External temperature (°F) |
| humidity | INTEGER | YES | weather.json relativeHumidity | Relative humidity (%) |
| wind_speed_ms | DOUBLE | YES | weather.json windSpeed | Wind speed (m/s) |
| wind_direction_compass | VARCHAR | YES | weather.json windDirectionCompassPoint | Wind direction (N/NE/E/etc) |
| gear_name | VARCHAR | YES | summaryDTO.gear.displayName | Shoe/gear name |
| gear_type | VARCHAR | YES | summaryDTO.gear.gearTypeName | Gear type |
| created_at | TIMESTAMP | NO | CURRENT_TIMESTAMP | Record creation time |
| updated_at | TIMESTAMP | NO | CURRENT_TIMESTAMP | Record update time |
| total_elevation_gain | DOUBLE | YES | summaryDTO.elevationGain | Total elevation gain (m) |
| total_elevation_loss | DOUBLE | YES | summaryDTO.elevationLoss | Total elevation loss (m) |
| location_name | VARCHAR | YES | summaryDTO.locationName | Activity location |

**Population**: 100% for core fields (activity_id, date), 80-95% for optional metrics

---

## 2. splits

**Purpose**: 1km lap/split-level performance data with environmental calculations

**Primary Key**: `(activity_id, split_index)`
**Row Count**: ~2,016 splits (~9 splits/activity)
**Source**: `data/raw/activity/{activity_id}/splits.json` (lapDTOs)

### Schema

| Column | Type | Nullable | Source | Description |
|--------|------|----------|--------|-------------|
| activity_id | BIGINT | NO | activityId | Activity reference |
| split_index | INTEGER | NO | lapIndex | Split number (1-based) |
| distance | DOUBLE | YES | distance | Split distance (m) |
| duration_seconds | DOUBLE | YES | duration | Split duration (s) |
| start_time_gmt | VARCHAR | YES | startTimeGMT | Split start time |
| start_time_s | INTEGER | YES | Calculated from startLatitude timing | Split start offset (s) |
| end_time_s | INTEGER | YES | start_time_s + duration | Split end offset (s) |
| intensity_type | VARCHAR | YES | intensityType | Garmin intensity (warmup/active/recovery/cooldown/rest) |
| role_phase | VARCHAR | YES | Derived from position | Workout phase classification |
| pace_str | VARCHAR | YES | averageSpeed → mm:ss | Human-readable pace |
| pace_seconds_per_km | DOUBLE | YES | 1000 / averageSpeed | Pace (sec/km) |
| heart_rate | INTEGER | YES | averageHR | Average HR (bpm) |
| **hr_zone** | VARCHAR | YES | **CALCULATED** | **HR zone mapping (Zone1-5)** |
| cadence | DOUBLE | YES | averageRunCadence | Cadence (spm, total) |
| **cadence_rating** | VARCHAR | YES | **CALCULATED** | **Cadence quality (Excellent/Good/Fair/Low)** |
| power | DOUBLE | YES | avgPower | Average power (W) |
| **power_efficiency** | VARCHAR | YES | **CALCULATED** | **Power efficiency (Excellent/Good/Fair/Low)** |
| stride_length | DOUBLE | YES | strideLength | Stride length (cm) |
| ground_contact_time | DOUBLE | YES | groundContactTime | GCT (ms) |
| vertical_oscillation | DOUBLE | YES | verticalOscillation | VO (cm) |
| vertical_ratio | DOUBLE | YES | verticalRatio | VR (%) |
| elevation_gain | DOUBLE | YES | elevationGain | Elevation gain (m) |
| elevation_loss | DOUBLE | YES | elevationLoss | Elevation loss (m) |
| terrain_type | VARCHAR | YES | Calculated from elevation | Terrain classification |
| **environmental_conditions** | VARCHAR | YES | **CALCULATED** | **Weather summary** |
| **wind_impact** | VARCHAR | YES | **CALCULATED** | **Wind impact (None/Light/Moderate/Strong)** |
| **temp_impact** | VARCHAR | YES | **CALCULATED** | **Temperature impact (Ideal/Good/Slightly hot/etc)** |
| **environmental_impact** | VARCHAR | YES | **CALCULATED** | **Combined environmental impact** |

### Calculation Logic (7 fields)

#### hr_zone
Maps heart_rate to zone using heart_rate_zones boundaries:
- Zone 1: < zone2_low_boundary
- Zone 2: zone2_low ≤ HR < zone3_low
- Zone 3: zone3_low ≤ HR < zone4_low
- Zone 4: zone4_low ≤ HR < zone5_low
- Zone 5: ≥ zone5_low

#### cadence_rating
Based on total cadence (spm):
- Excellent: ≥190 spm
- Good: 180-189 spm
- Fair: 170-179 spm
- Low: <170 spm

#### power_efficiency
Based on W/kg ratio:
- Excellent: ≥4.0 W/kg
- Good: 3.0-3.9 W/kg
- Fair: 2.0-2.9 W/kg
- Low: <2.0 W/kg

#### environmental_conditions
Combines temperature, humidity, wind from weather.json:
- Example: "18.5°C, 65%, Wind: 3.2m/s NE"

#### wind_impact
Based on wind speed (m/s):
- None: <2.0
- Light: 2.0-4.9
- Moderate: 5.0-7.9
- Strong: ≥8.0

#### temp_impact
Training-type-aware temperature evaluation:
- Recovery: 15-22°C = Good (wider tolerance)
- Base Run: 10-18°C = Ideal, 18-23°C = Acceptable
- Tempo/Threshold: 8-15°C = Ideal, 15-20°C = Good, 20-25°C = Slightly hot
- Interval/Sprint: 8-15°C = Ideal, 20-23°C = Slightly hot, >23°C = Dangerous

#### environmental_impact
Combines wind + temperature impacts:
- Negligible: Both None/Ideal
- Low: Light wind or Good temp
- Moderate: Moderate wind or Slightly hot
- High: Strong wind or Hot/Dangerous

**Population**: 100% for core fields, 99.75% for stride_length, 100% for max metrics, 39.8% for power metrics

### MCP Tools for Splits Data

**Comprehensive Tool (Recommended):**
- `mcp__garmin-db__get_splits_comprehensive(activity_id, statistics_only=True/False)`
  - **Fields**: 12 fields (pace, HR, GCT, VO, VR, power, stride_length, cadence, elevation_gain/loss, max_HR, max_cadence)
  - **Token Optimization**: 67% reduction with `statistics_only=True`
  - **Use Case**: Complete split analysis in one call

**Lightweight Tools (Backward Compatible):**
- `mcp__garmin-db__get_splits_pace_hr()` - 4 fields (pace, HR, max_HR, distance)
- `mcp__garmin-db__get_splits_form_metrics()` - 4 fields (GCT, VO, VR, split_index)
- `mcp__garmin-db__get_splits_elevation()` - 5 fields (elevation_gain/loss, terrain_type, split_index, distance)

---

## 3. time_series_metrics

**Purpose**: Second-by-second detailed metrics (26 fields)

**Primary Key**: `(activity_id, seq_no)`
**Row Count**: ~260,304 rows (~1,126 rows/activity)
**Source**: `data/raw/activity/{activity_id}/metrics.json`

### Schema

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| activity_id | BIGINT | NO | Activity reference |
| seq_no | INTEGER | NO | Sequence number |
| timestamp_s | INTEGER | NO | Timestamp offset (seconds) |
| sum_moving_duration | DOUBLE | YES | Cumulative moving duration |
| sum_duration | DOUBLE | YES | Cumulative total duration |
| sum_elapsed_duration | DOUBLE | YES | Cumulative elapsed duration |
| sum_distance | DOUBLE | YES | Cumulative distance (m) |
| sum_accumulated_power | DOUBLE | YES | Cumulative power |
| heart_rate | DOUBLE | YES | Instantaneous HR (bpm) |
| speed | DOUBLE | YES | Instantaneous speed (m/s) |
| grade_adjusted_speed | DOUBLE | YES | Grade-adjusted speed (m/s) |
| cadence | DOUBLE | YES | Both feet cadence from directDoubleCadence (~180 spm, raw from Garmin API) |
| power | DOUBLE | YES | Instantaneous power (W) |
| ground_contact_time | DOUBLE | YES | GCT (ms) |
| vertical_oscillation | DOUBLE | YES | VO (cm) |
| vertical_ratio | DOUBLE | YES | VR (%) |
| stride_length | DOUBLE | YES | Stride length (cm) |
| vertical_speed | DOUBLE | YES | Vertical speed (m/s) |
| elevation | DOUBLE | YES | Elevation (m) |
| air_temperature | DOUBLE | YES | Device temperature (°C, +5-8°C body heat) |
| latitude | DOUBLE | YES | GPS latitude |
| longitude | DOUBLE | YES | GPS longitude |
| available_stamina | DOUBLE | YES | Available stamina |
| potential_stamina | DOUBLE | YES | Potential stamina |
| body_battery | DOUBLE | YES | Body battery level |
| performance_condition | DOUBLE | YES | Performance condition |

**Population**: 100% for timestamp/distance, 95-99% for HR/speed/cadence, 30-40% for power metrics

---

## 4. form_efficiency

**Purpose**: Running form efficiency summary (GCT/VO/VR)

**Primary Key**: `activity_id`
**Row Count**: ~231 activities
**Source**: Aggregated from splits.json (lapDTOs)

### Schema

| Column | Type | Nullable | Source | Description |
|--------|------|----------|--------|-------------|
| activity_id | BIGINT | NO | - | Activity reference |
| gct_average | DOUBLE | YES | AVG(groundContactTime) | Average GCT (ms) |
| gct_min | DOUBLE | YES | MIN(groundContactTime) | Minimum GCT (ms) |
| gct_max | DOUBLE | YES | MAX(groundContactTime) | Maximum GCT (ms) |
| gct_std | DOUBLE | YES | STDDEV(groundContactTime) | GCT standard deviation |
| gct_variability | DOUBLE | YES | (std/avg) * 100 | GCT variability (%) |
| gct_rating | VARCHAR | YES | Calculated | GCT quality rating (★) |
| **gct_evaluation** | VARCHAR | YES | **CALCULATED** | **GCT quality evaluation** |
| vo_average | DOUBLE | YES | AVG(verticalOscillation) | Average VO (cm) |
| vo_min | DOUBLE | YES | MIN(verticalOscillation) | Minimum VO (cm) |
| vo_max | DOUBLE | YES | MAX(verticalOscillation) | Maximum VO (cm) |
| vo_std | DOUBLE | YES | STDDEV(verticalOscillation) | VO standard deviation |
| **vo_trend** | VARCHAR | YES | **CALCULATED** | **VO trend analysis (increasing/stable/decreasing)** |
| vo_rating | VARCHAR | YES | Calculated | VO quality rating (★) |
| **vo_evaluation** | VARCHAR | YES | **CALCULATED** | **VO quality evaluation** |
| vr_average | DOUBLE | YES | AVG(verticalRatio) | Average VR (%) |
| vr_min | DOUBLE | YES | MIN(verticalRatio) | Minimum VR (%) |
| vr_max | DOUBLE | YES | MAX(verticalRatio) | Maximum VR (%) |
| vr_std | DOUBLE | YES | STDDEV(verticalRatio) | VR standard deviation |
| vr_rating | VARCHAR | YES | Calculated | VR quality rating (★) |
| **vr_evaluation** | VARCHAR | YES | **CALCULATED** | **VR quality evaluation** |

### Calculation Logic (4 fields)

#### gct_evaluation
Based on gct_average (ms):
- Excellent: <200ms
- Good: 200-250ms
- Fair: 250-300ms
- Poor: >300ms

#### vo_evaluation
Based on vo_average (cm):
- Excellent: <7cm
- Good: 7-10cm
- Fair: 10-12cm
- Poor: >12cm

#### vr_evaluation
Based on vr_average (%):
- Excellent: <7%
- Good: 7-8%
- Fair: 8-10%
- Poor: >10%

#### vo_trend
Analyzes VO changes across splits:
- Increasing: VO worsens >5% from start to end
- Stable: VO changes ≤5%
- Decreasing: VO improves >5% from start to end

**Population**: 100% for all fields (aggregated from splits)

---

## 5. form_baselines

**Purpose**: Statistical model coefficients for pace-corrected form expectations

**Primary Key**: `baseline_id`
**Unique Key**: `(user_id, condition_group, metric)`
**Row Count**: 3 rows (GCT, VO, VR)
**Source**: Trained from splits data using `tools/scripts/train_form_baselines.py`

### Schema

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| baseline_id | INTEGER | NO | Unique baseline ID |
| user_id | VARCHAR | NO | User identifier (default: 'default') |
| condition_group | VARCHAR | NO | Terrain group (default: 'flat_road') |
| metric | VARCHAR | NO | Metric name ('gct', 'vo', 'vr') |
| coef_alpha | DOUBLE | YES | GCT: log(v) intercept (α in v = c * (GCT)^d) |
| coef_d | DOUBLE | YES | GCT: power exponent (d < 0, monotonic) |
| coef_a | DOUBLE | YES | VO/VR: intercept (a in y = a + b * v) |
| coef_b | DOUBLE | YES | VO/VR: slope (b) |
| rmse | DOUBLE | YES | Root mean squared error |
| n_samples | INTEGER | YES | Number of training samples |
| speed_range_min | DOUBLE | YES | Minimum speed (m/s) |
| speed_range_max | DOUBLE | YES | Maximum speed (m/s) |
| trained_at | TIMESTAMP | NO | Training timestamp |

### Model Types

**GCT (Ground Contact Time):**
- Model: Power regression `v = exp((log(GCT) - α) / d)`
- Constraint: d < 0 (ensures monotonicity: faster pace → shorter GCT)
- Training: Huber regression with outlier removal (IQR method)

**VO (Vertical Oscillation) and VR (Vertical Ratio):**
- Model: Linear regression `y = a + b * v`
- Training: Huber regression with outlier removal (IQR method)

### Training Script

```bash
# Train baselines from all data
uv run python tools/scripts/train_form_baselines.py \
  --db-path /path/to/garmin_performance.duckdb \
  --verbose

# Train monthly with 2-month rolling window
uv run python tools/scripts/train_form_baselines_monthly.py \
  --year-month 2025-10 \
  --db-path /path/to/garmin_performance.duckdb
```

**Population**: 100% (3 metrics, manually trained)

---

## 6. form_baseline_history

**Purpose**: 2-month rolling window baseline history for trend analysis

**Primary Key**: `history_id`
**Unique Key**: `(user_id, condition_group, metric, period_start, period_end)`
**Row Count**: Variable (weekly updates × 3 metrics)
**Source**: `tools/scripts/train_form_baselines_monthly.py`

### Schema

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| history_id | INTEGER | NO | Unique history ID |
| user_id | VARCHAR | NO | User identifier |
| condition_group | VARCHAR | NO | Terrain group |
| metric | VARCHAR | NO | Metric name ('gct', 'vo', 'vr') |
| period_start | DATE | NO | Training period start date |
| period_end | DATE | NO | Training period end date (inclusive) |
| coef_d | DOUBLE | YES | GCT: power exponent (for trend analysis) |
| coef_b | DOUBLE | YES | VO/VR: slope (for trend analysis) |
| n_samples | INTEGER | YES | Number of training samples in window |
| trained_at | TIMESTAMP | NO | Training timestamp |

### Usage in Trend Analysis

The `get_form_baseline_trend(activity_id, activity_date)` MCP tool:
1. Retrieves current period baseline (activity_date within period_start/period_end)
2. Retrieves 1-month-ago baseline (activity_date - 1 month within period_start/period_end)
3. Calculates deltas: Δd (GCT), Δb (VO/VR)
4. Interprets trends:
   - GCT: Negative Δd = improvement (shorter GCT at same pace)
   - VO/VR: Negative Δb = improvement (less bounce at same pace)

**Population**: Variable (depends on monthly training schedule)

---

## 7. form_evaluations

**Purpose**: Pace-corrected activity evaluation results with star ratings

**Primary Key**: `eval_id`
**Unique Key**: `activity_id`
**Row Count**: 224 activities (96.9% of activities)
**Source**: Generated by `workflow_planner` using `tools/form_baseline/evaluator.py`

### Schema

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| eval_id | INTEGER | NO | Unique evaluation ID |
| activity_id | BIGINT | NO | Activity reference (unique) |
| gct_ms_expected | DOUBLE | YES | Expected GCT from pace (ms) |
| vo_cm_expected | DOUBLE | YES | Expected VO from pace (cm) |
| vr_pct_expected | DOUBLE | YES | Expected VR from pace (%) |
| gct_ms_actual | DOUBLE | YES | Actual GCT (ms) |
| vo_cm_actual | DOUBLE | YES | Actual VO (cm) |
| vr_pct_actual | DOUBLE | YES | Actual VR (%) |
| gct_delta_pct | DOUBLE | YES | GCT deviation (%) |
| vo_delta_cm | DOUBLE | YES | VO deviation (cm) |
| vr_delta_pct | DOUBLE | YES | VR deviation (%) |
| gct_penalty | DOUBLE | YES | GCT penalty score (0-100) |
| gct_star_rating | VARCHAR | YES | GCT rating (★★★★★ ~ ★☆☆☆☆) |
| gct_score | DOUBLE | YES | GCT score (0-5.0) |
| gct_needs_improvement | BOOLEAN | YES | GCT needs improvement flag |
| gct_evaluation_text | TEXT | YES | GCT evaluation text (Japanese) |
| vo_penalty | DOUBLE | YES | VO penalty score (0-100) |
| vo_star_rating | VARCHAR | YES | VO rating (★★★★★ ~ ★☆☆☆☆) |
| vo_score | DOUBLE | YES | VO score (0-5.0) |
| vo_needs_improvement | BOOLEAN | YES | VO needs improvement flag |
| vo_evaluation_text | TEXT | YES | VO evaluation text (Japanese) |
| vr_penalty | DOUBLE | YES | VR penalty score (0-100) |
| vr_star_rating | VARCHAR | YES | VR rating (★★★★★ ~ ★☆☆☆☆) |
| vr_score | DOUBLE | YES | VR score (0-5.0) |
| vr_needs_improvement | BOOLEAN | YES | VR needs improvement flag |
| vr_evaluation_text | TEXT | YES | VR evaluation text (Japanese) |
| cadence_actual | DOUBLE | YES | Actual cadence (spm) |
| cadence_minimum | DOUBLE | YES | Minimum cadence threshold (180 spm) |
| cadence_achieved | BOOLEAN | YES | Cadence achievement flag |
| overall_score | DOUBLE | YES | Overall form score (0-5.0) |
| overall_star_rating | VARCHAR | YES | Overall rating (★★★★★ ~ ★☆☆☆☆) |
| evaluated_at | TIMESTAMP | NO | Evaluation timestamp |

### Evaluation Logic

**Score Calculation:**
- Base score: 100 (perfect)
- Penalty: Based on deviation from expected value
  - Ideal range: ±2% → 0 penalty (★★★★★ 5.0)
  - Good range: 2-5% → 0-30 penalty (★★★★☆ 4.0)
  - Fair range: 5-10% → 30-60 penalty (★★★☆☆ 3.0)
  - Poor range: >10% → 60-90 penalty (★★☆☆☆ 2.0 or ★☆☆☆☆ 1.0)
- Score: (100 - penalty) / 20

**needs_improvement Flag:**
- `true` if deviation > 5% from expected value
- `false` if within ideal/good range

**Overall Score:**
- Average of GCT, VO, VR scores
- Weighted slightly toward GCT (most important metric)

### MCP Tool

`get_form_evaluations(activity_id)` returns:
```json
{
  "gct": {
    "expected_ms": 260.1,
    "actual_ms": 258.3,
    "delta_pct": -0.7,
    "score": 5.0,
    "star_rating": "★★★★★",
    "needs_improvement": false,
    "evaluation_text": "258msは期待値260ms±2%の理想範囲内です..."
  },
  "vo": { ... },
  "vr": { ... },
  "overall_score": 4.3,
  "overall_star_rating": "★★★★☆",
  "cadence_actual": 181.27,
  "cadence_achieved": true
}
```

**Population**: 96.9% (requires form_baselines to be trained)

---

## 8. hr_efficiency

**Purpose**: Heart rate efficiency and training quality analysis

**Primary Key**: `activity_id`
**Row Count**: ~231 activities
**Source**: `hr_zones.json`, `activity.json`

### Schema

| Column | Type | Nullable | Source | Description |
|--------|------|----------|--------|-------------|
| activity_id | BIGINT | NO | - | Activity reference |
| **primary_zone** | VARCHAR | YES | **CALCULATED** | **Zone with most time** |
| **zone_distribution_rating** | VARCHAR | YES | **CALCULATED** | **Distribution quality** |
| hr_stability | VARCHAR | YES | Calculated | HR stability rating |
| **aerobic_efficiency** | VARCHAR | YES | **CALCULATED** | **Aerobic efficiency rating** |
| **training_quality** | VARCHAR | YES | **CALCULATED** | **Overall training quality** |
| **zone2_focus** | BOOLEAN | YES | **CALCULATED** | **Zone 2 focus indicator** |
| **zone4_threshold_work** | BOOLEAN | YES | **CALCULATED** | **Zone 4+ threshold work** |
| training_type | VARCHAR | YES | trainingEffectLabel | Training type (aerobic_base, tempo, threshold, etc) |
| zone1_percentage | DOUBLE | YES | Calculated | Zone 1 time (%) |
| zone2_percentage | DOUBLE | YES | Calculated | Zone 2 time (%) |
| zone3_percentage | DOUBLE | YES | Calculated | Zone 3 time (%) |
| zone4_percentage | DOUBLE | YES | Calculated | Zone 4 time (%) |
| zone5_percentage | DOUBLE | YES | Calculated | Zone 5 time (%) |

### Calculation Logic (6 fields)

#### primary_zone
Zone with maximum time_in_zone_seconds

#### zone_distribution_rating
Training-type-aware rating:
- Recovery: Z1+Z2 ≥80% = Excellent
- Base Run: Z2 ≥60% = Excellent
- Tempo: Z3+Z4 ≥50% = Excellent
- Threshold: Z4 ≥40% = Excellent
- Interval: Z4+Z5 ≥60% = Excellent

#### aerobic_efficiency
Based on Z1+Z2 percentage:
- Excellent: ≥80%
- Good: 60-79%
- Fair: 40-59%
- Poor: <40%

#### training_quality
Combines zone_distribution_rating + primary_zone + training_type:
- Excellent: Distribution Excellent + primary zone matches target
- Good: Distribution Good or Fair with acceptable primary zone
- Needs Improvement: Poor distribution or mismatched zones

#### zone2_focus
True if zone2_percentage ≥50%

#### zone4_threshold_work
True if (zone4_percentage + zone5_percentage) ≥20%

**Population**: 100% for all fields (calculated from heart_rate_zones)

---

## 9. heart_rate_zones

**Purpose**: HR zone boundaries and time distribution

**Primary Key**: `(activity_id, zone_number)`
**Row Count**: ~1,155 rows (5 zones × 231 activities)
**Source**: `hr_zones.json`

### Schema

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| activity_id | BIGINT | NO | Activity reference |
| zone_number | INTEGER | NO | Zone number (1-5) |
| zone_low_boundary | INTEGER | YES | Zone lower HR boundary (bpm) |
| zone_high_boundary | INTEGER | YES | Zone upper HR boundary (bpm, calculated) |
| time_in_zone_seconds | DOUBLE | YES | Time spent in zone (s) |
| zone_percentage | DOUBLE | YES | Time in zone (%) |

**Population**: 100% (5 zones per activity)

---

## 10. performance_trends

**Purpose**: Performance patterns and 4-phase workout analysis

**Primary Key**: `activity_id`
**Row Count**: ~231 activities
**Source**: Calculated from splits.json

### Schema

| Column | Type | Nullable | Source | Description |
|--------|------|----------|--------|-------------|
| activity_id | BIGINT | NO | - | Activity reference |
| pace_consistency | DOUBLE | YES | Calculated | Pace consistency score |
| hr_drift_percentage | DOUBLE | YES | (last_hr - first_hr) / first_hr | HR drift (%) |
| cadence_consistency | VARCHAR | YES | Calculated | Cadence consistency rating |
| fatigue_pattern | VARCHAR | YES | Calculated | Fatigue pattern classification |
| warmup_splits | VARCHAR | YES | Comma-separated | Warmup split indices |
| warmup_avg_pace_seconds_per_km | DOUBLE | YES | AVG(pace) | Warmup avg pace |
| warmup_avg_pace_str | VARCHAR | YES | mm:ss | Warmup pace string |
| warmup_avg_hr | DOUBLE | YES | AVG(HR) | Warmup avg HR |
| **warmup_avg_cadence** | DOUBLE | YES | **CALCULATED** | **Warmup avg cadence** |
| **warmup_avg_power** | DOUBLE | YES | **CALCULATED** | **Warmup avg power** |
| **warmup_evaluation** | VARCHAR | YES | **CALCULATED** | **Warmup quality evaluation** |
| run_splits | VARCHAR | YES | Comma-separated | Run split indices |
| run_avg_pace_seconds_per_km | DOUBLE | YES | AVG(pace) | Run avg pace |
| run_avg_pace_str | VARCHAR | YES | mm:ss | Run pace string |
| run_avg_hr | DOUBLE | YES | AVG(HR) | Run avg HR |
| **run_avg_cadence** | DOUBLE | YES | **CALCULATED** | **Run avg cadence** |
| **run_avg_power** | DOUBLE | YES | **CALCULATED** | **Run avg power** |
| **run_evaluation** | VARCHAR | YES | **CALCULATED** | **Run quality evaluation** |
| recovery_splits | VARCHAR | YES | Comma-separated | Recovery split indices |
| recovery_avg_pace_seconds_per_km | DOUBLE | YES | AVG(pace) | Recovery avg pace |
| recovery_avg_pace_str | VARCHAR | YES | mm:ss | Recovery pace string |
| recovery_avg_hr | DOUBLE | YES | AVG(HR) | Recovery avg HR |
| **recovery_avg_cadence** | DOUBLE | YES | **CALCULATED** | **Recovery avg cadence** |
| **recovery_avg_power** | DOUBLE | YES | **CALCULATED** | **Recovery avg power** |
| **recovery_evaluation** | VARCHAR | YES | **CALCULATED** | **Recovery quality evaluation** |
| cooldown_splits | VARCHAR | YES | Comma-separated | Cooldown split indices |
| cooldown_avg_pace_seconds_per_km | DOUBLE | YES | AVG(pace) | Cooldown avg pace |
| cooldown_avg_pace_str | VARCHAR | YES | mm:ss | Cooldown pace string |
| cooldown_avg_hr | DOUBLE | YES | AVG(HR) | Cooldown avg HR |
| **cooldown_avg_cadence** | DOUBLE | YES | **CALCULATED** | **Cooldown avg cadence** |
| **cooldown_avg_power** | DOUBLE | YES | **CALCULATED** | **Cooldown avg power** |
| **cooldown_evaluation** | VARCHAR | YES | **CALCULATED** | **Cooldown quality evaluation** |

### Calculation Logic (12 fields)

#### Phase Detection
Based on splits.intensity_type:
- Warmup: intensity_type = 'warmup'
- Run: intensity_type = 'active' (main workout)
- Recovery: intensity_type = 'recovery'
- Cooldown: intensity_type = 'cooldown'

#### warmup_avg_cadence / run_avg_cadence / recovery_avg_cadence / cooldown_avg_cadence
Average of split cadence values within each phase

#### warmup_avg_power / run_avg_power / recovery_avg_power / cooldown_avg_power
Average of split power values within each phase (NULL if no power data)

#### warmup_evaluation
- Excellent: Gradual pace increase, HR rises steadily
- Good: Adequate warmup duration (>5 min)
- Needs Improvement: Too short (<3 min) or missing

#### run_evaluation
Training-type-aware:
- Excellent: Pace consistent (CV <5%), HR stable
- Good: Acceptable consistency (CV 5-10%)
- Needs Improvement: High variability (CV >10%)

#### recovery_evaluation
- Excellent: HR drops ≥20 bpm from run phase, cadence drops ≥10 spm
- Good: HR drops 10-19 bpm
- Needs Improvement: Insufficient recovery (HR drop <10 bpm)

#### cooldown_evaluation
- Excellent: Gradual pace decrease, HR lowers steadily
- Good: Adequate cooldown duration (>5 min)
- Needs Improvement: Too short (<3 min) or missing

**Population**: 100% for core fields, 80-95% for phase-specific fields (depends on workout structure)

---

## 11. vo2_max

**Purpose**: VO2 max estimates

**Primary Key**: `activity_id`
**Row Count**: ~180 activities (78% population)
**Source**: `vo2_max.json`

### Schema

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| activity_id | BIGINT | NO | Activity reference |
| precise_value | DOUBLE | YES | Precise VO2 max (ml/kg/min) |
| value | DOUBLE | YES | Rounded VO2 max (ml/kg/min) |
| date | DATE | YES | Measurement date |
| category | INTEGER | YES | Fitness category (0-6) |

**Note**: `fitness_age` field removed in v2.0 (device does not provide this data)

**Population**: 78% (Garmin provides VO2 max only for certain activity types)

---

## 12. lactate_threshold

**Purpose**: Lactate threshold estimates

**Primary Key**: `activity_id`
**Row Count**: ~120 activities (52% population)
**Source**: `lactate_threshold.json`

### Schema

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| activity_id | BIGINT | NO | Activity reference |
| heart_rate | INTEGER | YES | Lactate threshold HR (bpm) |
| speed_mps | DOUBLE | YES | Lactate threshold speed (m/s) |
| date_hr | TIMESTAMP | YES | HR threshold measurement date |
| functional_threshold_power | INTEGER | YES | FTP (W) |
| power_to_weight | DOUBLE | YES | FTP / weight (W/kg) |
| weight | DOUBLE | YES | Weight at measurement (kg) |
| date_power | TIMESTAMP | YES | FTP measurement date |

**Population**: 52% (requires sufficient training history for Garmin to estimate)

---

## 13. body_composition

**Purpose**: Weight and body composition measurements

**Primary Key**: `measurement_id`
**Row Count**: Variable (daily measurements)
**Source**: `data/raw/weight/YYYY-MM-DD.json`

### Schema

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| measurement_id | INTEGER | NO | Unique measurement ID |
| date | DATE | NO | Measurement date |
| weight_kg | DOUBLE | YES | Weight (kg) |
| body_fat_percentage | DOUBLE | YES | Body fat (%) |
| muscle_mass_kg | DOUBLE | YES | Muscle mass (kg) |
| bone_mass_kg | DOUBLE | YES | Bone mass (kg) |
| bmi | DOUBLE | YES | Body mass index |
| hydration_percentage | DOUBLE | YES | Hydration (%) |
| measurement_source | VARCHAR | YES | Measurement device |

**Note**: 5 metabolic fields removed in v2.0 (device does not provide this data):
- basal_metabolic_rate
- active_metabolic_rate
- metabolic_age
- visceral_fat_rating
- physique_rating

**Population**: Varies by measurement availability (scale usage)

---

## 14. section_analyses

**Purpose**: Agent-generated analysis results (5 types per activity)

**Primary Key**: `analysis_id`
**Row Count**: ~1,155 rows (5 analyses × 231 activities)
**Source**: Generated by section analysis agents

### Schema

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| analysis_id | INTEGER | NO | Unique analysis ID |
| activity_id | BIGINT | NO | Activity reference |
| activity_date | DATE | NO | Activity date |
| section_type | VARCHAR | NO | Analysis type (split/phase/summary/efficiency/environment) |
| analysis_data | VARCHAR | YES | JSON analysis results |
| created_at | TIMESTAMP | NO | Analysis creation timestamp |
| agent_name | VARCHAR | YES | Agent identifier |
| agent_version | VARCHAR | YES | Agent version |

### Section Types

1. **split**: 1km split analysis (pace, HR, form)
2. **phase**: Phase evaluation (warmup/run/cooldown, training-type-aware)
3. **summary**: Activity type classification + overall assessment
4. **efficiency**: Form (GCT/VO/VR) + HR efficiency
5. **environment**: Environmental impact analysis (weather, terrain)

**Population**: 100% (5 analyses per activity, auto-generated)

---

## Summary Statistics

| Table | Row Count | Primary Key Type | Foreign Keys | Population |
|-------|-----------|------------------|--------------|------------|
| activities | 231 | activity_id | - | 100% (core) |
| splits | 2,016 | (activity_id, split_index) | activities | 100% |
| time_series_metrics | 250,186 | (activity_id, timestamp_s) | activities | 100% |
| form_efficiency | 231 | activity_id | activities | 100% |
| form_baselines | 3 | baseline_id | - | 100% (manually trained) |
| form_baseline_history | Variable | history_id | - | Variable (weekly) |
| form_evaluations | 224 | eval_id (unique: activity_id) | activities | 96.9% |
| hr_efficiency | 231 | activity_id | activities | 100% |
| heart_rate_zones | 1,155 | (activity_id, zone_number) | activities | 100% |
| performance_trends | 231 | activity_id | activities | 100% |
| vo2_max | 180 | activity_id | activities | 78% |
| lactate_threshold | 120 | activity_id | activities | 52% |
| body_composition | Variable | measurement_id | - | Variable |
| section_analyses | 1,155 | analysis_id | activities | 100% |

**Total Database Size**: ~670 MB
**Total Tables**: 14
**Total Activities**: 231

---

## Data Pipeline

```
Raw Data (API)
    ↓
data/raw/activity/{id}/
    ├── activity.json         → activities, hr_efficiency
    ├── splits.json           → splits, form_efficiency, performance_trends
    ├── hr_zones.json         → heart_rate_zones, hr_efficiency
    ├── vo2_max.json          → vo2_max
    ├── lactate_threshold.json → lactate_threshold
    ├── weather.json          → activities (weather fields)
    └── metrics.json          → time_series_metrics
    ↓
DuckDB Inserters
    ├── activities.py
    ├── splits.py (7 calculation fields)
    ├── time_series_metrics.py
    ├── form_efficiency.py (4 evaluation fields)
    ├── hr_efficiency.py (6 evaluation fields)
    ├── heart_rate_zones.py
    ├── performance_trends.py (12 phase fields)
    ├── vo2_max.py
    ├── lactate_threshold.py
    └── body_composition.py
    ↓
garmin_performance.duckdb (14 tables)
    ↓
Form Baseline System (NEW)
    ├── train_form_baselines.py → form_baselines (3 metrics)
    ├── train_form_baselines_monthly.py → form_baseline_history (weekly)
    └── evaluator.py → form_evaluations (per activity)
    ↓
MCP Tools (70-98.8% token reduction)
    ├── get_form_evaluations(activity_id)
    ├── get_form_baseline_trend(activity_id, activity_date)
    └── ... (existing tools)
    ↓
Analysis Agents (5 types)
    ├── efficiency-section-analyst (uses get_form_evaluations, get_form_baseline_trend)
    ├── summary-section-analyst (uses needs_improvement flags)
    └── ... (other agents)
    ↓
Markdown Reports (Japanese)
```

---

## Maintenance Notes

### Schema Migration
Use `tools/scripts/regenerate_duckdb.py` for schema changes:
```bash
# Single table
uv run python tools/scripts/regenerate_duckdb.py --tables splits

# Multiple tables with date range
uv run python tools/scripts/regenerate_duckdb.py \
  --tables splits form_efficiency hr_efficiency performance_trends \
  --start-date 2025-10-01 --end-date 2025-10-31
```

### Backup Policy
- Create timestamped backups before schema changes
- Store in `data/database/backups/`
- Verify backup integrity with read-only connection

### Testing Requirements
- All tests must use mocked data (no production DB access)
- Use `@pytest.fixture` for test data
- Integration tests: `pytest-mock` for DuckDB connections
- Performance tests: Real data OK, skip if unavailable

---

**End of Schema Documentation**
