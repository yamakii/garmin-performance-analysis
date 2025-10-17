# Data Analyst Agent - Implementation Plan

**Created**: 2025-10-17
**Updated**: 2025-10-17 (MCP Architecture Knowledge Integration)
**Status**: Planning
**Priority**: Medium (improves workflow efficiency)
**Base Project**: 2025-10-16_duckdb_mcp_llm_architecture (#25)

## Overview

Create a specialized agent for bulk data analysis that uses the **DuckDB × MCP × LLM Architecture** (from #25) to efficiently analyze multi-month performance data while protecting LLM context.

**Foundation**: Built on top of Phase 0-3 of `duckdb_mcp_llm_architecture` project, which established:
- MCP Server Functions: `export()`, `profile()`, `histogram()`, `materialize()`
- Python Helper Functions: `safe_load_export()`, `safe_summary_table()`, `safe_json_output()`, `validate_output()`
- LLM Behavior Rules: Documented in `docs/LLM_BEHAVIOR_RULES.md`
- Proven token reduction: 95.8-98.7% in benchmark tests

## Motivation

**Problem**: Current workflow for multi-month analysis is inefficient:
- Multiple individual MCP calls (100+ for 5-month analysis)
- Trial-and-error with column names (5+ failed queries)
- CSV format for large datasets (slow, inefficient)
- High token usage (10-100x more than necessary)

**Solution**: Specialized agent that:
- Always checks schema first
- Uses single export with parquet
- Performs analysis in Python
- Follows documented best practices

## Requirements

### Functional Requirements

1. **Schema-Aware Query Building**
   - Check information_schema before writing queries
   - Validate column names exist
   - Build correct JOINs based on available tables

2. **Efficient Data Export**
   - Single export call with CTEs for aggregation
   - Parquet format (not CSV)
   - Appropriate max_rows setting

3. **Python Analysis**
   - Time series analysis (growth rate, trends)
   - Performance prediction (VDOT, Riegel formula)
   - Statistical tests (t-test, correlation)
   - Visualization (matplotlib/seaborn) optional

4. **Common Analysis Types**
   - 5+ month progression analysis
   - Race time prediction
   - Training phase comparison
   - Correlation analysis (pace vs HR, form vs pace)

### Non-Functional Requirements

1. **Efficiency**: 10-100x token reduction vs individual MCP calls
2. **Reliability**: Schema validation prevents query errors
3. **Maintainability**: Follows CLAUDE.md guidelines
4. **Usability**: Simple invocation for common tasks

## Design

### Agent Location

`.claude/agents/data-analyst.md`

### Agent Structure

```markdown
# Data Analyst Agent

Specialized in bulk performance data analysis using the **DuckDB × MCP × LLM Architecture**.

**Base Architecture**: Phase 0-3 of #25 (duckdb_mcp_llm_architecture)
**Core Principle**: PLAN → EXPORT → CODE → RESULT → INTERPRET

## When to Use

Call this agent when:
- Analyzing 10+ activities at once
- Calculating growth rates over weeks/months (5-month progression, etc.)
- Predicting race times from training data
- Comparing performance across time periods
- Statistical analysis (correlation, regression, t-tests)
- Time series analysis with 100+ data points

DON'T call for:
- Single activity analysis (use regular MCP tools: get_performance_trends, etc.)
- Simple lookups (get_activity_by_date, get_splits_pace_hr with statistics_only=True)
- Report generation (use section analysis agents)
- Data with <50 rows (direct MCP tools more efficient)

## Architecture Awareness

This agent follows the **Responsibility Separation** principle:

1. **LLM (ME)**:
   - ✅ Data request planning (PLAN)
   - ✅ Result interpretation (INTERPRET)
   - ❌ NO direct data reading
   - ❌ NO full data展開

2. **MCP Server**:
   - ✅ Data extraction (export to Parquet)
   - ✅ Summary statistics (profile/histogram)
   - ❌ NO raw data in response (handle only)

3. **Python Executor**:
   - ✅ Data processing (pandas/numpy/scipy)
   - ✅ Visualization (matplotlib)
   - ❌ NO full data output (summary only)

## Workflow (5 Steps)

### Step 1: PLAN
- Extract: date range, metrics, analysis type
- Check schema: `information_schema.columns` for table structure
- Design query: Single SQL with CTEs for aggregation

### Step 2: EXPORT (MCP)
- Use: `mcp__garmin-db__export(query, format="parquet")`
- Receive: **Handle only** (~100 bytes)
  ```json
  {
    "handle": "/tmp/garmin_exports/export_20251017_xxx.parquet",
    "rows": 107,
    "size_mb": 0.02,
    "columns": ["activity_id", "activity_date", "avg_pace", ...]
  }
  ```
- Token cost: ~25 tokens (not 10,000+ for raw data)

### Step 3: CODE (Python)
- Load: `safe_load_export(handle, max_rows=10000)`
- Process: pandas/numpy for time series, stats, regression
- Validate: Auto-check JSON <1KB, Table <10 rows
- Output: Summary JSON + plot path (if visualization)

### Step 4: RESULT (Validation)
- Auto-validation by `validate_output()`
- Size check: JSON <1KB, Table <10 rows
- If exceeded: Auto-trim + warning

### Step 5: INTERPRET (LLM)
- Receive: Summary JSON (~500 bytes, ~125 tokens)
- Interpret: Natural language explanation
- Report: Insights + recommendations

## Tools Available (MCP Architecture)

**Primary**:
- `mcp__garmin-db__export()` - Parquet export (handle only)
- `mcp__garmin-db__profile()` - Summary stats (optional, for pre-check)

**Python Execution**:
- `Bash(uv run python -c "...")` - Safe data processing
- `safe_load_export()` - Load with 10K row limit
- `safe_summary_table()` - DataFrame display (10 row limit)
- `safe_json_output()` - JSON output (1KB limit)

**Schema Check**:
- `export(query="SELECT column_name FROM information_schema.columns WHERE table_name='activities'")`
- Then `Read(handle)` to verify columns

**Prohibited**:
- ❌ Multiple `get_activity_by_date()` in loop
- ❌ CSV format for 50+ rows
- ❌ Direct data展開 in LLM context
- ❌ Skip schema check and guess column names

## Example Prompts

- "Analyze my progression over the last 5 months" ← **Main use case**
- "Predict my half marathon time based on recent training"
- "Compare my performance in August vs October"
- "Calculate correlation between pace and heart rate across 100 runs"
- "Show me the growth rate of my VO2 max over 6 months"

## Token Cost Efficiency

**Example: 5-month progression (107 activities)**

従来 (Multiple MCP calls):
- 107 × get_activity_by_date() = ~2,140 tokens
- 107 × get_performance_trends() = ~53,500 tokens
- Total: ~55,000 tokens

**With Architecture**:
- 1 × export() response (handle) = ~25 tokens
- 1 × Python summary JSON = ~125 tokens
- Total: ~150 tokens
- **Reduction: 99.7%** 🎉

## References

- Base Project: `docs/project/2025-10-16_duckdb_mcp_llm_architecture/`
- LLM Behavior Rules: `docs/LLM_BEHAVIOR_RULES.md`
- Architecture Guide: `CLAUDE.md` - "For Data Analysis" section
- Benchmarks: 95.8-98.7% token reduction proven
```

### Key Implementation Details

**Schema Validation Pattern**:
```python
# Always run this first
schema_handle = export(
    query="SELECT table_name, column_name, data_type FROM information_schema.columns WHERE table_name IN ('activities', 'splits', 'form_efficiency') ORDER BY table_name, ordinal_position",
    format="parquet"
)
# Read and validate before building main query
```

**Query Building Pattern**:
```python
# Use CTEs for aggregation in SQL
query = """
WITH splits_agg AS (
  SELECT activity_id, AVG(metric) as avg_metric
  FROM splits GROUP BY activity_id
)
SELECT a.*, s.avg_metric FROM activities a
LEFT JOIN splits_agg s ON a.activity_id = s.activity_id
WHERE a.activity_date >= ? AND a.activity_date <= ?
ORDER BY a.activity_date
"""
```

**Analysis Pattern**:
```python
import pandas as pd
from scipy import stats

df = pd.read_parquet(handle)
df['activity_date'] = pd.to_datetime(df['activity_date'])

# Calculate growth rate
slope, intercept, r_value, p_value, std_err = stats.linregress(
    range(len(df)), df['target_metric']
)

# Project to future date
weeks_ahead = ...
predicted = df['target_metric'].iloc[-1] + slope * weeks_ahead * runs_per_week
```

## Implementation Steps

### Phase 1: Agent Creation (30 min)
1. Create `.claude/agents/data-analyst.md`
2. Define agent prompt with:
   - Clear when-to-use criteria
   - Standard workflow steps
   - Available tools
   - Example prompts
3. Test with simple invocation

### Phase 2: Core Workflows (1 hour)
1. **Time Series Analysis**:
   - Export 3+ months of data
   - Calculate linear regression
   - Compute confidence intervals
   - Project to race date

2. **Performance Prediction**:
   - VDOT calculation from recent times
   - Riegel formula application
   - Adjustment for conditions

3. **Comparative Analysis**:
   - Two-period export
   - Statistical tests (t-test, Mann-Whitney)
   - Effect size calculation

### Phase 3: Testing (30 min)
1. Test with 5-month progression (current use case)
2. Test with race prediction
3. Test with comparative analysis
4. Verify token usage reduction

### Phase 4: Documentation (15 min)
1. Update CLAUDE.md reference to agent
2. Add agent to README (if exists)
3. Create example usage in docs

## Success Criteria

✅ **Efficiency**:
- 5-month analysis: <10 tool calls (vs 100+)
- Token usage: 10-20k tokens (vs 100k+)
- Execution time: <2 minutes

✅ **Reliability**:
- Zero column name errors (schema validation)
- Correct data types (parquet preserves)
- Reproducible results

✅ **Usability**:
- Single Task() call initiates analysis
- Clear progress reporting
- Actionable insights in output

## Alternative Approaches Considered

### Alt 1: Slash Command
```markdown
.claude/commands/analyze-progression.md
```
**Pros**: Simpler to invoke (`/analyze-progression 5 pace`)
**Cons**: Less flexible, harder to parameterize

**Decision**: Agent better for complex, multi-step analysis

### Alt 2: Python Script + Tool
```python
tools/scripts/analyze_progression.py
```
**Pros**: Reusable, testable
**Cons**: Not interactive, requires setup

**Decision**: Agent provides better UX for Claude Code users

### Alt 3: Enhanced MCP Tool
```python
mcp__garmin-db__analyze_progression(months=5, metric="pace")
```
**Pros**: Single tool call
**Cons**: Inflexible, hard to customize queries

**Decision**: Agent allows flexible queries + analysis

## Future Enhancements

**Phase 2** (after initial agent working):
- Visualization generation (matplotlib charts)
- Automated report generation
- Integration with section analysts
- Anomaly detection in trends

**Phase 3** (long-term):
- Machine learning models (sklearn)
- Seasonal pattern detection
- Fatigue accumulation modeling
- Optimal taper calculation

## Notes

- Agent should reference CLAUDE.md "For Data Analysis" section
- Should follow same style as existing agents (split-section-analyst, etc.)
- Consider making it proactive: detect when user asks for multi-month analysis

## References

- CLAUDE.md: "For Data Analysis" section
- Session 2025-10-17: Anti-pattern examples
- Existing agents: `.claude/agents/*.md`
