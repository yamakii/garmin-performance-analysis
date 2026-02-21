# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Overview

Garmin running performance analysis system with **DuckDB-first architecture** and **MCP-first tool usage**.

**System Pipeline:** Raw Data (API) → DuckDB → MCP Tools → Analysis → Reports

**Key Features:**
- DuckDB normalized storage (14 tables, 100+ activities)
- 30+ token-optimized MCP tools (70-98.8% reduction)
- 7 specialized agents (5 analysis + 2 development)
- Japanese reports (code/docs in English)

**Two Use Cases:**
1. **Activity Analysis** - Analyze running data using MCP tools (→ See "For Activity Analysis")
2. **Tool Development** - Develop/improve the analysis system (→ See "For Tool Development")

---

## For Activity Analysis

**When:** Analyzing activities, generating reports, finding trends, comparing workouts.

All MCP tools have docstrings describing their parameters. Use `mcp__garmin-db__*` tools directly.

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

---

## For Data Analysis

**When:** Statistical analysis, multi-month trends, race prediction, adhoc queries involving 10+ activities.

Use the export-based 5-step workflow (Plan → Export → Code → Result → Interpret).
See `.claude/rules/mcp-data-access.md` for workflow details and `docs/data-analysis-guide.md` for examples.

---

## Common Pitfalls

**Intent disambiguation:** See `.claude/rules/intent-disambiguation.md`

**Training plan rules:** See `.claude/rules/training-plan-rules.md`

**Project conventions:** Rule files go in `.claude/rules/` (auto-loaded). CLAUDE.md is for overview and workflows only.

---

## For Tool Development

**When:** Modifying code, adding features, fixing bugs, running tests, managing projects.

Rules are auto-loaded from `.claude/rules/` (MCP data access, git workflow, testing, code quality, etc.).

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

**2. Development Process (GitHub Issue-centric)**
```
Decompose → Plan mode (per sub-issue) → Implement (worktree) → Ship & Close

Commands & Agents:
- /decompose: Break large tasks into Epic + Sub-issues on GitHub
- /project-status: Show Epic progress dashboard
- tdd-implementer: TDD cycle (reads design from GitHub Issue body)
- completion-reporter: Posts report to Issue + closes it
- /ship --close N: Push + close Issue
```

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

### Project Management (GitHub Issue-centric)

**GitHub Issues are the Single Source of Truth:**
- `epic` label: Large tasks with sub-issues (task list tracks progress)
- `sub-issue` label: Independently implementable units (1 plan mode cycle = 1 sub-issue)
- `spike` label: Investigation only, no code changes

**Workflows:**
- Large task: `/decompose` → Epic + Sub-issues → Plan mode per sub-issue → `/ship --close N`
- Small task: Plan mode → `/ship` (Issue optional)
- Progress: `/project-status [epic-number]`

**Issue hierarchy:**
```
Epic #50: Refactor ingest pipeline
  ├── Sub-issue #51: Extract ApiClient (closed)
  ├── Sub-issue #52: Extract RawDataFetcher (in progress)
  └── Sub-issue #53: Extract DuckDBSaver (pending)
```

---

## Architecture

**Pipeline:** API → Raw JSON → DuckDB → MCP Tools → Analysis → Markdown Reports

**Key Modules (after Phase 1/2 refactoring):**

| Module | Role |
|---|---|
| `GarminIngestWorker` | Thin orchestrator delegating to 3 modules below |
| `ApiClient` | Garmin Connect API authentication singleton |
| `RawDataFetcher` | Cache-first raw data collection |
| `DuckDBSaver` | Transaction-batched DuckDB insertion |
| `GarminDBWriter` | DuckDB write operations (14 tables, 12 inserters) |
| `GarminDBReader` | DuckDB read operations (query builders) |
| `ReportGeneratorWorker` | Template-based report generation |
| 8 MCP Handlers | MetadataHandler, SplitsHandler, PhysiologyHandler, PerformanceHandler, AnalysisHandler, TimeSeriesHandler, ExportHandler, TrainingPlanHandler |

**DuckDB Schema (14 tables):**
- Metadata: `activities`, `body_composition`
- Performance: `splits`, `performance_trends`, `time_series_metrics` (26 metrics x 1000-2000 rows)
- Physiology: `form_efficiency`, `form_evaluations`, `form_baseline_history`, `hr_efficiency`, `heart_rate_zones`, `vo2_max`, `lactate_threshold`
- Training: `training_plans`, `planned_workouts`
- Analysis: `section_analyses` (5 agent results per activity)

### Directory Structure

```
garmin-performance-analysis/
├── packages/
│   └── garmin-mcp-server/
│       ├── pyproject.toml
│       ├── src/garmin_mcp/
│       │   ├── ingest/             # API → Raw data (ApiClient, RawDataFetcher, DuckDBSaver)
│       │   ├── database/
│       │   │   ├── inserters/      # 12 table-specific inserters
│       │   │   ├── readers/        # Query builders (SplitsQueryBuilder etc.)
│       │   │   └── migrations/     # Schema migrations
│       │   ├── handlers/           # 8 MCP tool handlers
│       │   ├── reporting/          # Report generation + components
│       │   ├── training_plan/      # Training plan generation
│       │   ├── form_baseline/      # Form baseline training
│       │   ├── scripts/
│       │   │   └── regenerate/     # DuckDB regeneration utilities
│       │   ├── tool_schemas.py     # MCP tool definitions (30 tools)
│       │   └── validation/         # Data validation
│       └── tests/
├── .claude/
│   ├── agents/                     # 5 analysis + 2 dev agents
│   ├── commands/                   # /analyze-activity, /batch-analyze, /decompose, /project-status, /ship
│   ├── rules/                      # Shared rules (auto-loaded)
│   └── settings.local.json
├── data/                           # GARMIN_DATA_DIR (configurable via .env)
│   ├── raw/                        # API responses (8 files/activity)
│   └── database/                   # garmin_performance.duckdb
├── result/                         # GARMIN_RESULT_DIR (configurable via .env)
│   ├── individual/                 # YEAR/MONTH/YYYY-MM-DD_id.md
│   └── monthly/
├── docs/
└── CLAUDE.md
```

### Agent System

**5 Section Analysis Agents (run in parallel via Task tool):**
1. **split-section-analyst**: 1km split analysis (pace, HR, form)
2. **phase-section-analyst**: Phase evaluation (warmup/run/cooldown, training-type-aware)
3. **summary-section-analyst**: Activity type + overall assessment
4. **efficiency-section-analyst**: Form (GCT/VO/VR) + HR efficiency
5. **environment-section-analyst**: Environmental impact (weather, terrain)

**2 Development Agents:**
- **tdd-implementer**: TDD cycle in worktree (reads design from GitHub Issue)
- **completion-reporter**: Posts completion report to GitHub Issue + closes it

### Critical Data Sources

**Split Analysis:**
- `splits.json` (lapDTOs) - 1km lap data
- NOT `typed_splits.json` - Aggregated only

**Temperature:**
- `weather.json` - External weather station
- NOT `splits.json` temperature - Device temp (+5-8 C body heat)

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
