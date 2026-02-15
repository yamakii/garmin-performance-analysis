# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Overview

Garmin running performance analysis system with **DuckDB-first architecture** and **MCP-first tool usage**.

**System Pipeline:** Raw Data (API) → DuckDB → MCP Tools → Analysis → Reports

**Key Features:**
- DuckDB normalized storage (12 tables, 100+ activities)
- Token-optimized MCP tools (70-98.8% reduction)
- 8 specialized agents (5 analysis + 3 development)
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
- `get_splits_comprehensive(activity_id, statistics_only=True/False)` - **NEW:** All split data (12 fields: pace, HR, form, power, cadence, elevation)
- `get_splits_pace_hr(activity_id, statistics_only=True/False)` - Pace/HR data (lightweight, backward compatible)
- `get_splits_form_metrics(activity_id, statistics_only=True/False)` - GCT/VO/VR (lightweight, backward compatible)
- `get_splits_elevation(activity_id, statistics_only=True/False)` - Terrain data

**Physiological Data:**
- `get_form_efficiency_summary(activity_id)` - Form metrics summary
- `get_form_evaluations(activity_id)` - **NEW:** Pace-corrected form evaluation with star ratings
- `get_form_baseline_trend(activity_id, activity_date)` - **NEW:** 1-month baseline coefficient comparison
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
- Use `statistics_only=True` for overview/trends (67-80% reduction)
- Use `statistics_only=False` only when per-split details needed
- NEW: `get_splits_comprehensive()` provides all 12 fields in one call (recommended for split-section-analyst)
- Use `detect_form_anomalies_summary()` before `get_form_anomaly_details()`

### Prohibited Practices

❌ **NEVER do these:**
- Direct DuckDB queries: `conn = duckdb.connect(...)`
- Direct file reads: `Read("/path/to/database/garmin_performance.duckdb")`
- Using deprecated tools: `get_splits_all()`, old `get_section_analysis()`
- Querying non-existent columns (check schema if unsure)

---

## For Data Analysis

**When:** Statistical analysis, multi-month trends, race prediction, adhoc queries involving 10+ activities.

### Workflow: DuckDB × MCP × Python Architecture

**For bulk analysis (10+ activities), use the optimized workflow documented in `docs/data-analysis-guide.md`.**

**Key Principles:**
1. **Token Efficiency**: 99.7% reduction (175 tokens vs 55,000 tokens)
2. **Schema Validation**: Always check column names before queries
3. **Single Export**: Use `mcp__garmin-db__export()` with CTEs, NOT individual calls
4. **Summary Output**: Return <1KB JSON, NOT raw DataFrames
5. **Statistical Rigor**: Include p-values + effect sizes

**5-Step Workflow:**
```
STEP 1: PLAN
  → Extract requirements (date range, metrics, analysis type)
  → Check schema with export() to avoid column errors
  → Design single SQL query with CTEs

STEP 2: EXPORT
  → Call mcp__garmin-db__export(query, format="parquet")
  → Receive handle only (~25 tokens), NOT raw data

STEP 3: CODE
  → Write Python analysis to /tmp/analyze.py
  → Load parquet, calculate stats, return summary JSON

STEP 4: RESULT
  → Execute with: uv run python /tmp/analyze.py
  → Validate output <1KB

STEP 5: INTERPRET
  → Receive summary JSON (~125 tokens)
  → Explain in natural language with actionable insights
```

**Example (5-Month Progression):**
```python
# STEP 1: Plan
query = """
WITH splits_agg AS (
  SELECT activity_id, AVG(pace_seconds_per_km) as avg_pace
  FROM splits GROUP BY activity_id
)
SELECT a.activity_date, a.total_distance_km, s.avg_pace
FROM activities a
LEFT JOIN splits_agg s ON a.activity_id = s.activity_id
WHERE a.activity_date >= '2025-05-01'
ORDER BY a.activity_date
"""

# STEP 2: Export
handle = mcp__garmin-db__export(query=query, format="parquet")

# STEP 3: Code + Execute
# (Write /tmp/analyze.py with regression analysis)
# uv run python /tmp/analyze.py

# STEP 5: Interpret
# "Improving by 3.2 sec/km/week (p<0.01), reach goal in 8 weeks"
```

**Common Patterns:**
- Growth rate: Linear regression on pace over time
- Race prediction: VDOT calculation + Riegel formula
- Period comparison: t-test + Cohen's d effect size
- Injury risk: Training load analysis + consecutive hard runs

**Helper Tools:**
- `mcp__garmin-db__profile()` - Check data size before export
- `mcp__garmin-db__histogram()` - Analyze distribution patterns
- `mcp__garmin-db__materialize()` - Cache complex queries

**See `docs/data-analysis-guide.md` for detailed examples, code templates, and best practices.**

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

**DuckDB Regeneration (Post-FK-Removal)**

**New Capabilities (2025-11-01):**
- Independent table regeneration (FK constraints removed)
- Update metadata without touching performance data
- Recalculate specific metrics for targeted activities
- Validation ensures parent activities exist (prevents orphaned records)

**Common Patterns:**

1. **Metadata Fix (activities table only)**
   ```bash
   # Update activity name/date without recalculating performance
   uv run python -m garmin_mcp.scripts.regenerate_duckdb \
     --tables activities \
     --activity-ids 12345 \
     --force
   ```

2. **Performance Recalculation (child tables only)**
   ```bash
   # Fix calculation errors in splits or form metrics
   uv run python -m garmin_mcp.scripts.regenerate_duckdb \
     --tables splits form_efficiency \
     --activity-ids 12345 \
     --force
   ```

3. **Date Range Update (specific tables)**
   ```bash
   # Update specific metrics for a month of activities
   uv run python -m garmin_mcp.scripts.regenerate_duckdb \
     --tables splits \
     --start-date 2025-10-01 \
     --end-date 2025-10-31 \
     --force
   ```

4. **Full Table Regeneration (all activities)**
   ```bash
   # Regenerate entire table after schema change
   uv run python -m garmin_mcp.scripts.regenerate_duckdb \
     --tables splits form_efficiency \
     --force
   ```

5. **Full Database Regeneration (DANGEROUS)**
   ```bash
   # Complete reset (requires user approval)
   uv run python -m garmin_mcp.scripts.regenerate_duckdb --delete-db
   ```

**Safety Rules:**
- Child tables (splits, form_efficiency, etc.) require parent activities to exist
- Validation occurs BEFORE deletion (prevents orphaned records)
- Use `--activity-ids` for surgical updates, date range for batch updates
- Full database deletion (--delete-db) cannot be combined with --tables

**Enhanced Logging:**
- 🗑️ Activity-specific deletion: Logs when deleting specific activity records
- ⚠️ Table-wide deletion: Warns when deleting all records from tables
- ✅ Validation messages: Shows which parent activities exist/missing

**Raw Data Fetching:**
```bash
# Fetch missing raw data
uv run python -m garmin_mcp.scripts.bulk_fetch_raw_data --start-date 2025-10-01

# Fetch activity details only
uv run python -m garmin_mcp.scripts.bulk_fetch_activity_details --activity-ids 12345 67890
```

### DuckDB CLI Usage

**When:** Schema inspection, query prototyping, data validation, debugging.

**Installation:**
```bash
# Download official binary to /usr/local/bin
cd /tmp
wget https://github.com/duckdb/duckdb/releases/latest/download/duckdb_cli-linux-amd64.zip
unzip duckdb_cli-linux-amd64.zip
sudo mv duckdb /usr/local/bin/
rm duckdb_cli-linux-amd64.zip

# Verify installation
duckdb --version
```

**Quick Start (Aliases):**
```bash
# Pre-configured aliases in ~/.zshrc
duckdb-tables       # Show all tables
duckdb-activities   # Show last 10 activities
duckdb-garmin       # Open DB in read-only mode

# Custom queries
duckdb-garmin -c "SELECT * FROM splits WHERE activity_id = 12345 LIMIT 5;"
```

**Common Commands:**
```bash
# Schema inspection
duckdb-garmin -c "SHOW TABLES;"
duckdb-garmin -c "DESCRIBE splits;"
duckdb-garmin -c "PRAGMA table_info('form_efficiency');"

# Data validation
duckdb-garmin -c "SELECT COUNT(*) FROM splits WHERE activity_id = 12345;"
duckdb-garmin -c "SELECT activity_date, activity_name FROM activities WHERE activity_date = '2025-10-30';"

# MCP tool verification (compare tool output with actual data)
duckdb-garmin -c "SELECT split_number, pace_seconds_per_km, avg_heart_rate
  FROM splits WHERE activity_id = 20783281578 ORDER BY split_number;"

# Query prototyping (before implementing MCP tools)
duckdb-garmin -c "
  WITH splits_agg AS (
    SELECT activity_id, AVG(pace_seconds_per_km) as avg_pace
    FROM splits GROUP BY activity_id
  )
  SELECT a.activity_date, s.avg_pace
  FROM activities a
  LEFT JOIN splits_agg s ON a.activity_id = s.activity_id
  WHERE a.activity_date >= '2025-10-01'
  ORDER BY a.activity_date LIMIT 5;
"
```

**Safety Rules:**
- ✅ **ALWAYS use `-readonly` flag** (aliases include it by default)
- ✅ Schema inspection, query prototyping, debugging: OK
- ❌ **NEVER write queries in application code** (use MCP tools instead)
- ❌ **NEVER modify data via CLI** (use scripts with proper logging)

**Use Cases:**
1. **Before implementing MCP tool**: Prototype SQL query in CLI, then convert to tool
2. **Debugging tool output**: Compare MCP tool result with actual DB content
3. **Schema changes**: Verify column names/types before writing migration scripts
4. **Data validation**: Check data integrity after regeneration scripts

**Direct Command (without alias):**
```bash
duckdb ~/garmin_data/data/database/garmin_performance.duckdb -readonly -c "SHOW TABLES;"
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
- Edit code without Serena MCP: `Edit("packages/garmin-mcp-server/src/garmin_mcp/ingest/worker.py", ...)`
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
- `GarminDBWriter`: DuckDB insertion (12 normalized tables)
- `ReportGeneratorWorker`: Template-based report generation

**DuckDB Schema (12 tables):**
- Metadata: `activities`, `body_composition`
- Performance: `splits`, `performance_trends`, `time_series_metrics` (26 metrics × 1000-2000 rows)
- Physiology: `form_efficiency`, `hr_efficiency`, `heart_rate_zones`, `vo2_max`, `lactate_threshold`
- Analysis: `section_analyses` (5 agent results per activity)

### Directory Structure

```
garmin-performance-analysis/          # Monorepo
├── packages/
│   └── garmin-mcp-server/            # Deployable MCP server
│       ├── pyproject.toml            # Package dependencies
│       ├── src/
│       │   └── garmin_mcp/
│       │       ├── server.py         # MCP server entry point
│       │       ├── database/         # DuckDB operations
│       │       ├── ingest/           # API fetching
│       │       ├── reporting/        # Report generation
│       │       ├── form_baseline/    # Form evaluation
│       │       ├── rag/              # RAG queries
│       │       ├── utils/            # Utilities
│       │       └── scripts/          # Maintenance scripts
│       └── tests/                    # All tests
├── .claude/                          # Claude Code workflow
│   ├── agents/                       # 5 analysis + 3 dev agents
│   ├── commands/                     # /analyze-activity, /batch-analyze
│   └── settings.local.json           # MCP settings
├── data/                             # GARMIN_DATA_DIR (configurable via .env)
│   ├── raw/                          # API responses (8 files/activity)
│   └── database/                     # garmin_performance.duckdb
├── result/                           # GARMIN_RESULT_DIR (configurable via .env)
│   ├── individual/                   # YEAR/MONTH/YYYY-MM-DD_id.md
│   └── monthly/                      # Monthly trends
├── docs/                             # Documentation + project management
└── CLAUDE.md                         # This file
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

**Temperature Evaluation (Training-Type-Aware):**
- **Recovery**: 15-22°C = Good (tolerance wider due to low heat production)
- **Base Run**: 10-18°C = Ideal, 18-23°C = Acceptable
- **Tempo/Threshold**: 8-15°C = Ideal, 15-20°C = Good, 20-25°C = Slightly hot
- **Interval/Sprint**: 8-15°C = Ideal, 20-23°C = Slightly hot, >23°C = Dangerous
- Note: environment-section-analyst uses `get_hr_efficiency_analysis()` to get training_type

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
