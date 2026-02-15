# MCP Data Access Rules

## Mandatory: Use Garmin DB MCP tools for ALL performance data access

- USE: `mcp__garmin-db__*` functions
- NEVER: Direct DuckDB queries (`duckdb.connect()`, SQL queries)
- NEVER: Direct file access to `data/database/*.duckdb`

**Why:** MCP tools provide 70-98.8% token reduction and standardized data access.

## Token Optimization

- Use `statistics_only=True` for overview/trends (67-80% reduction)
- Use `statistics_only=False` only when per-split details needed
- Use `get_splits_comprehensive()` for all 12 fields in one call
- Use `detect_form_anomalies_summary()` before `get_form_anomaly_details()`

## Data Analysis (10+ Activities)

For bulk analysis, use the export-based 5-step workflow:
1. **PLAN** - Design SQL with CTEs, check schema
2. **EXPORT** - `mcp__garmin-db__export(query, format="parquet")` (returns handle, ~25 tokens)
3. **CODE** - Write Python to `/tmp/analyze.py`, load parquet, return summary JSON
4. **RESULT** - `uv run python /tmp/analyze.py`, validate output <1KB
5. **INTERPRET** - Explain in natural language with actionable insights

Key principles: Single export with CTEs (NOT individual calls), summary output <1KB, include p-values + effect sizes.

See `docs/data-analysis-guide.md` for detailed examples and templates.
