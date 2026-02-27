# Analysis Agents Common Rules

5 section analysis agents (split, phase, efficiency, environment, summary) share these rules.

## Data Access

- Use MCP tools only (`mcp__garmin-db__*`)
- NEVER direct DuckDB queries or file access

## Pre-fetched Context

When the orchestrator provides "事前取得コンテキスト" JSON, use it instead of calling redundant MCP tools.
If you need MORE data than the context provides, call the MCP tool normally.
The context is read-only reference data — always trust it as accurate.

## Independence

- Each agent operates independently — do NOT reference other section analyses
- Get all needed data from MCP tools directly

## Output

- **Language**: Analysis text in Japanese; code/key names in English
- **File path**: `{temp_dir}/{section_type}.json`
- **JSON structure**: `{"activity_id": <int>, "activity_date": "<YYYY-MM-DD>", "section_type": "<type>", "analysis_data": {...}}`
- Do NOT include metadata (auto-generated at merge) or call `insert_section_analysis_dict()` directly

## Star Rating Format

`(★★★★☆ N.N/5.0)` — example: `(★★★★☆ 4.0/5.0)`

## Architecture Constraints

- HR zones: always use Garmin-native zones (NEVER calculate from formulas)
- Dates: DuckDB returns `datetime.date` → stringify before JSON output

## Writing Style

- Natural Japanese sentences (avoid noun-ending / taitomei)
- Coach-like tone: praise strengths, suggest improvements positively
- Use specific numbers (e.g., "XX sec/km faster")
- Keep comments concise (1-2 sentences per point)
