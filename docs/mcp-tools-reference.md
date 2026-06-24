# MCP Tools Reference

Auto-generated from the `ToolDef` registry (`garmin_mcp.tools.ALL_DEFS`) — **50 tools** (48 domain + 2 server). Do not edit by hand.

Regenerate with:

```bash
uv run --directory packages/garmin-mcp-server \
  python -m garmin_mcp.scripts.generate_tool_reference
```

Tools are callable as MCP tools (`mcp__garmin-db__<name>`) and, for domain tools, via the reloadless `garmin-db` CLI. Return shapes are not captured by the registry — call a tool (or read its handler) for the response structure.

## Contents

- [Export](#export) (1)
- [Metadata](#metadata) (3)
- [Splits](#splits) (5)
- [Analysis](#analysis) (6)
- [Physiology](#physiology) (8)
- [Performance](#performance) (3)
- [Time Series](#time-series) (4)
- [Training Plan](#training-plan) (6)
- [Athlete](#athlete) (4)
- [Race](#race) (1)
- [Training Load](#training-load) (2)
- [Durability](#durability) (2)
- [strength](#strength) (2)
- [ingest](#ingest) (1)
- [Server](#server) (2)

## Export

### `export`

CLI: `garmin-db export run`

Export query results to file (returns handle only, not data). Use for large datasets that need processing in Python.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | **required** | DuckDB SQL query to execute |
| `format` | enum: `parquet`, `csv` | optional (default `parquet`) | Output format (parquet recommended for efficiency) |
| `max_rows` | integer | optional (default `100000`) | Safety limit for export size (default: 100000) |

## Metadata

### `get_activity_by_date`

CLI: `garmin-db metadata activity-by-date`

Get activity ID and metadata from date

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `date` | string | **required** | Date in YYYY-MM-DD format |

### `get_date_by_activity_id`

CLI: `garmin-db metadata date-by-activity-id`

Get date and activity name from activity ID

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** |  |

### `ingest_activity`

CLI: `garmin-db metadata ingest`

Ingest activity data from Garmin Connect into DuckDB. Fetches raw data, stores in DuckDB, and runs form evaluation.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `date` | string | **required** | Activity date in YYYY-MM-DD format |
| `force_regenerate` | boolean | optional (default `False`) | Force regeneration of all data (default: false) |

## Splits

### `get_splits_pace_hr`

CLI: `garmin-db splits pace-hr`

Deprecated: use get_splits_comprehensive instead. Get pace and heart rate data from splits (lightweight: ~3 fields/split, or ~200 bytes with statistics_only=True)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** |  |
| `statistics_only` | boolean | optional (default `False`) | If true, return only aggregated statistics (mean, median, std, min, max) instead of per-split data. Reduces output size by ~80%. Default: false |

### `get_splits_form_metrics`

CLI: `garmin-db splits form-metrics`

Deprecated: use get_splits_comprehensive instead. Get form efficiency metrics from splits (lightweight: ~4 fields/split, or ~300 bytes with statistics_only=True)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** |  |
| `statistics_only` | boolean | optional (default `False`) | If true, return only aggregated statistics (mean, median, std, min, max) for GCT, VO, VR instead of per-split data. Reduces output size by ~80%. Default: false |

### `get_splits_elevation`

CLI: `garmin-db splits elevation`

Get elevation and terrain data from splits (lightweight: ~5 fields/split, or ~250 bytes with statistics_only=True)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** |  |
| `statistics_only` | boolean | optional (default `False`) | If true, return only aggregated statistics (mean, median, std, min, max) for elevation gain/loss instead of per-split data. Reduces output size by ~80%. Default: false |

### `get_splits_comprehensive`

CLI: `garmin-db splits comprehensive`

Get comprehensive split data (12 fields: pace, HR, form, power, cadence, elevation). Supports statistics_only mode for 67% token reduction.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** |  |
| `statistics_only` | boolean | optional (default `False`) | If true, return only aggregated statistics (mean, median, std, min, max) instead of per-split data. Reduces output size by ~67%. Default: false |

### `get_interval_analysis`

CLI: `garmin-db splits interval-analysis`

Analyze interval training Work/Recovery segments using intensity_type from DuckDB

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** |  |

## Analysis

### `insert_section_analysis_dict`

CLI: `garmin-db analysis insert-section`

Insert section analysis dict directly into DuckDB (no file creation)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** |  |
| `activity_date` | string | **required** |  |
| `section_type` | string | **required** |  |
| `analysis_data` | object | **required** |  |

### `validate_section_json`

CLI: `garmin-db analysis validate-section`

Validate section analysis data against Pydantic schema. Returns {valid: bool, errors: list[str]}.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `section_type` | enum: `split`, `phase`, `efficiency`, `environment`, `summary` | **required** |  |
| `analysis_data` | object | **required** |  |

### `get_analysis_contract`

CLI: `garmin-db analysis contract`

Get analysis contract for a section type (output schema, evaluation thresholds, instructions). Agents call this for up-to-date evaluation criteria.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `section_type` | enum: `split`, `phase`, `efficiency`, `environment`, `summary` | **required** | Section type |

### `analyze_performance_trends`

CLI: `garmin-db analysis performance-trends`

Analyze performance trends across multiple activities with filtering (Phase 3.1)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `metric` | string | **required** | Metric name (pace, heart_rate, cadence, power, vertical_oscillation, ground_contact_time, vertical_ratio, distance, training_effect, elevation_gain) |
| `start_date` | string | **required** | Start date in YYYY-MM-DD format |
| `end_date` | string | **required** | End date in YYYY-MM-DD format |
| `activity_ids` | array[integer] | **required** | List of activity IDs to analyze |
| `activity_type` | string | optional | Optional activity type filter |
| `temperature_range` | array[number] | optional | Optional [min_temp, max_temp] filter in Celsius |
| `distance_range` | array[number] | optional | Optional [min_km, max_km] filter |

### `extract_insights`

CLI: `garmin-db analysis extract-insights`

Extract insights from section analyses using keyword-based search (Phase 3.2)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `keywords` | array[string] | **required** | Keywords to search for (e.g., key_strengths, improvement_areas, efficiency, evaluation, environmental_impact) |
| `section_types` | array[string] | optional | Optional section types to filter by |
| `limit` | integer | optional (default `10`) | Maximum number of results (default: 10) |
| `offset` | integer | optional (default `0`) | Number of results to skip (default: 0) |
| `max_tokens` | integer | optional | Maximum token count (optional) |

### `compare_similar_workouts`

CLI: `garmin-db analysis compare-workouts`

Find and compare similar past workouts based on pace and distance (Phase 4.5)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** | Target activity ID |
| `pace_tolerance` | number | optional | Pace tolerance as fraction (default 0.2 = ±20%) |
| `distance_tolerance` | number | optional | Distance tolerance as fraction (default 0.2 = ±20%) |
| `terrain_match` | boolean | optional | Whether to match terrain characteristics |
| `activity_type_filter` | string | optional | Optional activity type keyword filter |
| `date_range` | array[string] | optional | Optional [start_date, end_date] in YYYY-MM-DD format |
| `limit` | integer | optional | Maximum number of results (default 10) |

## Physiology

### `get_form_efficiency_summary`

CLI: `garmin-db physiology form-efficiency`

Get form efficiency summary (GCT, VO, VR metrics) from form_efficiency table

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** |  |

### `get_form_evaluations`

CLI: `garmin-db physiology form-evaluations`

Get pace-corrected form evaluation results (expected values, actual values, scores, star ratings, evaluation texts)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** |  |

### `get_form_baseline_trend`

CLI: `garmin-db physiology form-baseline-trend`

Get form baseline trend (1-month coefficient comparison for form_trend analysis)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** |  |
| `activity_date` | string | **required** | Activity date in YYYY-MM-DD format |
| `user_id` | string | optional (default `default`) | User ID (default: 'default') |
| `condition_group` | string | optional (default `flat_road`) | Condition group (default: 'flat_road') |

### `get_hr_efficiency_analysis`

CLI: `garmin-db physiology hr-efficiency`

Get HR efficiency analysis (zone distribution, training type) from hr_efficiency table

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** |  |

### `get_heart_rate_zones_detail`

CLI: `garmin-db physiology heart-rate-zones`

Get heart rate zones detail (boundaries, time distribution) from heart_rate_zones table

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** |  |

### `get_vo2_max_data`

CLI: `garmin-db physiology vo2-max`

Get VO2 max data (precise value, fitness age, category) from vo2_max table

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** |  |

### `get_lactate_threshold_data`

CLI: `garmin-db physiology lactate-threshold`

Get lactate threshold data (HR, speed, power) from lactate_threshold table

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** |  |

### `get_body_composition_trend`

CLI: `garmin-db physiology body-composition-trend`

Get the body-composition trend over the trailing window (default 12 weeks). Decomposes the weight change between the first and last measurement into fat-mass and lean-mass components. Returns weeks, a date-ascending series ([{date, weight_kg, fat_mass, lean_mass}]; fat_mass/lean_mass null when body fat unrecorded), a change block (delta_weight, delta_fat, delta_lean, lean_loss_ratio, muscle_loss_warning -- true when >40% of the lost weight is lean mass, flagging leg-durability/injury risk), and lean_pwr (lean-mass power-to-weight = latest functional_threshold_power / lean mass; null when body fat or FTP is missing).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `weeks` | integer | optional (default `12`) | Trailing window length in weeks to analyze (default: 12). |

## Performance

### `get_performance_trends`

CLI: `garmin-db performance trends`

Get performance trends data (pace consistency, HR drift, phase analysis)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** |  |

### `get_weather_data`

CLI: `garmin-db performance weather`

Get weather data (temperature, humidity, wind) from activity

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** |  |

### `prefetch_activity_context`

CLI: `garmin-db performance prefetch-context`

Pre-fetch shared activity context for analysis agents. Returns training_type, weather, terrain, HR efficiency (zone_percentages), form evaluation scores, phase structure, and planned workout in a single call. Auto-generates the form baseline for the activity's month (and prior month) if missing.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** |  |

## Time Series

### `get_split_time_series_detail`

CLI: `garmin-db time-series split-detail`

Get second-by-second detailed metrics for a specific 1km split (DuckDB-based, 98.8% token reduction)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** |  |
| `split_number` | integer | **required** | Split number (1-based) |
| `metrics` | array[string] | optional | List of metric names to extract (optional) |
| `statistics_only` | boolean | optional | If true, only return statistics (98.8% token reduction). Default: false |
| `detect_anomalies` | boolean | optional | Whether to detect anomalies in the data. Default: false |
| `z_threshold` | number | optional | Z-score threshold for anomaly detection. Default: 2.0 |

### `get_time_range_detail`

CLI: `garmin-db time-series time-range-detail`

Get second-by-second detailed metrics for arbitrary time range

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** |  |
| `start_time_s` | integer | **required** | Start time in seconds |
| `end_time_s` | integer | **required** | End time in seconds |
| `metrics` | array[string] | optional | List of metric names to extract (optional) |
| `statistics_only` | boolean | optional | If true, only return statistics (mean, std, min, max) without time series data. Default: false |

### `detect_form_anomalies_summary`

CLI: `garmin-db time-series anomalies-summary`

Detect form anomalies and return lightweight summary (~700 tokens, 95% reduction)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** |  |
| `metrics` | array[string] | optional | Metrics to analyze (default: GCT, VO, VR) |
| `z_threshold` | number | optional | Z-score threshold for anomaly detection (default: 3.0) |

### `get_form_anomaly_details`

CLI: `garmin-db time-series anomaly-details`

Get detailed anomaly information with flexible filtering (variable token size)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** |  |
| `anomaly_ids` | array[integer] | optional | Optional specific anomaly IDs to retrieve |
| `time_range` | array[integer] | optional | Optional [start_sec, end_sec] time range |
| `metrics` | array[string] | optional | Optional metric names to filter |
| `z_threshold` | number | optional | Optional minimum z-score threshold |
| `causes` | array[string] | optional | Optional causes to filter (elevation_change, pace_change, fatigue) |
| `limit` | integer | optional (default `50`) | Maximum number of results (default: 50) |
| `sort_by` | enum: `z_score`, `timestamp` | optional (default `z_score`) | Sort order: z_score (desc) or timestamp (asc) |

## Training Plan

### `get_current_fitness_summary`

CLI: `garmin-db training-plan fitness-summary`

Get current fitness level assessment (VDOT, pace zones, weekly volume, training type distribution)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `lookback_weeks` | integer | optional | Number of weeks to analyze (default: 8) |

### `save_training_plan`

CLI: `garmin-db training-plan save-plan`

Save a training plan (structured JSON) to DuckDB. Validates schema and safety constraints (volume progression <= 15%, return_to_run restrictions, date alignment).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `plan` | object | **required** | TrainingPlan JSON conforming to the Pydantic model schema (plan_id, goal_type, vdot, pace_zones, total_weeks, start_date, weekly_volumes, phases, workouts, etc.) |

### `get_training_plan`

CLI: `garmin-db training-plan get-plan`

Get a previously generated training plan

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `plan_id` | string | **required** | Plan identifier |
| `version` | integer | optional | Specific version to retrieve. Omit for latest active version. |
| `week_number` | integer | optional | Specific week to retrieve (optional) |
| `summary_only` | boolean | optional | If true, exclude individual workouts (default: false) |

### `upload_workout_to_garmin`

CLI: `garmin-db training-plan upload-workout`

Upload workout(s) to Garmin Connect

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `workout_id` | string | optional | Single workout ID to upload |
| `plan_id` | string | optional | Plan ID to upload all workouts from |
| `week_number` | integer | optional | Specific week to upload (with plan_id) |
| `schedule` | boolean | optional (default `True`) | Schedule workouts on Garmin Connect calendar (default: true) |

### `delete_workout_from_garmin`

CLI: `garmin-db training-plan delete-workout`

Delete workout(s) from Garmin Connect

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `workout_id` | string | optional | Single workout ID to delete |
| `plan_id` | string | optional | Plan ID to delete all workouts from |
| `week_number` | integer | optional | Specific week to delete (with plan_id) |

### `get_garmin_scheduled_workouts`

CLI: `garmin-db training-plan scheduled-workouts`

Fetch scheduled workouts (including adaptive plan workouts) from the Garmin Connect calendar-service for a date range. Returns workout-type calendar items sorted by date.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | string | **required** | Inclusive start date (YYYY-MM-DD) |
| `end_date` | string | **required** | Inclusive end date (YYYY-MM-DD) |

## Athlete

### `save_athlete_profile`

CLI: `garmin-db athlete save-profile`

Save the athlete profile (current focus, race goals, and season retrospectives) as a single object to DuckDB. The profile row is upserted on user_id; goals and retrospectives are fully replaced per user_id.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `profile` | object | **required** | Profile JSON with user_id (default 'default'), current_focus, focus_notes, goals (list of {race_name, race_date, priority, goal_type, distance_km, target_time_seconds, status, notes}), and retrospectives (list of {season_label, period_start, period_end, narrative, key_learnings}). |

### `get_athlete_profile`

CLI: `garmin-db athlete get-profile`

Get the athlete profile (current focus, goals, and retrospectives) merged into a single object. Returns an empty structure (current_focus=None, goals=[], retrospectives=[]) when no profile is registered.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `user_id` | string | optional | Profile owner identifier (default: 'default') |

### `save_weekly_review`

CLI: `garmin-db athlete save-review`

Save a weekly training review to DuckDB. Each save appends a new version for (user_id, week_start_date) instead of overwriting, so re-running the same week keeps prior versions as history; the latest version is treated as canonical. The free-form review_data payload is stored as JSON.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `review` | object | **required** | Review JSON with user_id (default 'default'), week_start_date, week_end_date, review_date, review_data (object, e.g. {this_week, garmin_next_week, verdict, recommendations, overall}), agent_name, and agent_version. |

### `get_weekly_review`

CLI: `garmin-db athlete get-review`

Get a single weekly review (the latest version of its week). When week_start_date is omitted, the latest version of the most recent week is returned. review_data is JSON-decoded back into an object. Returns null when no matching review exists.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `week_start_date` | string | optional | Week start date (YYYY-MM-DD). When omitted, returns the most recent review. |
| `user_id` | string | optional | Profile owner identifier (default: 'default') |

## Race

### `get_race_readiness`

CLI: `garmin-db race readiness`

Get race readiness: the athlete's current VDOT (from recent fitness), VDOT-based race-time predictions (5k/10k/half/full in seconds), the active race goal (priority A / active preferred, else the nearest future race), and a progress block with the predicted goal-distance time, gap to target (seconds; positive = behind target), pace gap (sec/km), weeks remaining, and a status (ahead/on_track/behind). Returns empty predictions when no VDOT can be derived and a null goal/progress when no goal is registered.

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

## Durability

### `get_activity_durability`

CLI: `garmin-db durability activity`

Get one activity's cardiac decoupling: the second-half vs first-half HR/speed efficiency ratio (split at the time-series timestamp midpoint). Returns activity_id, activity_date, distance_km, decoupling_pct ((back HR/speed)/(front HR/speed)-1; >5% suggests insufficient aerobic durability), pace_fade_pct (back/front pace ratio), and nullable second-half form fades gct_fade_pct / vo_fade_pct / vr_fade_pct (back-vs-front ground-contact time / vertical oscillation / vertical ratio; null on devices lacking the metric). Returns null when HR or speed data is missing.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | integer | **required** | Activity ID to compute first-half vs second-half decoupling for. |

### `get_durability_trend`

CLI: `garmin-db durability trend`

Get the longitudinal cardiac-decoupling trend across long runs in a date window. Only activities with total_distance_km >= min_distance_km (default 15) are included. Returns an activities array (per-activity durability, date ascending) and a trend block with decoupling_slope_per_day (regressed on elapsed days), data_points, direction (improving when decoupling falls / worsening / stable / insufficient_data), plus second-half form decay: gct_fade_slope_per_day (GCT fade regressed over runs with form data; null when <2 such runs) and form_direction (same classification applied to GCT fade).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | string | **required** | Inclusive window start date (YYYY-MM-DD). |
| `end_date` | string | **required** | Inclusive window end date (YYYY-MM-DD). |
| `min_distance_km` | number | optional (default `15.0`) | Minimum total_distance_km for an activity to qualify as a long run (default: 15.0). Shorter runs are excluded. |

## strength

### `ingest_strength_sessions`

CLI: `garmin-db strength ingest`

Discover strength_training (補強) activities from the Garmin Connect API in a date window and upsert summary rows into the strength_sessions table. Catch-up aware: omit start_date to ingest from the latest stored strength date (re-fetched so recent edits are reflected), or end_date - 30 days when none exist yet; omit end_date to default to today. Discovery uses the activity list filtered to typeKey == 'strength_training' (runs with distance are excluded). Each session's ACTIVE exercise sets are aggregated into a category_counts map (e.g. {"CRUNCH": 4, "PLANK": 7}). Idempotent: re-ingesting an activity overwrites its row. Returns inserted, updated, activity_ids, and the resolved window {start, end}.

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

Differential catch-up ingest across the running, weight and strength domains in a single call. Resolves an independent window per domain (each table advances at its own pace): end_date or today as the shared end, and per-domain start = start_date (when given) or that domain's latest stored date, or end_date - 30 days when the domain is empty. running delegates to ingest_running_activities, weight to ingest_weight_range, strength to ingest_strength_sessions. Pass domains to ingest a subset (default: all three). A failure in one domain is isolated (its entry carries an error) while the others complete. Returns each requested domain's result plus a window map of {domain: {start, end}}.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | string | optional | Inclusive shared window start date (YYYY-MM-DD). When omitted, each domain resolves its own start from its latest stored date (or end_date - 30 days when that domain is empty). |
| `end_date` | string | optional | Inclusive window end date (YYYY-MM-DD). Defaults to today when omitted. |
| `domains` | array[string] | optional | Subset of domains to ingest. Defaults to all of running, weight, strength. Domains not listed are skipped. |

## Server

### `get_server_info`

Get diagnostic info about the running MCP server (server_dir). Use to verify which directory the server is running from.

_No parameters._

### `reload_server`

Restart the worker to pick up the latest code. The launcher process stays alive, so the MCP connection is preserved (no reconnect needed).

_No parameters._
