# MCP Tools Reference

Auto-generated from the `ToolDef` registry (`garmin_mcp.tools.ALL_DEFS`) — **74 tools** (72 domain + 2 server). Do not edit by hand.

Regenerate with:

```bash
uv run --directory packages/garmin-mcp-server \
  python -m garmin_mcp.scripts.generate_tool_reference
```

Tools are callable as MCP tools (`mcp__garmin-db__<name>`) and, for domain tools, via the reloadless `garmin-db` CLI. Return shapes are not captured by the registry — call a tool (or read its handler) for the response structure.

## Contents

- [Export](#export) (1)
- [Metadata](#metadata) (3)
- [Splits](#splits) (2)
- [Analysis](#analysis) (9)
- [Physiology](#physiology) (13)
- [Performance](#performance) (4)
- [Time Series](#time-series) (4)
- [Training Plan](#training-plan) (2)
- [Athlete](#athlete) (10)
- [Race](#race) (1)
- [Training Load](#training-load) (4)
- [Durability](#durability) (3)
- [strength](#strength) (2)
- [ingest](#ingest) (2)
- [Workout Scheduling](#workout-scheduling) (3)
- [hiking](#hiking) (2)
- [Training Plan Ledger](#training-plan-ledger) (6)
- [gear](#gear) (1)
- [Server](#server) (2)

## Export

### `export`

CLI: `garmin-db export run`

Run a read-only DuckDB SELECT and write the result to a local parquet or CSV file instead of returning rows. Returns handle (the file path under /tmp/garmin_exports, deleted after 1 hour), rows, columns, size_mb and expires_at (UTC ISO 8601), or error (with a suggestion when rows exceed max_rows). Use it for multi-activity analysis read back in Python. An empty result writes no file and returns rows=0 with handle and expires_at null.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | **required** | A single DuckDB SELECT, wrapped as a subquery, so no trailing semicolon |
| `format` | enum: `parquet`, `csv` | optional (default `parquet`) | parquet (default) or csv with a header row |
| `max_rows` | integer | optional (default `100000`) | Refuse the export when the result has more rows than this (default: 100000) |

## Metadata

### `get_activity_by_date`

CLI: `garmin-db metadata activity-by-date`

Resolve a local date to the ingested run(s) on that day. With exactly one run, returns success=true plus activity_id, activity_name, start_time (local), distance_km, duration_seconds and gear (gear_type, gear_model, gear_nickname, gear_label). With none or several, returns success=false, an error and an activities list with the same fields to pick from. Only runs already ingested into DuckDB are found; ingest_activity fetches a new day.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `date` | string | **required** | Local calendar date of the run, YYYY-MM-DD |

### `get_date_by_activity_id`

CLI: `garmin-db metadata date-by-activity-id`

Look up the local activity date of an ingested activity. Returns {activity_id, date} with date as YYYY-MM-DD, or date=null when the ID is not in DuckDB. It returns no name, distance or metrics; get_activity_by_date gives those for a date.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** | Garmin activity ID to look up |

### `ingest_activity`

CLI: `garmin-db metadata ingest`

Ingest the one run on date from Garmin Connect (raw files are cache-first), write it to DuckDB and run the pace-corrected form evaluation. Returns {success: true, activity_id, date, form_evaluation_status} where form_evaluation_status is success, model_not_found, failed or error; returns {success: false, error} when the day has no run or several. Use catch_up_ingest for a date range and get_activity_by_date to read a run that is already ingested.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `date` | string | **required** | Activity date in YYYY-MM-DD format |

## Splits

### `get_splits_elevation`

CLI: `garmin-db splits elevation`

Per-lap elevation for one activity from the splits table (Garmin laps: auto 1 km, or workout/manual laps). Full mode returns splits[] with split_number, elevation_gain_m, elevation_loss_m and terrain_type (平坦/起伏/丘陵/山岳). statistics_only returns metrics.elevation_gain / elevation_loss as {mean, median, std, min, max} in metres, without terrain_type. get_splits_comprehensive carries the same gain/loss; this tool adds the terrain class.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** | Garmin activity ID (resolve one from a date with get_activity_by_date) |
| `statistics_only` | boolean | optional (default `False`) | If true, return only aggregated statistics (mean, median, std, min, max) for elevation gain/loss instead of per-split data. Default: false |

### `get_splits_comprehensive`

CLI: `garmin-db splits comprehensive`

Per-lap data for one activity from the splits table (Garmin laps: auto 1 km, or workout/manual laps). Full mode returns splits[]: split_number, distance_km, pace (s/km), HR and max HR, GCT (ms), VO (cm), VR (%), power (W), stride (cm), cadence and max cadence (spm), elevation gain/loss (m), intensity_type and role_phase; _warnings flags laps without form metrics. To judge a single run, start from get_run_report; use this for lap-level detail it does not carry.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** | Garmin activity ID (resolve one from a date with get_activity_by_date) |
| `statistics_only` | boolean | optional (default `False`) | If true, return only {mean, median, std, min, max} per metric (12 metrics) over all laps instead of per-lap rows: unweighted, the short final lap included, and a metric with no data reads 0.0. Default: false |

## Analysis

### `insert_section_analysis_dict`

CLI: `garmin-db analysis insert-section`

Append one section_analyses row (activity_id, activity_date, section_type, analysis_data) verbatim to DuckDB as a new version (fresh run_id); readers treat the latest version as canonical and prior versions are kept. Does NOT run the run_note schema or grounding gate - the normal path is validate_section_json then merge_section_analyses via the analyze-activity workflow. Use only for manual repair.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** | Garmin activity ID (resolve one from a date with get_activity_by_date) |
| `activity_date` | string | **required** | Activity date, YYYY-MM-DD |
| `section_type` | string | **required** | Section type of the row, e.g. run_note |
| `analysis_data` | object | **required** | The section's analysis_data object, stored as given |

### `validate_section_json`

CLI: `garmin-db analysis validate-section`

Validate a run_note coach review against its Pydantic schema. Returns {valid: bool, errors: list[str]}. Only section_type run_note is accepted. This checks the schema only: the grounding gate (every evidence key must resolve against the run report) runs at merge, so valid: true does not mean the merge will accept it.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `section_type` | enum: `run_note` | **required** | Section type to validate |
| `analysis_data` | object | **required** | The analysis_data object to check against the section schema |

### `get_analysis_contract`

CLI: `garmin-db analysis contract`

Get the analysis contract for the run_note coach review (output schema, evidence keys, writing criterion). The analyst calls this for the up-to-date criterion.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `section_type` | enum: `run_note` | **required** | Section type |

### `find_unanalyzed_activities`

CLI: `garmin-db analysis find-unanalyzed`

Find running activities without an analysis in a date range. An activity counts as analysed when it has a run_note row or the complete legacy section set. Returns [{activity_id, date, section_count}] for the rest, where section_count is the distinct legacy section count, ordered by date ascending. Used to backfill analysis history for catch-up-ingested days.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | string | **required** | Start date (inclusive) in YYYY-MM-DD format |
| `end_date` | string | **required** | End date (inclusive) in YYYY-MM-DD format |
| `required_sections` | integer | optional (default `5`) | Legacy section count considered complete (default 5) |

### `analyze_performance_trends`

CLI: `garmin-db analysis performance-trends`

Linear trend of one metric across the activity_ids dated within start_date..end_date (omit activity_ids to use every run in the window): each activity contributes the unweighted mean of the metric over its laps, regressed on elapsed days. Returns metric, trend, slope (metric units per day), correlation, p_value, data_points, start_date, end_date. trend is stable when p>0.05 and insufficient_data under 3 points. Otherwise pace, ground_contact_time, vertical_oscillation and vertical_ratio (lower is better) read improving / declining, while heart_rate, power, cadence and elevation_gain, which are not comparable across runs at different paces, read only increasing / decreasing.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `metric` | string | **required** | pace (s/km), heart_rate, cadence, power, vertical_oscillation, ground_contact_time, vertical_ratio or elevation_gain (mean per-lap gain); any other value returns an error listing these |
| `start_date` | string | **required** | Inclusive start (YYYY-MM-DD); activities dated earlier are dropped |
| `end_date` | string | **required** | Inclusive end (YYYY-MM-DD); activities dated later are dropped |
| `activity_ids` | array[integer] | optional | Activities to consider; only those dated in the window are used. Omit to use every run dated in the window |
| `temperature_range` | array[number] | optional | Keep only activities whose weather-station temperature (°C) is within [min, max]; runs without weather are dropped |
| `distance_range` | array[number] | optional | Keep only activities whose total distance (km) is within [min, max] |

### `get_heat_adjusted_trend`

CLI: `garmin-db analysis heat-adjusted-trend`

Climate-neutral HR-at-pace trend: fits HR ~ pace + max(temp - ref_temp_c, 0) + days on whole-run averages (HR, pace, weather-station temperature) of the activity_ids dated within start_date..end_date. Returns status, coefficients (beta_heat = bpm per °C above ref, n, r_squared), neutral_hr_slope (bpm/day) with its p_value, and points[] {date, temp_c, raw_hr, heat_cost, neutral_hr}. Needs 10 complete runs, else status=insufficient_data. Workout types are mixed.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | string | **required** | Inclusive start (YYYY-MM-DD); runs dated earlier are dropped |
| `end_date` | string | **required** | Inclusive end (YYYY-MM-DD); runs dated later are dropped |
| `activity_ids` | array[integer] | **required** | Activities to fit on; only those dated in the window with HR, pace and temperature are used |
| `ref_temp_c` | number | optional | Hinge reference temperature in Celsius (default 15) |

### `compare_similar_workouts`

CLI: `garmin-db analysis compare-workouts`

Find earlier activities whose whole-run average pace and total distance are within tolerance of the target, ordered by pace closeness then recency. Only runs that started before the target are candidates (an earlier date, or the same date with an earlier start), so an old run is never compared with later ones. Returns target_activity and similar_activities[] with training_type, temperature and its diff, similarity_score (0-100: pace 45%, distance 35%, training type 20%), pace_diff (s/km) and hr_diff (bpm) as candidate minus target, and a Japanese interpretation.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** | Garmin activity ID of the target run (resolve one from a date with get_activity_by_date) |
| `pace_tolerance` | number | optional | Allowed fractional difference from the target's average pace in s/km (default 0.2 = ±20%) |
| `distance_tolerance` | number | optional | Distance tolerance as fraction (default 0.2 = ±20%) |
| `activity_type_filter` | string | optional | Substring matched against activity_name (SQL LIKE), not a workout type |
| `date_range` | array[string] | optional | Optional [start, end] (YYYY-MM-DD, inclusive) limiting candidates |
| `limit` | integer | optional | Maximum number of results (default 10) |

### `get_run_report`

CLI: `garmin-db analysis run-report`

Get the deterministic report for one run: everything the single-run page and the run note are built from, in one call. Returns activity_id, activity_date, intensity_category, purpose ({id, label_ja, source}: what the run was for -- declared on the prescription, the session_type default, inferred from the run's own data, or unknown; hedge an inferred one), headline (plan_label, flag_count, flag_labels -- adverse signals plus the label_ja of concern moments), plan (verdict ✅/🟡/🔴 against the day's prescription, its title, per-axis checks with target/actual/on_plan -- plus a strides axis (target/actual as reps, status on_plan/short/missing, verdict ✅/🟡/🔴) when the prescription carries strides -- and hr_ceiling {bpm, seconds_over, pct_over}; with a time series the ceiling row, seconds_over and pct_over cover steady running only -- stops, auto-pause resumes, bursts and stride/recovery laps are left out together with the HR recovery after each, detected from the HR trace (back to the pre-event baseline, a new plateau, or 180 s at most); without one the zone totals stand; null when the day had no prescription), judged_share ({hr, form}: the share of the run's time the ceiling and the form signals were judged on, null without a time series), signals (per metric: today, expected, the athlete's own normal_low/normal_high, z, status within/edge/outside/insufficient, adverse, streak, n, reason; form signals are insufficient with reason low_judged_share when less than half of the run was steady running), zones (HR zone percentages), moments (2-5 deterministic turning points, each with a label_ja and a unit of km or step, real positions km_from/km_to + t_from_s/t_to_s, facts, and policy {verdict, reason} judging the scene against the purpose: concern (a deviation from what the run was for -- the only moments a growth point may rest on), acceptable (expected or allowed, e.g. a walk break on an aerobic long run) or neutral (descriptive; step scenes are always neutral); a block of strides and their jogs is one strides moment with facts reps, fastest_pace_s_per_km, median_pace_s_per_km, median_cadence_spm, peak_hr and hr_at_next_start per rep), flow (the series the chart draws: axis distance/time, total_km, total_s, segments, steps and the fragment count), recurrence (moment kinds that keep happening at the same point of the run), phases (warmup/run/recovery/cooldown pace and HR), conditions (temp_c, humidity_pct, wind_mps, terrain, elevation_gain_m), vs_previous (delta chips against the previous same-family run), next_run_target (what the next run of this kind should look like) and next_session (what the athlete actually does next: date, days_ahead, session_type, title, target_km/target_minutes, hr_low/hr_high and whether it came from the plan, the long-run ladder or a projection). Returns null when the activity does not exist.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** | Activity ID to build the deterministic run report for. |

### `get_run_note_inputs`

CLI: `garmin-db analysis run-note-inputs`

Get everything the run-note (coach review) agent writes from, in one call: report (exactly get_run_report) and context (the coach subset of prefetch_activity_context: training_type, week_position, prescription_for_run {title, session_type, target_km, target_minutes, hr_low, hr_high, rationale}, morning_wellness, vs_previous, previous_same_type, the top 3 similar_workouts, gear and long_run_gate; null when the bundle failed). Returns {error, activity_id} when the activity has no run report.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** | Activity ID to build the deterministic run report for. |

## Physiology

### `get_form_efficiency_summary`

CLI: `garmin-db physiology form-efficiency`

Get raw form metric statistics (GCT, VO, VR averages, min/max, std) from the form_efficiency table. NOT AUTHORITATIVE for judging form: the star ratings here are absolute bands with no pace term, so the same runner reads worse at slow paces purely because ground contact and vertical ratio scale with speed. Use get_form_evaluations for the pace-corrected verdict, and get_form_baseline_trend for longitudinal comparison.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** | Garmin activity ID (resolve one from a date with get_activity_by_date) |

### `get_form_evaluations`

CLI: `garmin-db physiology form-evaluations`

Pace-corrected form inputs for one activity: for GCT (ms), VO (cm), VR (%) and cadence (spm), the actual value, the value expected at that pace from the athlete's own baseline, the delta, a star score and evaluation text; power efficiency (W, W/kg, actual vs expected speed, a self-baseline label); integrated_score, training_mode and overall score/stars. Null when not evaluated. Stars are legacy display values; judge a run with get_run_report.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** | Garmin activity ID (resolve one from a date with get_activity_by_date) |

### `get_form_baseline_trend`

CLI: `garmin-db physiology form-baseline-trend`

Compare the athlete's form-baseline model coefficients for the period containing activity_date with the period one month earlier. Returns success and metrics keyed gct/vo/vr/cadence/power, each with current and previous {coef_d, coef_b, power_a, power_b, period} and deltas (delta_d/delta_b for the pace models, delta_power_a/delta_power_b for power). success=false with an error when either period has no baseline.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** | Garmin activity ID; echoed only (the lookup uses activity_date) |
| `activity_date` | string | **required** | Date (YYYY-MM-DD) whose baseline period is compared with the one a month earlier |
| `user_id` | string | optional (default `default`) | Baseline owner (default: 'default') |
| `condition_group` | string | optional (default `flat_road`) | Baseline condition group (default: 'flat_road', the group the baseline scripts train) |

### `get_hr_efficiency_analysis`

CLI: `garmin-db physiology hr-efficiency`

HR-zone summary for one activity, computed at ingest from Garmin's native zone times: zone_percentages zone1-zone5 (% of time), primary_zone, training_type (Garmin training-effect label, lowercased), rule-based labels zone_distribution_rating, hr_stability, aerobic_efficiency and training_quality, and flags zone2_focus (>60% Z2) and zone4_threshold_work (>20% Z4-5). Null when missing. Zone boundaries: get_heart_rate_zones_detail.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** | Garmin activity ID (resolve one from a date with get_activity_by_date) |

### `get_heart_rate_zones_detail`

CLI: `garmin-db physiology heart-rate-zones`

Garmin native heart-rate zones recorded with one activity: zones[] with zone_number 1-5, low_boundary and high_boundary (bpm), time_in_zone_seconds and zone_percentage. Boundaries are the zone settings in force for that run; high_boundary is the next zone's low minus 1, and null for zone 5, which has no upper bound. Null when missing.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** | Garmin activity ID (resolve one from a date with get_activity_by_date) |

### `get_vo2_max_data`

CLI: `garmin-db physiology vo2-max`

Garmin's running VO2max estimate for one activity: precise_value and rounded value (ml/kg/min) and date (Garmin calendar date of the estimate). When the activity has no row, falls back to the latest estimate dated on or before the activity. Null when none exists.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** | Garmin activity ID (resolve one from a date with get_activity_by_date) |

### `get_lactate_threshold_data`

CLI: `garmin-db physiology lactate-threshold`

Garmin's lactate-threshold values fetched with one activity: heart_rate (bpm), speed_mps (m/s), date_hr (when Garmin last updated the HR/speed threshold), functional_threshold_power (W), power_to_weight (W/kg), weight and date_power. Null when that activity has no row; there is no fallback to other activities. These are Garmin's auto-estimates as of the fetch.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** | Garmin activity ID (resolve one from a date with get_activity_by_date) |

### `get_body_composition_trend`

CLI: `garmin-db physiology body-composition-trend`

Get the body-composition trend over the trailing window (default 12 weeks). Decomposes the weight change between the first and last measurement into fat-mass and lean-mass components. Returns weeks, a date-ascending series ([{date, weight_kg, fat_mass, lean_mass}]; fat_mass/lean_mass null when body fat unrecorded), a change block (delta_weight, delta_fat, delta_lean, lean_loss_ratio, muscle_loss_warning -- true when >40% of the lost weight is lean mass, flagging leg-durability/injury risk), and lean_pwr (lean-mass power-to-weight = latest functional_threshold_power / lean mass; null when body fat or FTP is missing).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `weeks` | integer | optional (default `12`) | Trailing window length in weeks to analyze (default: 12). |

### `get_weight_economy_coupling`

CLI: `garmin-db physiology weight-economy-coupling`

Couple easy runs (default training_type=aerobic_base) with body weight and fit a longitudinal running-economy model over the trailing window (default 52 weeks). Joins each easy run to its nearest body_composition weight (within max_gap_days, default 14) and derives the efficiency factor EF = avg_speed_ms / avg_heart_rate, then fits EF ~ weight + days (+ VO2max fitness) by OLS. Returns weeks, n_runs_total, n_matched, weight_spread_kg, a model block (weight/days/fitness coefficients with p-values and VIF, R^2, delta_ef_per_5kg_loss effect size, collinearity_flag, note) reported as an association rather than a clean causal coefficient, a date-ascending series ([{activity_id, run_date, weight_kg, ef, weight_gap_days}]), and a note. When too few runs match for the regression, model is null and a reason string is included (no error raised).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `weeks` | integer | optional (default `52`) | Trailing window length in weeks to analyze (default: 52). |
| `max_gap_days` | integer | optional (default `14`) | Maximum allowed absolute day gap between a run and the nearest body-composition weight measurement for the join (default: 14). |

### `get_recovery_trend`

CLI: `garmin-db physiology recovery-trend`

Get the RHR / HRV recovery trend over the trailing window (default 8 weeks) from daily_wellness. Returns weeks, an rhr block (median_7d, median_30d, rhr_trend -- 'improving' when the 7-day median is >=2 bpm below the 30-day median, 'fatigued' when >=3 bpm above, else 'stable'), an hrv block (latest_ms, status, hrv_below_baseline_days, under_recovery -- true when >=2 consecutive nights are below HRV baseline; AND this with a high get_acwr to flag over-training), and a date-ascending series ([{date, resting_hr, hrv_overnight_ms}]). Medians / HRV fields are null when data is missing (device-off days are skipped).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `weeks` | integer | optional (default `8`) | Trailing window length in weeks to analyze (default: 8). |

### `get_recovery_status`

CLI: `garmin-db physiology recovery-status`

Get today's morning go/no-go recovery status from daily_wellness (defaults to the latest day; pass date=YYYY-MM-DD for a specific day). Synthesizes Training Readiness, Body Battery and sleep score with the HRV under_recovery flag into a recommendation: 'rest' / 'easy' when readiness<50 or sleep<50 or HRV is under-recovered (>=2 nights below baseline), 'quality' (tempo allowed) when readiness>=75 and HRV is normal, else 'moderate'. Device-off days (no readiness and no sleep) return recommendation='unknown' with a 'go by feel' reason. Returns date, recommendation, score (mean of available markers), reasons, and the raw training_readiness, body_battery_high, sleep_score, sleep_seconds (how long the night lasted, as opposed to how good it was; all null-safe).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `date` | string | optional | Target day as YYYY-MM-DD. Omit to use the latest day in daily_wellness. |

### `get_wellness_baseline_deviation`

CLI: `garmin-db physiology wellness-baseline`

Judge today's HRV / Training Readiness / resting HR against the athlete's own rolling personal baseline band (mean +/- SD over the trailing window, default 30 days) from daily_wellness -- a per-individual early warning, not an absolute threshold (defaults to the latest day; pass date=YYYY-MM-DD for a specific day). Returns date, an hrv / readiness / rhr block each with mean, std, today, z=(today-mean)/std, flag ('low' when z<-1, 'high' when z>+1, else 'within'; 'insufficient' with null stats when <7 non-null samples), adverse (true in the unfavorable direction -- low HRV/readiness or high RHR), and n, plus overall_flag (true when any metric is in an adverse deviation). All fields are null-safe (device-off days are skipped).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `date` | string | optional | Target day as YYYY-MM-DD. Omit to use the latest day in daily_wellness. |
| `window_days` | integer | optional (default `30`) | Trailing window length in days used to build the personal baseline band (today excluded; default 30). |

### `get_long_run_recovery_cost`

CLI: `garmin-db physiology long-run-recovery-cost`

Judge what one run cost over the following two mornings: joins the activity to the daily_wellness rows of d+1 / d+2 and compares them with the athlete's own trailing 14-day median (run day excluded). Three criteria: 'rhr_two_day' (resting HR >=+2 bpm over baseline on BOTH mornings -- a single elevated morning is the normal price of a long run; with no d+2 row it needs >=+3 on d+1 alone), 'readiness' (d+1 Training Readiness <35) and 'hrv' (d+1 overnight HRV <=-15% vs baseline). cost_flag is true when >=2 of the 3 fire -- one lone marker is noise. Returns activity_id, activity_date, distance_km, avg_heart_rate, temperature_c, baseline (rhr_median, hrv_median, n), d1 (rhr, rhr_delta, hrv, hrv_delta_pct, readiness, sleep_hours, body_battery_low), d2 (rhr, rhr_delta), criteria [{name, fired, value, threshold}], criteria_fired, cost_flag, insufficient_data (missing d+1 row or <5 baseline RHR samples -- cost_flag is then false) and a short Japanese reason_ja. Returns null for an unknown activity. No distance floor is applied; the thresholds were backtested on runs >=15 km, where the rule fires on the two 2026 injury-trigger long runs and on none of the ladder long runs.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** | Activity ID of the run whose next-morning cost to judge. |

## Performance

### `get_performance_trends`

CLI: `garmin-db performance trends`

Within-run pacing summary for one activity: pace_consistency (coefficient of variation of representative run-lap paces, a fraction), hr_drift_percentage (half-vs-half decoupling for steady runs, rep-matched drift for intervals) and avg_pace (s/km) / avg_hr per phase (warmup, run, cooldown, plus recovery for intervals). Null when missing. get_activity_durability gives the time-series decoupling.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** | Garmin activity ID (resolve one from a date with get_activity_by_date) |

### `get_weather_data`

CLI: `garmin-db performance weather`

Weather for one activity from Garmin's activity weather record (an external weather station's observation near the start time), not the watch's body-warmed temperature sensor. Returns temperature_c, temperature_f, humidity (%), wind_speed_ms and wind_direction (compass point). One snapshot per run; fields are null when Garmin had no weather, and the result is null for an unknown activity.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** | Garmin activity ID (resolve one from a date with get_activity_by_date) |

### `prefetch_activity_context`

CLI: `garmin-db performance prefetch-context`

Pre-fetch the context a run report does not carry, in a single call: training_type, the shoe worn (gear), similar_workouts (earlier runs only), the long_run_gate verdict (runs >= 10 km) and the prescription vs actual layer (that day's prescription, week_position, previous_same_type + vs_previous and morning_wellness). The run itself (plan vs actual and its verdict, signals, scenes, conditions) is get_run_report; weather, HR zones and form have their own tools. Auto-generates the form baseline for the activity's month (and prior month) if missing.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** | Garmin activity ID (resolve one from a date with get_activity_by_date) |

### `get_objective_fitness_curve`

CLI: `garmin-db performance objective-fitness-curve`

Objective (non-optimistic) fitness curve: rolling 90-day max best-effort performance VDOT from splits, side-by-side with Garmin VO2max and the optimism gap. Returns objective_curve [{date, vdot, source_distance_km}] ascending by run day (best contiguous 2 / 5 / 10 km efforts), garmin_vo2max [{date, value}] ascending, and optimism_gap {garmin_vdot, objective_vdot, gap_vdot, gap_speed_mps, gap_pace_sec_per_km}, or null when either series is empty. get_race_readiness reads the latest objective VDOT per distance bucket from this curve.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `window_days` | integer | optional (default `90`) | Rolling window in days for the best-effort maximum (default 90) |

## Time Series

### `get_split_time_series_detail`

CLI: `garmin-db time-series split-detail`

Sample-level data for one lap (split_number as in get_splits_comprehensive; laps are auto 1 km or workout/manual laps) from time_series_metrics. Returns time_range, metrics, statistics {mean, std, min, max} and, unless statistics_only, time_series. With detect_anomalies, anomalies[] {timestamp_s, metric, value, z_score} lists samples in this lap whose absolute z against the whole-activity mean and std exceeds z_threshold, in either direction.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** | Garmin activity ID (resolve one from a date with get_activity_by_date) |
| `split_number` | integer | **required** | Lap number (1-based), as split_number in get_splits_comprehensive |
| `metrics` | array[string] | optional | time_series_metrics column names, e.g. heart_rate, speed (m/s), cadence (spm, both feet), power, ground_contact_time, vertical_oscillation, vertical_ratio, stride_length, elevation, grade_adjusted_speed, air_temperature (device sensor); default: heart_rate, speed, cadence, power, vertical_oscillation, ground_contact_time, vertical_ratio. Unknown names return an error |
| `statistics_only` | boolean | optional | If true, return only statistics {mean, std, min, max} per metric, without time_series. Default: false |
| `detect_anomalies` | boolean | optional | If true, add anomalies[] for this lap (z versus the whole-activity mean/std). Default: false |
| `z_threshold` | number | optional | Absolute z above which a sample is an anomaly. Default: 2.0 |

### `get_time_range_detail`

CLI: `garmin-db time-series time-range-detail`

Recorded samples of chosen metrics for one activity between start_time_s and end_time_s (elapsed seconds, end exclusive), from time_series_metrics. Returns time_range, metrics, statistics {mean, std, min, max} per metric and, unless statistics_only, time_series [{timestamp_s, metric: value}]. Long runs are recorded about every 2 s, so rows are not per second. A metric with no data reads 0.0 in statistics.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** | Garmin activity ID (resolve one from a date with get_activity_by_date) |
| `start_time_s` | integer | **required** | Inclusive start, seconds elapsed since the activity start |
| `end_time_s` | integer | **required** | Exclusive end, seconds elapsed since the activity start |
| `metrics` | array[string] | optional | time_series_metrics column names, e.g. heart_rate, speed (m/s), cadence (spm, both feet), power, ground_contact_time, vertical_oscillation, vertical_ratio, stride_length, elevation, grade_adjusted_speed, air_temperature (device sensor); default: heart_rate, speed, cadence, power, vertical_oscillation, ground_contact_time, vertical_ratio. Unknown names return an error |
| `statistics_only` | boolean | optional | If true, only return statistics (mean, std, min, max) without time series data. Default: false |

### `detect_form_anomalies_summary`

CLI: `garmin-db time-series anomalies-summary`

Scan one activity's raw activity_details samples for sustained form deterioration: a sample counts when its z against a rolling 60-sample baseline exceeds z_threshold in the worse (higher) direction, passes a magnitude gate (GCT 10 ms, VO 0.5 cm, VR 0.3 %) and lasts 5 s. Returns anomalies_detected, counts per metric and per cause (elevation_change/pace_change/fatigue/isolated), severity bands, 5-minute clusters, the top 5 and Japanese recommendations.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** | Garmin activity ID (resolve one from a date with get_activity_by_date) |
| `metrics` | array[string] | optional | Garmin descriptor keys directGroundContactTime, directVerticalOscillation, directVerticalRatio (the default) or the short names GCT / VO / VR, case-insensitive. Unknown names return an error |
| `z_threshold` | number | optional | Minimum z versus the rolling baseline (default: 3.0) |

### `get_form_anomaly_details`

CLI: `garmin-db time-series anomaly-details`

Full records for the anomalies detect_form_anomalies_summary counts, after filters. Each has anomaly_id, timestamp (elapsed s), metric, value, baseline (rolling mean), z_score, probable_cause (elevation_change/pace_change/fatigue/isolated), cause_details and 30 s before/after context. Returns total_anomalies, returned_anomalies and anomalies ordered by sort_by (absolute z_score descending, or timestamp ascending), capped by limit.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** | Garmin activity ID (resolve one from a date with get_activity_by_date) |
| `anomaly_ids` | array[integer] | optional | anomaly_id values from an earlier call with the same metrics and z_threshold |
| `time_range` | array[integer] | optional | [start, end] elapsed seconds, inclusive |
| `metrics` | array[string] | optional | Form metrics to detect and return: descriptor keys directGroundContactTime, directVerticalOscillation, directVerticalRatio (the default) or GCT / VO / VR, case-insensitive. Unknown names return an error |
| `z_threshold` | number | optional | Detection threshold and minimum |z| filter (default: 3.0) |
| `causes` | array[string] | optional | Keep only these: elevation_change, pace_change, fatigue, isolated |
| `limit` | integer | optional (default `50`) | Maximum number of results (default: 50) |
| `sort_by` | enum: `z_score`, `timestamp` | optional (default `z_score`) | z_score = |z_score| descending (default), timestamp = ascending; applied before limit |

## Training Plan

### `get_current_fitness_summary`

CLI: `garmin-db training-plan fitness-summary`

Fitness snapshot over the last lookback_weeks up to today: vdot (latest Garmin VO2max x 0.98, or from the fastest 3 km+ run when none), Daniels pace_zones (s/km), Garmin hr_zones from the latest run, weekly_volume_km and runs_per_week (totals / weeks), training_type_distribution (shares of Garmin training-effect labels), gap fields for a 7+ day break, and body_composition when present. This vdot is Garmin-derived and runs optimistic; the objective one comes from get_objective_fitness_curve and is what get_race_readiness uses.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `lookback_weeks` | integer | optional | Weeks back from today (default: 8); volume is total km divided by this, so a partial current week lowers it |

### `get_garmin_scheduled_workouts`

CLI: `garmin-db training-plan scheduled-workouts`

Fetch scheduled workouts (including adaptive plan workouts) live from the Garmin Connect calendar-service for a date range; nothing is read from DuckDB. Returns {start_date, end_date, count, workouts} where each workout is {date, title, item_type, schedule_id, training_plan_id, training_plan_name, workout_uuid} (missing keys null), ascending by date and de-duplicated. Items titled [MCP] are copies of saved prescriptions, whose canonical form is get_weekly_prescriptions; adaptive-plan items are reference only. Returns {error} when the Garmin call fails.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | string | **required** | Inclusive start date (YYYY-MM-DD) |
| `end_date` | string | **required** | Inclusive end date (YYYY-MM-DD) |

## Athlete

### `save_athlete_profile`

CLI: `garmin-db athlete save-profile`

Save the athlete profile (current focus, race goals, and season retrospectives) as a single object to DuckDB. The profile row is upserted on user_id; goals and retrospectives are fully replaced per user_id, so the normalized tables always hold the latest state. Each save additionally appends a JSON snapshot of the whole profile as a new version, keeping overwritten content (e.g. the previous focus_notes) recoverable via list_athlete_profile_versions + get_athlete_profile_version.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `profile` | object | **required** | Profile JSON with user_id (default 'default'), current_focus, focus_notes, week_start_day (0=Mon..6=Sun, default 0), goals (list of {race_name, race_date, priority, goal_type, distance_km, target_time_seconds, status, notes}), and retrospectives (list of {season_label, period_start, period_end, narrative, key_learnings}). |

### `get_athlete_profile`

CLI: `garmin-db athlete get-profile`

Get the athlete profile (current focus, goals, and retrospectives) merged into a single object. Returns an empty structure (current_focus=None, goals=[], retrospectives=[]) when no profile is registered.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `user_id` | string | optional | Profile owner identifier (default: 'default') |

### `list_athlete_profile_versions`

CLI: `garmin-db athlete list-profile-versions`

List recent athlete profile snapshots as metadata only (newest first). Every save_athlete_profile appends the whole profile as a new version; this indexes that history without the bulky snapshot: each entry has version_id, user_id, created_at, current_focus, focus_notes_chars, n_goals, and n_retrospectives. Use get_athlete_profile_version to read one snapshot in full. Returns an empty list when no version exists.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `user_id` | string | optional | Profile owner identifier (default: 'default') |
| `limit` | integer | optional | Maximum number of versions to return (default: 5) |

### `get_athlete_profile_version`

CLI: `garmin-db athlete get-profile-version`

Get one athlete profile snapshot in full: version_id, user_id, created_at, and profile_data (the snapshot decoded back into an object). Pick version_id from list_athlete_profile_versions; snapshots are large, so fetch one at a time. Returns null when no such version exists for the user.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `version_id` | integer | **required** | Version identifier from list_athlete_profile_versions |
| `user_id` | string | optional | Profile owner identifier (default: 'default') |

### `save_weekly_review`

CLI: `garmin-db athlete save-review`

Save a weekly training review to DuckDB. Each save appends a new version for (user_id, week_start_date) instead of overwriting, so re-running the same week keeps prior versions as history; the latest version is treated as canonical. The free-form review_data payload is stored as JSON, minus the per-day plan: a non-empty review_data.verdict is rejected because those rows live in save_weekly_prescriptions (rating/rationale) and the verdict is derived from them on read. Returns {status, user_id, week_start_date, review_id}; pass review_id to save_weekly_prescriptions to link the week's prescribed sessions to this review version.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `review` | object | **required** | Review JSON with user_id (default 'default'), week_start_date, week_end_date, review_date, review_data (object, e.g. {this_week, garmin_next_week, recommendations, overall}), agent_name, and agent_version. review_data must NOT carry verdict rows: the per-day plan (rating/rationale) belongs to save_weekly_prescriptions and the verdict is derived from it. |

### `get_weekly_review`

CLI: `garmin-db athlete get-review`

Get a single weekly review (the latest version of its week). When week_start_date is omitted, the latest version of the most recent week is returned. review_data is JSON-decoded back into an object; its verdict is derived from the week's canonical weekly_prescriptions batch (verdict_source='prescriptions' with prescription_batch_id, or 'stored' for reviews written before the split). Returns null when no matching review exists.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `week_start_date` | string | optional | Week start date (YYYY-MM-DD). When omitted, returns the most recent review. |
| `user_id` | string | optional | Profile owner identifier (default: 'default') |

### `save_symptom`

CLI: `garmin-db athlete save-symptom`

Log one pain / tightness report to DuckDB: what was felt, where (one body region per call), how bad (severity 0-10), and when (during_run / after_run / morning / rest_day). Rows are append-only, so two sore spots on one day are two calls and a later report never overwrites an earlier one. Log severity 0 when the athlete was asked and reported nothing: that row is what lets a later read tell 'no pain' from 'never asked'. Returns {status, symptom_id}.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `date` | string | **required** | Date the symptom was felt (YYYY-MM-DD) |
| `body_region` | enum: `foot`, `ankle`, `achilles`, `calf`, `shin`, `knee`, `hamstring`, `quad`, `hip`, `glute`, `groin`, `lower_back`, `other` | **required** | Where it was felt (one region per call; log two spots twice) |
| `severity` | integer | **required** | 0-10, where 0 means asked and clear (worth logging: it separates 'no pain' from 'not asked'), 1-3 niggle, 4-6 pain that alters the run, 7-10 pain that stops it |
| `phase` | enum: `during_run`, `after_run`, `morning`, `rest_day` | **required** | When it was felt: during_run, after_run, morning, rest_day |
| `side` | enum: `left`, `right`, `both` | optional | Side of the body (omit when not applicable) |
| `activity_id` | integer | optional | The run this refers to, when there is one |
| `note` | string | optional | Free-form note in the athlete's own words |
| `user_id` | string | optional | Profile owner identifier (default: 'default') |

### `get_symptoms`

CLI: `garmin-db athlete get-symptoms`

Get the athlete's symptom (pain / niggle) reports in a date range, oldest first, optionally narrowed to one body_region. Each row carries date, body_region, side, severity, phase, activity_id and note; severity-0 rows are included because they record an explicit all-clear. Returns an empty list when nothing was logged.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | string | **required** | Range start, inclusive (YYYY-MM-DD) |
| `end_date` | string | **required** | Range end, inclusive (YYYY-MM-DD) |
| `body_region` | string | optional | Optional region filter (e.g. 'calf'); omit for every region |
| `user_id` | string | optional | Profile owner identifier (default: 'default') |

### `get_symptom_status`

CLI: `garmin-db athlete symptom-status`

Get the deterministic symptom verdict for a day: reads the last 14 days of symptom reports and flags a body region when its two most recent reports are both severity 3+ (pain that comes and goes) or when any report within 7 days hit severity 5+. Returns {date, flag, flagged_regions (body_region, side, rule='consecutive'|'acute', latest_severity, latest_date, reports), asked_today, clear_today, recently_cleared, days_since_last_report, reason_ja}. Use this for gates ('run only if no leg tightness'): clear_today distinguishes an explicit all-clear from a question that was never asked, and days_since_last_report is null when nothing was logged at all.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `date` | string | optional | Reference day (YYYY-MM-DD). When omitted, today is used (symptoms describe how the legs are now, not on the last run's date). |
| `user_id` | string | optional | Profile owner identifier (default: 'default') |

### `prefetch_weekly_review_context`

CLI: `garmin-db athlete prefetch-weekly-review-context`

Pre-fetch the shared weekly-review CONTEXT bundle in a single call: resolves the target week W (and prior week W-1) and returns both weeks' activities (with performance_trends + weather), the fitness summary (Garmin native hr_zones), multi-week load_trend/acwr, recovery (trend/status/baseline_deviation), strength sessions, the training_block backbone (W's block + long-run ladder step + weeks to the block's end + quality budget), prescriptions_prev_week (W-1 rows + adherence counts), prescriptions_current_week (W's canonical batch with its batch_id / review_id), the Garmin scheduled_workouts for W with the garmin_conflicts they raise against the block, the athlete_profile, goals with weeks_to_race, and the last past_review. Every collector is null-on-error (additive). Excludes catch_up_ingest (a write); run that separately before this.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `target` | string | optional | Target week W selector: omit for the smart default (today == last day of the week -> next week, else this week), 'this' for the week containing today, 'next' for the following week, or a YYYY-MM-DD date within the desired week. |
| `user_id` | string | optional | Profile owner identifier (default: 'default') |

## Race

### `get_race_readiness`

CLI: `garmin-db race readiness`

Get race readiness: the athlete's current VDOT (the objective fitness curve's latest point when it is at most 90 days old, else Garmin's optimistic VO2max conversion; vdot_source names which of 'objective' / 'garmin_vo2max' was used), VDOT-based race-time predictions (5k/10k/half/full in seconds), the active race goal (priority A / active preferred, else the nearest future race), and a progress block with the predicted goal-distance time, gap to target (seconds; positive = behind target), pace gap (sec/km), weeks remaining, and a status (ahead/on_track/behind). Returns empty predictions when no VDOT can be derived and a null goal/progress when no goal is registered.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `user_id` | string | optional (default `default`) | Profile owner identifier (default: 'default') |
| `lookback_weeks` | integer | optional (default `8`) | Lookback window (weeks) for the fitness assessment (default: 8) |

## Training Load

### `get_acwr`

CLI: `garmin-db load acwr`

Get the distance-based Acute:Chronic Workload Ratio (ACWR), an injury-risk proxy. Daily load is the sum of total_distance_km; acute = the last-7-day load sum and chronic = the last-28-day load sum divided by 4 (weekly average). Returns acute_load_7d, chronic_load_28d_weekly, acwr (null when there is no chronic baseline), and a status (undertraining <0.8 / optimal 0.8-1.3 / caution 1.3-1.5 / high_risk >1.5 / insufficient_data). HR-independent: works even when avg_heart_rate is null.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `end_date` | string | optional | Reference day (YYYY-MM-DD) the ACWR is computed as of. Defaults to the latest activity_date. |

### `get_load_trend`

CLI: `garmin-db load trend`

Get the weekly training-load and ACWR trend over the trailing lookback_weeks (default 12). Returns a weeks array (oldest to newest) with week_start, load_km (that week's total distance), acwr (null when there is no chronic baseline), and status. Distance-based and HR-independent.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `lookback_weeks` | integer | optional (default `12`) | Number of trailing weekly buckets to return (default: 12). |
| `end_date` | string | optional | Reference day (YYYY-MM-DD) for the most recent week. Defaults to the latest activity_date. |

### `get_injury_risk`

CLI: `garmin-db load injury-risk`

Get a composite injury-risk score (0-100) with a low/moderate/high band and a per-factor breakdown, live-computed (no LLM, no backfill). Fuses seven deterministic signals: ACWR (weight 0.25; 0.8-1.3 is the safe zone, 1.5 = 50%, 1.8+ = 100%), the symptom-log rule (0.25), the post-race protection window (0.15; inside the window green = 25%, yellow = 60%, red = 100%), the latest long run's next-morning recovery cost (0.10; criteria fired / 3), worsening durability trend (0.10), personal wellness-baseline deviation of HRV/readiness/RHR (0.10), and trailing-14-day form anomalies (0.05). Missing signals are dropped and the rest renormalized; when all are missing returns {insufficient_data: true}. Bands: <30 low / 30-60 moderate / >60 high. Defaults to the latest activity_date.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `date` | string | optional | Reference day (YYYY-MM-DD) the injury-risk score is computed as of. Defaults to the latest activity_date. |

### `get_post_event_window`

CLI: `garmin-db load post-event-window`

Get the 21-day protection window after the last race or comparably big stimulus, and whether the long runs since then stayed under the pre-event ceiling. The event comes from the race calendar first (athlete_goals at any status, plus kind='race' steps of the block's long-run ladder, mapped to that week's Sunday); a >=18 km run at or above its own Garmin zone-3 lower boundary is only a fallback proxy and never overrides a calendar event on the same day (a cold-weather half can average 141 bpm). ceiling_km = the longest run in the 56 days before the event. Verdicts: no_event / green (outside the window, or at or under the ceiling) / yellow (over the ceiling) / red (over it by more than 10%) / insufficient_data (in window, no ceiling). Returns date, last_event {date, source, label, activity_id}, days_since_event, in_window, ceiling_km, longest_since_km, longest_since_activity_id, overshoot_pct, verdict and a Japanese reason_ja. Defaults to the latest activity_date.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `date` | string | optional | Reference day (YYYY-MM-DD) the protection window is evaluated as of. Defaults to the latest activity_date. |

## Durability

### `get_activity_durability`

CLI: `garmin-db durability activity`

Get one activity's cardiac decoupling: the second-half vs first-half HR/speed efficiency ratio (split at the time-series timestamp midpoint). Returns activity_id, activity_date, distance_km, decoupling_pct ((back HR/speed)/(front HR/speed)-1; >5% suggests insufficient aerobic durability), pace_fade_pct (back/front pace ratio), and nullable second-half form fades gct_fade_pct / vo_fade_pct / vr_fade_pct (back-vs-front ground-contact time / vertical oscillation / vertical ratio; null on devices lacking the metric). Returns null when HR or speed data is missing.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** | Activity ID to compute first-half vs second-half decoupling for. |

### `get_durability_trend`

CLI: `garmin-db durability trend`

Get the longitudinal cardiac-decoupling trend across long runs in a date window. Only activities with total_distance_km >= min_distance_km (default 10) are included. Returns an activities array (per-activity durability, date ascending) and a trend block with decoupling_slope_per_day (regressed on elapsed days), data_points, direction (improving when decoupling falls / worsening / stable / insufficient_data), plus second-half form decay: gct_fade_slope_per_day (GCT fade regressed over runs with form data; null when <2 such runs) and form_direction (same classification applied to GCT fade).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | string | **required** | Inclusive window start date (YYYY-MM-DD). |
| `end_date` | string | **required** | Inclusive window end date (YYYY-MM-DD). |
| `min_distance_km` | number | optional (default `10.0`) | Minimum total_distance_km for an activity to qualify as a long run (default: 10.0). Shorter runs are excluded. |

### `get_long_run_progression_gate`

CLI: `garmin-db durability progression-gate`

Judge whether the next long run may be extended. Compares this long run's second-half decay against a comparable earlier practice long run (similar distance, within 8 weeks, similar temperature, races excluded) and returns verdict (green/yellow/red/insufficient_data), recommendation (extend/repeat/shorten), the triggers that fired (gct_fade_ms >= 10, cadence_fade_spm <= -5 (running samples only, so prescribed walk/fuel breaks never read as a cadence collapse), pace_fade_pct >= 8, each with the reference value and whether it is clearly worse, plus a fourth trigger 'recovery_cost' from get_long_run_recovery_cost -- what the run cost over the next two mornings vs the athlete's own 14-day baseline; it fires with reference=null since no earlier run can exonerate it), reference_activity_id, a recovery_cost block (cost_flag, criteria_fired, insufficient_data, reason_ja; null when unavailable), decoupling_contaminated (current run at >= 30C, where decoupling is thermal drift) and a Japanese reason_ja, alongside the current and reference durability blocks. A morning cost that fires ALONE is yellow/repeat (the legs held, so hold the distance); together with any in-run trigger it is red/shorten. An unevaluated cost never changes the verdict.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** | Long-run activity ID to judge (compared against a comparable earlier practice long run). |

## strength

### `ingest_strength_sessions`

CLI: `garmin-db strength ingest`

Discover strength_training (補強) activities from the Garmin Connect API in a date window and insert summary rows into the strength_sessions table. Catch-up aware: omit start_date to ingest from the latest stored strength date, or end_date - 30 days when none exist yet; omit end_date to default to today. Discovery uses the activity list filtered to typeKey == 'strength_training' (runs with distance are excluded). Each session's ACTIVE exercise sets are aggregated into a category_counts map (e.g. {"CRUNCH": 4, "PLANK": 7}). Sessions already stored are skipped without an exercise_sets API call. Returns discovered, ingested, skipped_existing, activity_ids, and the resolved window {start, end}.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | string | optional | Inclusive window start date (YYYY-MM-DD). When omitted, catch-up resolution is used: the latest stored strength date (re-fetched so recent edits are reflected), or end_date - 30 days when no strength session exists yet. |
| `end_date` | string | optional | Inclusive window end date (YYYY-MM-DD). Defaults to today when omitted. |

### `get_strength_sessions`

CLI: `garmin-db strength list`

Get persisted strength_training (補強) summaries with activity_date in [start_date, end_date] from the strength_sessions table (no Garmin access). Returns a list (activity_date ascending) of summaries with activity_id, activity_date, start_time_local, activity_name, active/elapsed duration, avg/max heart rate, calories, active/total sets and category_counts (a dict of ACTIVE exercise-set categories). Returns an empty list when none match.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | string | **required** | Inclusive window start date (YYYY-MM-DD). |
| `end_date` | string | **required** | Inclusive window end date (YYYY-MM-DD). |

## ingest

### `catch_up_ingest`

CLI: `garmin-db ingest catch-up`

Differential catch-up ingest across the running, weight, strength, hiking and wellness domains in a single call. Resolves an independent window per domain (each table advances at its own pace): end_date or today as the shared end, and per-domain start = start_date (when given) or that domain's latest stored date, or end_date - 30 days when the domain is empty. running delegates to ingest_running_activities, weight to ingest_weight_range, strength to ingest_strength_sessions, hiking to ingest_hiking_sessions, wellness to ingest_wellness_range. Pass domains to ingest a subset (default: all five). A failure in one domain is isolated (its entry carries an error) while the others complete. Returns each requested domain's result plus a window map of {domain: {start, end}}. When the running domain succeeds, the prescribed sessions in its window are also reconciled against the ingested runs and the counts are returned as prescriptions_reconciled (null when that step failed). On a fully-successful run (no domain error), if any of the last 4 completed weeks still lacks a trend narration, the result also carries trend_pending: {granularity, period_start, period_end} for the oldest such week so callers can fire trend-narration for it (idempotent: omitted once every scanned week is narrated). Use get_pending_trend_period to ask the same question without running an ingest.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | string | optional | Inclusive shared window start date (YYYY-MM-DD). When omitted, each domain resolves its own start from its latest stored date (or end_date - 30 days when that domain is empty). |
| `end_date` | string | optional | Inclusive window end date (YYYY-MM-DD). Defaults to today when omitted. |
| `domains` | array[string] | optional | Subset of domains to ingest. Defaults to all of running, weight, strength, hiking, wellness. Domains not listed are skipped. |

### `get_pending_trend_period`

CLI: `garmin-db ingest pending-trend`

Read-only check for a completed week that still lacks a longitudinal trend narration (trend_analyses row). Scans the lookback_weeks (default 4) most-recently-completed weeks relative to end_date (default today), oldest first, using the athlete's configured week-start day, and returns {granularity, period_start, period_end} for the first week with no narration, or null when all of them are narrated. Unlike catch_up_ingest's trend_pending field, this runs no ingest and is not gated on ingest success, so a caller (e.g. the weekly-review skill) can trigger trend-narration for the returned period even in a session that did not run catch-up.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `end_date` | string | optional | Reference date (YYYY-MM-DD) whose completed weeks are scanned. Defaults to today when omitted. |
| `lookback_weeks` | integer | optional | How many completed weeks to scan, oldest first. Defaults to 4; pass 1 to look only at the week that just ended. |

## Workout Scheduling

### `schedule_custom_workout`

CLI: `garmin-db workout schedule`

Build a Garmin running workout from a generic steps array, force-prefix its title with '[MCP] ', replace any same-title [MCP] template (delete -> recreate), upload it and schedule it on date. Runs the [MCP] cleanup first (unschedule past-dated [MCP] assignments, delete [MCP] templates with no future schedule), so stale items never linger; a cleanup failure never aborts the registration. Each step is an executable step (step_type warmup/run/recovery/cooldown; one of duration_minutes, duration_seconds or distance_m; optional hr_low/hr_high for a custom heart-rate-range target) or a repeat group (repeat_count + nested steps). Returns {workout_id, schedule_id, date, title, replaced_workout_ids, skipped_replace_ids, cleanup, bookend_minutes}. bookend_minutes is the value to record on the prescription row: the warmup + cooldown minutes when the steps open with a warmup (a threshold / tempo shape), else 0 (an easy run with strides ends on a 5min easy step that is part of its total).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `date` | string | **required** | Target date to schedule on (YYYY-MM-DD) |
| `title` | string | **required** | Workout title. A '[MCP] ' prefix is force-added (not doubled) so the cleanup tool can distinguish self-authored workouts. |
| `steps` | array[object] | **required** | Ordered workout steps. Each entry is either an executable step (step_type of warmup/run/recovery/cooldown, one of duration_minutes, duration_seconds or distance_m, and optional hr_low/hr_high for a custom HR-range target) or a repeat group (repeat_count + nested steps). |

### `schedule_weekly_prescriptions`

CLI: `garmin-db workout schedule-week`

Register a whole week of saved prescriptions to the Garmin calendar in one batch. Steps are derived in code from each row: long/easy/recovery become a single body step on target_minutes or target_km (hr_high as a ceiling, hr_low only when prescribed) so the watch asks for exactly what was prescribed; an easy row with a strides add-on becomes an opening easy step, a repeat group of reps x (run_seconds stride / recovery_seconds jog, no HR target) and a final 5min easy step, together exactly target_minutes (the run total). Quality sessions (threshold/tempo) keep a 10min warmup and a 5min cooldown around the body; rest/strength/cross rows, rows already registered and rows already reconciled with a run (done / replaced / skipped) are skipped, and naming an id in prescription_ids re-registers it. dry_run=True (default) returns {dry_run, week_start_date, items ({prescription_id, date, title, steps, bookend_minutes, existing_same_day, already_registered, would_replace_workout_ids}), would_cleanup, skipped, stale_superseded} so the plan can be confirmed first. dry_run=False runs the [MCP] cleanup first (unschedule past-dated [MCP] assignments, delete [MCP] templates with no future schedule; a cleanup failure never aborts the batch), then registers each item (delete the same-title [MCP] template, the [MCP] workout already recorded on a re-registered row AND the [MCP] workouts the week's superseded batches registered on that day, so a revised title never leaves the old item on the calendar -> upload -> schedule), records the workout/schedule ids with status=registered on the row, isolates per-item failures and returns {dry_run, week_start_date, cleanup, registered, failed, skipped, stale_superseded}. stale_superseded [{date, workout_ids}] lists superseded workouts on days the new batch no longer runs: they are never deleted, only reported (empty when prescription_ids narrows the run).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `week_start_date` | string | **required** | Week start date (YYYY-MM-DD) of the prescriptions to register. |
| `prescription_ids` | array[integer] | optional | Register only these prescription_ids (subset of the week). Naming an already-registered row re-registers it. Defaults to every registrable row of the week's latest batch. |
| `dry_run` | boolean | optional | When True (the default), return the plan (titles, steps, same-day Garmin conflicts) without writing anything to Garmin. |
| `user_id` | string | optional | Ledger owner identifier (default: 'default') |

### `cleanup_generated_workouts`

CLI: `garmin-db workout cleanup`

Tidy self-authored [MCP] workouts: unschedule past-dated [MCP] calendar assignments and delete [MCP] templates that have no future schedule. Never touches manual (non-[MCP]) workouts. The same tidy runs automatically before every schedule_custom_workout / schedule_weekly_prescriptions registration, so this tool is only needed to tidy without registering. Pass dry_run=True to only list what would be removed.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `dry_run` | boolean | optional (default `False`) | When True, only report the assignments/templates that would be removed without performing any write. |

## hiking

### `ingest_hiking_sessions`

CLI: `garmin-db hiking ingest`

Discover hiking (山行) activities from the Garmin Connect API in a date window and insert summary rows into the hiking_sessions table. Catch-up aware: omit start_date to ingest from the latest stored hiking date, or end_date - 30 days when none exist yet; omit end_date to default to today. Discovery uses the activity list filtered to typeKey == 'hiking'; hikes are kept out of the run-centric activities table so they never distort ACWR, load trend or form baselines. Sessions already stored are skipped. Returns discovered, ingested, skipped_existing, activity_ids, and the resolved window {start, end}.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | string | optional | Inclusive window start date (YYYY-MM-DD). When omitted, catch-up resolution is used: the latest stored hiking date, or end_date - 30 days when no hiking session exists yet. |
| `end_date` | string | optional | Inclusive window end date (YYYY-MM-DD). Defaults to today when omitted. |

### `get_hiking_sessions`

CLI: `garmin-db hiking list`

Get persisted hiking (山行) summaries with activity_date in [start_date, end_date] from the hiking_sessions table (no Garmin access). Returns a list (activity_date ascending) of summaries with activity_id, activity_date, start_time_local, activity_name, duration_seconds (moving) / elapsed_duration_seconds, distance_km, elevation_gain_m, elevation_loss_m, avg/max heart rate and calories. Use it for load/recovery context only — do not apply run pace or form interpretation. Returns an empty list when none match.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | string | **required** | Inclusive window start date (YYYY-MM-DD). |
| `end_date` | string | **required** | Inclusive window end date (YYYY-MM-DD). |

## Training Plan Ledger

### `save_training_blocks`

CLI: `garmin-db plan save-blocks`

Save the mesocycle ledger (training blocks) to DuckDB. Blocks are replaced wholesale per user_id (洗い替え, same as the athlete profile), so always pass the full list including unchanged blocks; sequence follows list order. Every save also appends a JSON snapshot of the whole list, so a previous plan stays recoverable. Validates the date range (start_date <= end_date), the phase, and that each long-run ladder step carries week_start plus exactly one of target_km / target_minutes. Returns {status, count, version_id}.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `blocks` | array[object] | **required** | Full ordered list of training blocks (洗い替え — unchanged blocks must be included). Each block: phase (base|build|peak|taper|race|recovery|cutback), title, start_date, end_date (YYYY-MM-DD), and optionally purpose, weight_mode (絞る|維持), quality_sessions_per_week, quality_types (list), long_run_ladder (list of {week_start, target_km OR target_minutes, hr_ceiling, kind, note}), cutback_rule (object), notes. |
| `user_id` | string | optional | Ledger owner identifier (default: 'default') |

### `get_training_blocks`

CLI: `garmin-db plan get-blocks`

Get the mesocycle ledger with the block that is active on a given date. Returns {blocks (ordered by sequence, JSON columns decoded), active_block (the block covering on_date, or null), ladder_step ({current, previous, next} long-run ladder steps for the week containing on_date, or null when no block covers it), on_date, week_start_date}. on_date defaults to today; the week is resolved with the athlete's week_start_day.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `on_date` | string | optional | Reference date (YYYY-MM-DD) used to resolve active_block and ladder_step. Defaults to today. |
| `user_id` | string | optional | Ledger owner identifier (default: 'default') |

### `save_weekly_prescriptions`

CLI: `garmin-db plan save-prescriptions`

Save one batch of prescribed sessions for a week (append-only). These rows are the single source of the per-day plan including its rating/comment; the weekly review derives its verdict from them. All rows get a fresh batch_id and the latest batch per week is canonical, so re-prescribing a week supersedes rather than mutates the earlier batch. Validates that each date falls inside the week, the session_type and rating are known, and hr_low <= hr_high. Once the week has a review, review_id must be that week's latest review version and may own only one batch — revise by saving a new review version first. A row may author its steps from a catalog template with workout {"template", "params"}; heart rate params are integer bpm (convert zones first), pace params s/km, and bookended templates also take warmup_minutes / cooldown_minutes. Templates (session types: example params): recovery (recovery: minutes, hr_high); easy (easy: minutes, hr_high); easy_strides (easy: minutes, hr_high, reps); long_easy (long: km, hr_high); aerobic_steady (tempo: km, hr_low, hr_high); tempo_continuous (tempo|threshold: minutes, hr_low, hr_high); cruise_intervals (threshold: reps, work_minutes, recovery_minutes, hr_low, hr_high); vo2_intervals (threshold: reps, work_seconds, recovery_seconds, pace_low, pace_high); short_reps (threshold: reps, work_seconds, recovery_seconds, recovery_step); hill_sprints (easy: minutes, hr_high, reps, work_seconds, recovery_seconds); progression (easy|long|tempo: stages); long_with_mp (long: easy_km_before, mp_km, easy_km_after, hr_high_easy, mp_pace_low, mp_pace_high, mp_hr_high); long_fast_finish (long: easy_km, finish_km, hr_high_easy, finish_pace_low, finish_pace_high, finish_hr_high, optional_finish); fartlek (tempo: reps, on_seconds, float_seconds, float_pace_high); race (long|tempo: distance_km, hr_high, optional_finish); time_trial (threshold: km). Returns {status, week_start_date, batch_id, count, prescription_ids}.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `week_start_date` | string | **required** | Week start date (YYYY-MM-DD); every row must fall in this week. |
| `prescriptions` | array[object] | **required** | Prescribed sessions for the week — the single source of the per-day plan, verdict included. Each row: date (YYYY-MM-DD), session_type (long|easy|recovery|threshold|tempo|rest|strength|cross), title, and optionally target_minutes, target_km, hr_low, hr_high (ceiling — the only bound for easy/long), pace_low_s_per_km, pace_high_s_per_km, rationale (the comment), rating (✅ | 🟡 | 🔴) and, on easy rows only, strides {"reps": 2-8, "run_seconds": 10-30 (default 20), "recovery_seconds": 60-180 (default 90)} — short pickups as a neuromuscular stimulus, not an interval, placed after at least 5min of easy running and followed by a final 5min easy; target_minutes stays the run total and must fit 10min plus reps x (run + recovery). Every run row should also set purpose — what the run is for, finer than session_type: easy | recovery (easy/recovery rows), long_easy | long_goal_pace | long_fast_finish (long rows), progression (easy/long/tempo), tempo (tempo/threshold), intervals (threshold/tempo), fartlek (easy/tempo/threshold), race (long/tempo/threshold); a purpose that does not fit the session_type is rejected, and a row without one falls back to the session_type default (long -> long_easy). Optional allowances {"walk": true|false} states what the run permits (walk breaks); other keys are rejected. Optional structure (run rows only, never together with strides) is the workout's ordered step list: each step has step_type (warmup|run|recovery|rest|cooldown), exactly one of duration_minutes / duration_seconds / distance_m, and optionally hr_low / hr_high in integer bpm (zone labels like 'Z4' are rejected), pace_low_s_per_km / pace_high_s_per_km, label and optional (top-level run steps only); a repeat group is {"repeat_count": 1-30, "steps": [...]}, nested at most two deep. When target_minutes is omitted and every step is timed it is derived from the structure (the body only — steps other than warmup/cooldown — for threshold/tempo, the total otherwise); hr_low / hr_high are never derived. Instead of hand-writing steps, a run row may set workout {"template": <catalog id>, "params": {...}} (never together with structure or strides): the template expands into the structure, the title when the row has none and the template's purpose when it declares none (templates are listed in the tool description). Revising a week means saving a new review version first and passing its review_id: a second batch for the same review is rejected. |
| `review_id` | integer | optional | weekly_reviews.review_id when saved by a weekly review. |
| `user_id` | string | optional | Ledger owner identifier (default: 'default') |

### `get_weekly_prescriptions`

CLI: `garmin-db plan get-prescriptions`

Get the canonical (latest batch) prescribed sessions for a week or a single day. Give exactly one of week_start_date / date — date resolves its week with the athlete's week_start_day. Rows are ordered by date and carry targets (target_km / target_minutes), HR and pace bounds, purpose, allowances and the step structure (null when not set), status (prescribed|registered|done|replaced|skipped), the Garmin workout/schedule ids and actual_activity_id. Returns an empty list when nothing is prescribed.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `week_start_date` | string | optional | Week start date (YYYY-MM-DD). Give exactly one of week_start_date / date. |
| `date` | string | optional | Single day (YYYY-MM-DD). Give exactly one of week_start_date / date. |
| `user_id` | string | optional | Ledger owner identifier (default: 'default') |

### `update_prescription_status`

CLI: `garmin-db plan update-status`

Update one prescription's status and optionally its Garmin workout / schedule ids, linked activity id, registered bookend minutes and the registered workout's step structure, refreshing updated_at. Only the values you pass are written, so registering a Garmin workout and later linking the actual activity are independent updates. Returns {updated: false} when the prescription_id does not exist.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `prescription_id` | integer | **required** | Prescription row identifier from get_weekly_prescriptions. |
| `status` | string | **required** | New lifecycle state: prescribed | registered | done | replaced | skipped. |
| `garmin_workout_id` | integer | optional | Garmin workout id to record (optional). |
| `garmin_schedule_id` | integer | optional | Garmin schedule id to record (optional). |
| `actual_activity_id` | integer | optional | Linked actual activity id to record (optional). |
| `registered_bookend_minutes` | integer | optional | Warmup + cooldown minutes the registered workout actually carries (optional). schedule_custom_workout returns it as bookend_minutes — pass it through when linking a hand-built quality workout so reconcile_prescriptions judges against the real bookends instead of the standard 15min. schedule_weekly_prescriptions records it on its own. |
| `structure` | array[object] | optional | The steps of a hand-built registered workout (optional), in the same format as a prescription row's structure (hr in integer bpm, never a zone label). Pass it with status registered so the run is judged against what the watch was asked to do. |

### `reconcile_prescriptions`

CLI: `garmin-db plan reconcile`

Deterministically link prescribed sessions in a date range to the activities that actually happened, so adherence needs no LLM. For each open (prescribed / registered) latest-batch row with a past date: an activity on that date within tolerance (0.85x-1.30x of target_km / target_minutes, with quality sessions (threshold/tempo) allowed the warmup/cooldown their registered workout adds — the row's registered_bookend_minutes when recorded, else the standard 15min) marks it done, any other activity marks it replaced (a rest day with a run is always replaced), and no activity marks it skipped (rest with no activity is done). strength rows are matched against strength_sessions instead of runs, on presence alone: a session on that date marks the row done, none marks it skipped (Garmin records working time only, so a duration band would reject a circuit done as prescribed). Future dates and superseded batches are never touched. Returns {updated, done, replaced, skipped}.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | string | **required** | Inclusive range start (YYYY-MM-DD). |
| `end_date` | string | **required** | Inclusive range end (YYYY-MM-DD). |
| `user_id` | string | optional | Ledger owner identifier (default: 'default') |

## gear

### `get_gear_wear`

CLI: `garmin-db gear wear`

Get every shoe with its lifetime mileage and whether it is due for replacement, most worn first. Wear is measured against the athlete's own per-shoe limit from Garmin (gear.json maximumMeters), not a generic mileage rule, so wear_status (ok <60% / monitor 60-80% / due_soon 80-100% / over >=100%) is null when no limit is recorded rather than assumed. A second, independent axis age_status (ok / aging >=24mo / aged >=36mo) covers midsole foam degrading on the shelf regardless of use; replace_recommended takes the stricter of the two. Shoes are identified by gear_uuid, so two generations sharing one model name keep separate mileage. Retired shoes are excluded unless include_retired is true. Returns gear (gear_label, gear_model, gear_nickname, gear_uuid, runs, km, max_km, wear_pct, wear_status, first_use_date, since_date, age_months, age_status, last_used, is_retired, replace_recommended) plus a replace_recommended list of the labels needing action.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `include_retired` | boolean | optional (default `False`) | Include shoes already retired in Garmin (default: false) |
| `as_of` | string | optional | Reference date in YYYY-MM-DD for the age axis (default: today) |

## Server

### `get_server_info`

Get diagnostic info about the running MCP server (shim started_at plus worker DB diagnostics). Use to verify readiness.

_No parameters._

### `reload_server`

Restart the execution worker to pick up code changes. The MCP shim process stays alive (the session is preserved) and a tools/list_changed notification is sent. Signature-compatible changes apply with no reconnect; schema changes (added/removed tools or changed args) need one /mcp reconnect. Shim code (server.py, worker_client.py) is not reloaded and needs /mcp or a new session. The worker is pinned to the caller's working directory, so reload from the main checkout, not from a worktree that will be deleted. A subagent that calls it loses its garmin-db tools.

_No parameters._
