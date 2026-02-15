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
- `get_splits_comprehensive(activity_id, statistics_only=True/False)` - All split data (12 fields: pace, HR, form, power, cadence, elevation)
- `get_splits_pace_hr(activity_id, statistics_only=True/False)` - Pace/HR data (lightweight)
- `get_splits_form_metrics(activity_id, statistics_only=True/False)` - GCT/VO/VR (lightweight)
- `get_splits_elevation(activity_id, statistics_only=True/False)` - Terrain data

**Physiological Data:**
- `get_form_efficiency_summary(activity_id)` - Form metrics summary
- `get_form_evaluations(activity_id)` - Pace-corrected form evaluation with star ratings
- `get_form_baseline_trend(activity_id, activity_date)` - 1-month baseline coefficient comparison
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

---

## For Data Analysis

**When:** Statistical analysis, multi-month trends, race prediction, adhoc queries involving 10+ activities.

Use the export-based 5-step workflow (Plan → Export → Code → Result → Interpret).
See `.claude/rules/mcp-data-access.md` for workflow details and `docs/data-analysis-guide.md` for examples.

---

## For Tool Development

**When:** Modifying code, adding features, fixing bugs, running tests, managing projects.

### Critical Rules

**MANDATORY MCP Usage:**
- Code files (`.py`, `.ts`): **Serena MCP only** (symbol-aware editing)
- Performance data: **Garmin DB MCP only** (token-optimized queries)
- Text files (`.md`, `.json`, `.txt`): Direct Read/Edit/Write OK

**MANDATORY Git Worktree:** Planning on main → Implementation in worktree → Merge back.

### Development Workflow

**1. Environment Setup**
```bash
# Initial setup (main branch)
uv sync --extra dev

# For new feature (worktree)
git worktree add -b feature/name ../garmin-feature-name main
cd ../garmin-feature-name
uv sync --extra dev
direnv allow

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

### Data Processing Scripts

**DuckDB Regeneration:**
```bash
# Surgical update (recommended)
uv run python -m garmin_mcp.scripts.regenerate_duckdb \
  --tables splits form_efficiency \
  --activity-ids 12345 \
  --force
```

Options: `--tables`, `--activity-ids`, `--start-date`/`--end-date`, `--delete-db` (dangerous).
See `.claude/rules/duckdb-safety.md` for safety rules.

**Raw Data Fetching:**
```bash
uv run python -m garmin_mcp.scripts.bulk_fetch_raw_data --start-date 2025-10-01
uv run python -m garmin_mcp.scripts.bulk_fetch_activity_details --activity-ids 12345 67890
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
```

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
- Performance: `splits`, `performance_trends`, `time_series_metrics` (26 metrics x 1000-2000 rows)
- Physiology: `form_efficiency`, `hr_efficiency`, `heart_rate_zones`, `vo2_max`, `lactate_threshold`
- Analysis: `section_analyses` (5 agent results per activity)

### Directory Structure

```
garmin-performance-analysis/          # Monorepo
├── packages/
│   └── garmin-mcp-server/            # Deployable MCP server
│       ├── pyproject.toml            # Package dependencies
│       ├── src/garmin_mcp/           # Source code
│       └── tests/                    # All tests
├── .claude/                          # Claude Code workflow
│   ├── agents/                       # 5 analysis + 3 dev agents
│   ├── commands/                     # /analyze-activity, /batch-analyze
│   ├── rules/                        # Shared rules (auto-loaded)
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
- `splits.json` (lapDTOs) - 1km lap data
- NOT `typed_splits.json` - Aggregated only

**Temperature:**
- `weather.json` - External weather station
- NOT `splits.json` temperature - Device temp (+5-8 C body heat)

**Temperature Evaluation (Training-Type-Aware):**
- **Recovery**: 15-22 C = Good (tolerance wider due to low heat production)
- **Base Run**: 10-18 C = Ideal, 18-23 C = Acceptable
- **Tempo/Threshold**: 8-15 C = Ideal, 15-20 C = Good, 20-25 C = Slightly hot
- **Interval/Sprint**: 8-15 C = Ideal, 20-23 C = Slightly hot, >23 C = Dangerous
- Note: environment-section-analyst uses `get_hr_efficiency_analysis()` to get training_type

**Elevation:**
- Source: `lapDTOs` → DuckDB
- Classification: flat/undulating/hilly/mountainous

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
