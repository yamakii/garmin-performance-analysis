# Analysis Agents Common Rules

5 section analysis agents (split, phase, efficiency, environment, summary) share these rules.

## Data Access

- Use MCP tools only (`mcp__garmin-db__*`)
- NEVER direct DuckDB queries or file access

## Pre-fetched Context (事前取得コンテキスト)

When the orchestrator provides a "事前取得コンテキスト" JSON in the prompt, **use it instead of calling redundant MCP tools**:

- `training_type` → skip `get_hr_efficiency_analysis()` if you only need training_type
- `temperature_c`, `humidity_pct`, `wind_mps`, `wind_direction` → skip `get_weather_data()`
- `terrain_category`, `avg_elevation_gain_per_km`, `total_elevation_gain`, `total_elevation_loss` → skip `get_splits_elevation(statistics_only=True)`
- `planned_workout` → not nullの場合、プランのワークアウト目標を含む（workout_type, target_hr_low/high, target_pace_low/high等）
  - **プラン目標がある場合は、Garminのtraining_typeより優先して評価基準とする**
  - nullの場合は従来通りtraining_typeベースで評価（アドホックラン）
- `zone_percentages` (dict: zone1-zone5), `primary_zone`, `zone_distribution_rating`, `hr_stability`, `aerobic_efficiency`, `training_quality`, `zone2_focus`, `zone4_threshold_work` → skip `get_hr_efficiency_analysis()` completely (C1)
- `form_scores` (dict: gct/vo/vr star_rating+score, integrated_score, overall_score, overall_star_rating) → skip `get_form_evaluations()` if you only need scores (C2)
- `phase_structure` (dict: pace_consistency, hr_drift_percentage, cadence_consistency, fatigue_pattern, warmup/run/recovery/cooldown avg_pace+avg_hr) → skip `get_performance_trends()` if you only need phase overview (C3)

**Rules:**
- If you need MORE data than what's in the context (e.g., full evaluation_text from form_evaluations, or detailed per-split data from performance_trends), call the MCP tool normally
- If the context provides everything you need for a field, do NOT call the corresponding MCP tool
- The context is read-only reference data — always trust it as accurate

## Independence

- Each agent operates independently - do NOT reference other section analyses
- Do NOT create dependencies between agents
- Get all needed data from MCP tools directly

## Output Language

- Analysis text: Japanese
- Code, key names, field names: English

## Output Save

- Write analysis results as JSON file to the temp directory path given in the prompt
- File path: `{temp_dir}/{section_type}.json`
- JSON structure: `{"activity_id": <int>, "activity_date": "<YYYY-MM-DD>", "section_type": "<type>", "analysis_data": {...}}`
- Do NOT include metadata - it is auto-generated at merge time
- Do NOT call `insert_section_analysis_dict()` directly — the orchestrator handles DB insertion

## Star Rating Format

Format: `(rating N.N/5.0)` with star marks and numeric score on a new line.

Example: `(stars 4.0/5.0)`

## Architecture Constraints (from architecture-preferences.md)

- HR zones: always use Garmin-native zones from `heart_rate_zones` table (NEVER calculate from formulas)
- Dates: DuckDB returns `datetime.date` → stringify before JSON/MCP output

## Writing Style

- Natural Japanese sentences (avoid noun-ending style / taitomei)
- Coach-like tone: praise strengths, suggest improvements positively
- Use specific numbers in text (e.g., "XX sec/km faster")
- Keep comments concise (1-2 sentences per point)
- Data formatting is NOT needed - data is displayed separately in reports
