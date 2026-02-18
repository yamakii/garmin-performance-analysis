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

**Rules:**
- If you need MORE data than what's in the context (e.g., full zone percentages from hr_efficiency), call the MCP tool normally
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
