# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Overview

Garmin running performance analysis system with **DuckDB-first architecture** and **MCP-first tool usage**.

**System Pipeline:** Raw Data (API) → DuckDB → MCP Tools → Analysis → Reports

**Key Features:**
- DuckDB normalized storage (14 tables, 100+ activities)
- 30+ token-optimized MCP tools (70-98.8% reduction)
- 5 specialized analysis agents
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
See `.claude/rules/analysis/analysis-standards.md` for workflow details and `docs/data-analysis-guide.md` for examples.

---

## Common Pitfalls

**Intent disambiguation:** See `.claude/rules/intent-disambiguation.md`

**Training plan rules:** See `.claude/rules/analysis/analysis-standards.md`

**Project conventions:** Rule files go in `.claude/rules/` (auto-loaded). CLAUDE.md is for overview and workflows only.

---

## For Tool Development

**When:** Modifying code, adding features, fixing bugs, running tests.

**Workflow:** Plan mode → Issue → Worktree → Implement → Ship

Key rules (auto-loaded from `.claude/rules/dev/`):
- `workflow-orchestration.md` — plan-first, elegance check, core principles
- `implementation-workflow.md` — delegate → verify → ship (手続き的ワークフロー)
- `dev-reference.md` — git, testing, code quality, architecture, validation (参照辞書)

### Analysis Workspace (検証用)

`analysis/` ディレクトリで分析専用ワークスペースを提供。worktree 検証時に使用:
```bash
# 1. analysis/.env に worktree パスを設定
echo 'GARMIN_MCP_SERVER_DIR=/path/to/worktree/packages/garmin-mcp-server' > analysis/.env
# 2. fixture DB 生成
GARMIN_DATA_DIR=analysis/data uv run python -m garmin_mcp.scripts.regenerate_duckdb --activity-ids 12345678901 --force
# 3. E2E 検証
cd analysis/ && claude -p "/analyze-activity 2025-10-09"
```

### Quick Commands
| Command | Purpose |
|---------|---------|
| `uv sync --extra dev` | Initial setup |
| `direnv allow` | Auto-load env |
| `uv run python -m garmin_mcp.scripts.regenerate_duckdb --tables X --activity-ids N --force` | Surgical DuckDB update |
| `uv run python -m garmin_mcp.scripts.bulk_fetch_raw_data --start-date YYYY-MM-DD` | Fetch raw data |
| `uv run python -m garmin_mcp.scripts.bulk_fetch_activity_details --activity-ids N` | Fetch activity details |

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
│   ├── agents/                     # 5 analysis agents
│   ├── commands/                   # /analyze-activity, /batch-analyze, /decompose, /project-status, /ship
│   ├── rules/                      # Shared rules (auto-loaded)
│   ├── tasks/                      # todo.md, lessons.md (session tracking)
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
