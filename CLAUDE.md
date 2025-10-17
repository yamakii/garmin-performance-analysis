# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Overview

Garmin running performance analysis system with **DuckDB-first architecture** and **MCP-first tool usage**.

**System Pipeline:** Raw Data (API) → DuckDB → MCP Tools → Analysis → Reports

**Key Features:**
- DuckDB normalized storage (11 tables, 100+ activities)
- Token-optimized MCP tools (70-98.8% reduction)
- 5 specialized analysis agents
- Japanese reports (code/docs in English)

**Two Use Cases:**
1. **Activity Analysis** - Analyze running data using MCP tools (→ See "For Activity Analysis")
2. **Tool Development** - Develop/improve the analysis system (→ See "For Tool Development")

---

## For Activity Analysis

**When:** Analyzing activities, generating reports, finding trends, comparing workouts.

### Critical Rules

**MANDATORY: Use Garmin DB MCP tools for ALL performance data access.**

- ✅ USE: `mcp__garmin-db__*` functions (see tool list below)
- ❌ NEVER: Direct DuckDB queries (`duckdb.connect()`, SQL queries)
- ❌ NEVER: Direct file access to `data/database/*.duckdb`

**Why:** MCP tools provide 70-98.8% token reduction and standardized data access.

### Common Analysis Workflows

**1. Single Activity Analysis**
```
1. Get activity ID: mcp__garmin-db__get_activity_by_date(date="2025-10-15")
2. Get performance: mcp__garmin-db__get_performance_trends(activity_id)
3. Get splits: mcp__garmin-db__get_splits_pace_hr(activity_id, statistics_only=True)
4. Get form: mcp__garmin-db__get_form_efficiency_summary(activity_id)
5. Get HR zones: mcp__garmin-db__get_hr_efficiency_analysis(activity_id)
```

**2. Multi-Activity Trends**
```
1. Get IDs for date range using analyze_performance_trends
2. Compare: mcp__garmin-db__analyze_performance_trends(
     metric="pace",
     start_date="2025-10-01",
     end_date="2025-10-31",
     activity_ids=[...]
   )
```

**3. Similar Workout Comparison**
```
mcp__garmin-db__compare_similar_workouts(
  activity_id=12345,
  pace_tolerance=0.1,
  distance_tolerance=0.1
)
```

### Essential MCP Tools

**Activity Lookup:**
- `get_activity_by_date(date)` - Get activity ID from date
- `get_date_by_activity_id(activity_id)` - Get date from ID

**Performance Metrics:**
- `get_performance_trends(activity_id)` - Pace consistency, HR drift, phases
- `get_splits_pace_hr(activity_id, statistics_only=True/False)` - Pace/HR data
- `get_splits_form_metrics(activity_id, statistics_only=True/False)` - GCT/VO/VR
- `get_splits_elevation(activity_id, statistics_only=True/False)` - Terrain data

**Physiological Data:**
- `get_form_efficiency_summary(activity_id)` - Form metrics summary
- `get_hr_efficiency_analysis(activity_id)` - HR zones + training type
- `get_heart_rate_zones_detail(activity_id)` - Zone boundaries/distribution
- `get_vo2_max_data(activity_id)` - VO2 max estimation
- `get_lactate_threshold_data(activity_id)` - Lactate threshold

**Advanced Analysis:**
- `analyze_performance_trends(metric, start_date, end_date, activity_ids)` - Cross-activity trends
- `compare_similar_workouts(activity_id, ...)` - Find similar past workouts
- `extract_insights(keywords=["改善", "課題"])` - Search analysis reports
- `get_interval_analysis(activity_id)` - Work/Recovery segments
- `detect_form_anomalies_summary(activity_id)` - Form anomalies (95% token reduction)
- `get_split_time_series_detail(activity_id, split_number)` - Second-by-second data (98.8% reduction)

**Token Optimization:**
- Use `statistics_only=True` for overview/trends (80% reduction)
- Use `statistics_only=False` only when per-split details needed
- Use `detect_form_anomalies_summary()` before `get_form_anomaly_details()`

### Prohibited Practices

❌ **NEVER do these:**
- Direct DuckDB queries: `conn = duckdb.connect(...)`
- Direct file reads: `Read("/path/to/database/garmin_performance.duckdb")`
- Using deprecated tools: `get_splits_all()`, old `get_section_analysis()`
- Querying non-existent columns (check schema if unsure)

---

## For Data Analysis

**When:** Statistical analysis over multiple months, performance trends, growth rate calculation, race time prediction.

### Critical Rules

**MANDATORY: Use export + parquet + Python for bulk data analysis.**

- ✅ USE: `mcp__garmin-db__export()` with parquet format
- ✅ THEN: Python (pandas/numpy/scipy) for analysis
- ✅ OR: Use **data-analyst agent** for automated workflow
- ❌ NEVER: Multiple individual MCP calls for same data
- ❌ NEVER: CSV format for 50+ rows (use parquet)

**Why:** Single export is 10-100x more efficient than multiple MCP calls.

### Data Analyst Agent

**For 10+ activities, use the data-analyst agent:**

```bash
# Invoke the agent for bulk analysis
Task("data-analyst", "Analyze my 5-month progression")
```

**The agent handles:**
1. **STEP 1: PLAN** - Extract date range, check schema, design SQL
2. **STEP 2: EXPORT** - Single parquet export (~25 tokens)
3. **STEP 3: CODE** - Python analysis with pandas/scipy
4. **STEP 4: RESULT** - Validate output (<1KB JSON)
5. **STEP 5: INTERPRET** - Natural language explanation

**Token Efficiency:**
- Old approach: 107 activities × 2 calls = 214 MCP calls = **~55,000 tokens**
- New approach: 1 schema check + 1 export + 1 analysis = **~175 tokens**
- **99.7% token reduction**

**Use Cases:**
- **Time Series Analysis**: "Analyze my 5-month progression" → Linear regression, growth rate
- **Race Prediction**: "Predict my half-marathon time in 3 months" → VDOT, Riegel formula
- **Comparative Analysis**: "Compare August vs October performance" → t-test, effect size

### Standard Workflow (Manual)

**1. Schema Confirmation** (once per session):
```sql
-- Check available columns
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_name IN ('activities', 'splits', 'form_efficiency')
ORDER BY table_name, ordinal_position
```

**2. Export to Parquet**:
```python
# Single query with JOINs
handle = mcp__garmin-db__export(
    query="""
    WITH splits_agg AS (
      SELECT activity_id, AVG(pace_seconds_per_km) as avg_pace
      FROM splits GROUP BY activity_id
    )
    SELECT a.*, s.avg_pace, fe.gct_average, he.training_type
    FROM activities a
    LEFT JOIN splits_agg s ON a.activity_id = s.activity_id
    LEFT JOIN form_efficiency fe ON a.activity_id = fe.activity_id
    LEFT JOIN hr_efficiency he ON a.activity_id = he.activity_id
    WHERE a.activity_date >= '2025-05-01'
      AND a.total_distance_km > 1.0
    ORDER BY a.activity_date
    """,
    format="parquet",
    max_rows=1000
)
```

**3. Python Analysis**:
```python
import pandas as pd
import numpy as np
from scipy import stats

# Read parquet
df = pd.read_parquet(handle)

# Time series analysis
df['activity_date'] = pd.to_datetime(df['activity_date'])
df = df.sort_values('activity_date')

# Calculate growth rate
slope, intercept, r_value, p_value, std_err = stats.linregress(
    range(len(df)), df['avg_pace']
)

# Project future performance
# ... analysis continues
```

### Anti-Patterns (DON'T DO THIS)

❌ **Multiple individual calls**:
```python
# BAD: 100 activities = 100+ MCP calls
for date in date_range:
    activity = get_activity_by_date(date)  # ❌ Token-heavy
    performance = get_performance_trends(activity_id)  # ❌ Slow
    splits = get_splits_pace_hr(activity_id)  # ❌ Error-prone
```

❌ **Trial-and-error with column names**:
```python
# BAD: Multiple failed queries
export(query="SELECT avg_hr FROM activities...")  # ❌ Error
export(query="SELECT hr FROM activities...")      # ❌ Error
export(query="SELECT avg_heart_rate FROM...")    # ✅ Finally works
```

❌ **CSV for large datasets**:
```python
# BAD: CSV is inefficient for 100+ rows
export(query="...", format="csv")  # ❌ Slow parsing
```

### Best Practices

✅ **Use data-analyst agent for 10+ activities**:
```python
# Agent handles schema check, export, analysis, interpretation
Task("data-analyst", "Analyze my 5-month progression")
```

✅ **Check schema first** (manual approach):
```sql
-- Always verify column names before writing query
SELECT column_name FROM information_schema.columns
WHERE table_name = 'activities'
```

✅ **Use CTEs for aggregation**:
```sql
-- Aggregate in SQL, not in Python
WITH splits_agg AS (
  SELECT activity_id, AVG(pace_seconds_per_km) as avg_pace
  FROM splits GROUP BY activity_id
)
SELECT a.*, s.avg_pace FROM activities a
LEFT JOIN splits_agg s ON a.activity_id = s.activity_id
```

✅ **Parquet for efficiency**:
```python
# Fast, compact, preserves data types
export(query="...", format="parquet", max_rows=1000)
```

### Common Patterns

**Time Series Analysis** (5+ months progression):
1. Export: activities + splits + form + HR efficiency
2. Calculate: linear regression, growth rate, correlation
3. Visualize: matplotlib/seaborn (optional)
4. Predict: extrapolate to race date

**Performance Prediction** (race time estimation):
1. Export: performance_trends + vo2_max + lactate_threshold
2. Model: VDOT calculation, Riegel formula
3. Adjust: for weather, terrain, training load
4. Output: predicted pace/time with confidence intervals

**Comparative Analysis** (before/after training block):
1. Export: Two date ranges
2. Calculate: mean, median, std for key metrics
3. Test: t-test or Mann-Whitney U for significance
4. Report: effect size, practical significance

### Example: 5-Month Progression Analysis (Manual)

```python
# 1. Export with schema verification
schema = export(query="""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'activities'
""", format="parquet")

# 2. Export actual data (single query)
handle = export(query="""
    WITH splits_agg AS (
      SELECT activity_id,
             AVG(pace_seconds_per_km) as avg_pace,
             AVG(heart_rate) as avg_hr
      FROM splits GROUP BY activity_id
    )
    SELECT
      a.activity_id,
      a.activity_date,
      a.total_distance_km,
      a.avg_pace_seconds_per_km,
      s.avg_pace as splits_avg_pace,
      s.avg_hr,
      fe.gct_average,
      he.training_type
    FROM activities a
    LEFT JOIN splits_agg s ON a.activity_id = s.activity_id
    LEFT JOIN form_efficiency fe ON a.activity_id = fe.activity_id
    LEFT JOIN hr_efficiency he ON a.activity_id = he.activity_id
    WHERE a.activity_date >= '2025-05-01'
      AND a.total_distance_km > 1.0
    ORDER BY a.activity_date
""", format="parquet", max_rows=500)

# 3. Analyze with Python
import pandas as pd
from scipy import stats

df = pd.read_parquet(handle)
df['week'] = pd.to_datetime(df['activity_date']).dt.isocalendar().week

# Growth rate
slope, _, r_value, p_value, _ = stats.linregress(
    range(len(df)), df['avg_pace']
)

# Project to race date
weeks_to_race = 8
predicted_pace = df['avg_pace'].iloc[-1] + slope * (weeks_to_race * 3)  # 3 runs/week

print(f"Growth rate: {slope:.2f} sec/km per activity")
print(f"Predicted pace in {weeks_to_race} weeks: {predicted_pace/60:.2f} min/km")
```

### Prohibited Practices

❌ **NEVER do these:**
- Multiple get_activity_by_date() in loop (use export once)
- CSV format for 50+ rows (use parquet)
- Skip schema check and guess column names
- Read exported CSV immediately (defeats purpose of export)

---

## For Tool Development

**When:** Modifying code, adding features, fixing bugs, running tests, managing projects.

### Critical Rules

**MANDATORY MCP Usage:**
- ✅ Code files (`.py`, `.ts`): **Serena MCP only** (symbol-aware editing)
- ✅ Performance data: **Garmin DB MCP only** (token-optimized queries)
- ✅ Text files (`.md`, `.json`, `.txt`): Direct Read/Edit/Write OK

**MANDATORY Git Worktree:**
- ✅ Planning: Main branch (no worktree)
- ✅ Implementation: Git worktree + `uv sync --extra dev` + activate Serena
- ✅ Completion: Merge to main, remove worktree

**Why:** Serena provides symbol-aware navigation, refactoring, and test-aware editing.

### Development Workflow

**1. Environment Setup**
```bash
# Initial setup (main branch)
uv sync --extra dev  # Installs pytest-xdist, black, ruff, mypy, pre-commit

# For new feature (worktree)
git worktree add -b feature/name ../garmin-feature-name main
cd ../garmin-feature-name
uv sync --extra dev
direnv allow  # Auto-loads .env

# MANDATORY: Activate Serena for agents
mcp__serena__activate_project("/absolute/path/to/worktree")
```

**2. Development Process (TDD)**
```
Planning (main) → Implementation (worktree) → Completion (merge)

Agents:
- project-planner: Creates planning.md, GitHub Issue
- tdd-implementer: TDD cycle (Red → Green → Refactor)
- completion-reporter: Generates completion_report.md
```

**3. Code Quality**
```bash
uv run black .                # Format
uv run ruff check .           # Lint
uv run mypy .                 # Type check
uv run pytest                 # All tests
uv run pytest -m unit         # Unit only
```

**4. Git Workflow**
```bash
# Pre-commit runs automatically
git add .
git commit -m "feat: description

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"

# After merge
cd /path/to/main
git worktree remove ../garmin-feature-name
```

### Serena MCP Tools

**Navigation:**
- `list_dir(path, recursive)` - List files
- `get_symbols_overview(file_path)` - File symbol overview
- `find_symbol(name_path, relative_path)` - Find classes/functions
- `find_referencing_symbols(name_path, relative_path)` - Find references

**Editing:**
- `replace_symbol_body(name_path, relative_path, body)` - Replace function/class
- `insert_after_symbol(name_path, relative_path, body)` - Add after symbol
- `insert_before_symbol(name_path, relative_path, body)` - Add before symbol
- `replace_regex(relative_path, regex, repl)` - Regex replacement

**Memory:**
- `read_memory(memory_name)` - Read project knowledge
- `write_memory(memory_name, content)` - Save project knowledge

### Data Processing Scripts

**DuckDB Regeneration** (after schema changes):
```bash
# Single table
uv run python tools/scripts/regenerate_duckdb.py --tables splits --activity-ids 12345

# Multiple tables with date range
uv run python tools/scripts/regenerate_duckdb.py \
  --tables splits form_efficiency \
  --start-date 2025-10-01 --end-date 2025-10-31

# Force re-insertion (delete + insert)
uv run python tools/scripts/regenerate_duckdb.py --tables splits --force

# Full database regeneration (DANGEROUS - requires user approval)
uv run python tools/scripts/regenerate_duckdb.py --delete-db
```

**Raw Data Fetching:**
```bash
# Fetch missing raw data
uv run python tools/scripts/bulk_fetch_raw_data.py --start-date 2025-10-01

# Fetch activity details only
uv run python tools/scripts/bulk_fetch_activity_details.py --activity-ids 12345 67890
```

### Testing Strategy

**CRITICAL: Tests must NEVER depend on real production data.**

**Test Types:**
1. **Unit** - `@pytest.fixture` mocks, no I/O, <100ms
2. **Integration** - `pytest-mock` (`mocker.Mock()`), mock DuckDB connections
3. **Performance** - Real data OK, but skip if unavailable

**Example:**
```python
@pytest.fixture
def mock_reader_factory(mocker):
    def _create(data):
        reader = mocker.Mock()
        reader.get_section_analysis.return_value = data
        return reader
    return _create

def test_analysis(mock_reader_factory):
    reader = mock_reader_factory({"rating": "★★★★☆"})
    assert reader.get_section_analysis(12345, "phase")["rating"] == "★★★★☆"
```

### Project Management

**GitHub Issue Integration:**
- All projects tracked as Issues (Open = Active, Closed = Archived)
- Link Issues in planning.md, reference in commits (`#123`)

**Project Structure:**
```
docs/project/
├── 2025-XX-XX_project_name/    # Active
│   ├── planning.md
│   └── completion_report.md
└── _archived/                  # Completed
    └── 2025-XX-XX_old_project/
```

### Prohibited Practices

❌ **NEVER do these:**
- Edit code without Serena MCP: `Edit("tools/ingest/worker.py", ...)`
- Implement on main branch (use worktree)
- Delete database without user approval: `rm *.duckdb`, `--delete-db`
- Tests depending on real data: `conn.execute("SELECT * FROM activities")`
- Remove worktree without checking status: `git worktree remove --force`

---

## Common Reference

### Architecture

**Pipeline:** API → Raw JSON → DuckDB → MCP Tools → Analysis → Markdown Reports

**Key Classes:**
- `GarminIngestWorker`: API fetching + raw data → DuckDB insertion
- `GarminDBWriter`: DuckDB insertion (11 normalized tables)
- `ReportGeneratorWorker`: Template-based report generation

**DuckDB Schema (11 tables):**
- Metadata: `activities`, `body_composition`
- Performance: `splits`, `performance_trends`, `time_series_metrics` (26 metrics × 1000-2000 rows)
- Physiology: `form_efficiency`, `hr_efficiency`, `heart_rate_zones`, `vo2_max`, `lactate_threshold`
- Analysis: `section_analyses` (5 agent results per activity)

### Directory Structure

```
garmin-performance-analysis/
├── data/                      # GARMIN_DATA_DIR (configurable via .env)
│   ├── raw/                   # API responses (8 files/activity)
│   └── database/              # garmin_performance.duckdb
├── result/                    # GARMIN_RESULT_DIR (configurable via .env)
│   ├── individual/            # YEAR/MONTH/YYYY-MM-DD_id.md
│   └── monthly/               # Monthly trends
├── tools/                     # Processing pipeline
│   ├── ingest/                # API fetching
│   ├── database/              # DuckDB operations
│   ├── reporting/             # Report generation
│   └── scripts/               # Maintenance scripts
├── docs/project/              # Project management
│   ├── 2025-*_*/              # Active projects
│   └── _archived/             # Completed projects
└── .claude/                   # Agents + slash commands
```

### Agent System

**5 Section Analysis Agents (run in parallel via Task tool):**
1. **split-section-analyst**: 1km split analysis (pace, HR, form)
2. **phase-section-analyst**: Phase evaluation (warmup/run/cooldown, uses training type)
3. **summary-section-analyst**: Activity type + overall assessment
4. **efficiency-section-analyst**: Form (GCT/VO/VR) + HR efficiency
5. **environment-section-analyst**: Environmental impact (weather, terrain)

**Training Type-Aware Evaluation (phase-section-analyst):**
- **low_moderate**: No warmup/cooldown required, positive tone
- **tempo_threshold**: Warmup/cooldown recommended, educational tone
- **interval_sprint**: Warmup/cooldown required, injury warnings

**1 Data Analysis Agent:**
- **data-analyst**: Bulk analysis for 10+ activities (99.7% token reduction)
  - Time series analysis (5-month progression, growth rate)
  - Race prediction (VDOT, Riegel formula, confidence intervals)
  - Comparative analysis (t-test, effect size, period comparison)

**3 Development Agents:**
- **project-planner**: Creates planning.md, GitHub Issue
- **tdd-implementer**: TDD cycle in worktree
- **completion-reporter**: Generates completion_report.md

### Critical Data Sources

**Split Analysis:**
- ✅ `splits.json` (lapDTOs) - 1km lap data
- ❌ `typed_splits.json` - Aggregated only

**Temperature:**
- ✅ `weather.json` - External weather station
- ❌ `splits.json` temperature - Device temp (+5-8°C body heat)

**Elevation:**
- Source: `lapDTOs` → DuckDB
- Classification: 平坦/起伏/丘陵/山岳

### DuckDB Safety Rules

**CRITICAL: Database contains 100+ activities. NEVER delete without user approval.**

**Error Protocol:**
1. ✅ Check integrity first: `conn = duckdb.connect(path, read_only=True)`
2. ✅ Try alternatives: Regenerate specific tables, use new Python process
3. ❌ NEVER propose `--delete-db` as first solution
4. ❌ NEVER delete without explicit user confirmation

**Remember:** INSERT/UPDATE errors ≠ data corruption. Check data first, delete last.

---

## Quick Reference

**Environment:**
```bash
cp .env.example .env  # Configure GARMIN_DATA_DIR, GARMIN_RESULT_DIR
direnv allow          # Auto-load environment
```

**Common Patterns:**
- Analysis: Use MCP tools only
- Development: Serena MCP + worktree mandatory
- Testing: Mock all data dependencies
- Database: Read-only checks before modifications
