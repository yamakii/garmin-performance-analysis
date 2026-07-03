# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Overview

Garmin running performance analysis system with **DuckDB-first architecture** and **MCP-first tool usage**.

**System Pipeline:** Raw Data (API) → DuckDB → MCP Tools → Analysis

**Key Features:**
- DuckDB normalized storage (23 tables, 100+ activities)
- Token-optimized MCP tools (70-98.8% reduction), declared via a single-source `tools/` registry (see `docs/mcp-tools-reference.md` for the full set)
- 3 analysis agents (unified-section-analyst + split-section-analyst + summary-section-analyst)
- Japanese analysis stored in DuckDB, viewed via the Web app (code/docs in English)

**Two Use Cases:**
1. **Activity Analysis** - Analyze running data using MCP tools (→ See "For Activity Analysis")
2. **Tool Development** - Develop/improve the analysis system (→ See "For Tool Development")

---

## For Activity Analysis

**When:** Analyzing activities, finding trends, comparing workouts.

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

### Worktree 検証

Validation Agent 方式（L1/L2 は subprocess で並列起動可、L3 のみメインセッション直列）。
`/implement` は `implement-tier` Workflow でティアを実装し、検証 PASS + `ci-guard` green の PR を auto-merge する。
プラン承認済みの実装は**単発 Issue でも既定で `/implement <issue>`**（承認時に `design-approved` 付与）。手動 developer 委任＋`/ship` は例外（L3／Workflow 不可／docs・rules の skip 微修正）。
詳細は `.claude/rules/dev/worktree-validation-protocol.md` を参照。

### Quick Commands
| Command | Purpose |
|---------|---------|
| `uv sync --extra dev` | Initial setup |
| `direnv allow` | Auto-load env |
| `uv run python -m garmin_mcp.scripts.regenerate_duckdb --tables X --activity-ids N --force` | Surgical DuckDB update |
| `uv run python -m garmin_mcp.scripts.bulk_fetch_raw_data --start-date YYYY-MM-DD` | Fetch raw data |
| `uv run python -m garmin_mcp.scripts.bulk_fetch_activity_details --activity-ids N` | Fetch activity details |
| `uv run python -m garmin_mcp.scripts.backfill_wellness [--start-date YYYY-MM-DD]` | Rate-limit-safe full-history daily_wellness backfill (monthly chunks, 429 backoff, auto data-floor stop, resume) |
| `uv run python -m garmin_mcp ingest catch-up --domains wellness --start-date YYYY-MM-DD` | Backfill daily wellness (RHR/HRV/sleep) over a date range |

---

## Architecture

**Pipeline:** API → Raw JSON → DuckDB → MCP Tools → Analysis (viewed via Web app)

**Key Modules:**

| Module | Role |
|---|---|
| `GarminIngestWorker` | Thin orchestrator delegating to 3 modules below |
| `ApiClient` | Garmin Connect API authentication singleton |
| `RawDataFetcher` | Cache-first raw data collection |
| `DuckDBSaver` | Transaction-batched DuckDB insertion |
| `GarminDBWriter` | DuckDB write operations (23 tables, 12 inserters) |
| `GarminDBReader` | DuckDB read operations (query builders) |
| `tools/` registry | Domain tools + 2 server tools declared as `ToolDef` (see `docs/mcp-tools-reference.md`). `server.py` dispatches directly from `ALL_DEFS_BY_NAME` (O(1) lookup) |

**DuckDB Schema (23 domain tables):**
- Metadata: `activities`, `body_composition`
- Performance: `splits`, `performance_trends`, `time_series_metrics` (26 metrics x 1000-2000 rows)
- Physiology: `form_efficiency`, `form_evaluations`, `form_baseline_history`, `hr_efficiency`, `heart_rate_zones`, `vo2_max`, `lactate_threshold`, `daily_wellness`
- Training: `training_plans`, `planned_workouts`, `strength_sessions`
- Athlete: `athlete_profile`, `athlete_goals`, `season_retrospectives`, `weekly_reviews`
- Analysis: `section_analyses` (5 section results per activity: efficiency/phase/environment/summary/split), `trend_analyses` (weekly/monthly longitudinal trend narration)
- Operations: `sync_runs` (scheduled auto-sync execution log)

> See `docs/spec/duckdb_schema_mapping.md` for the full column-level schema.

### Directory Structure

```
garmin-performance-analysis/
├── packages/
│   ├── garmin-mcp-server/
│       ├── pyproject.toml
│       ├── src/garmin_mcp/
│       │   ├── ingest/             # API → Raw data (ApiClient, RawDataFetcher, DuckDBSaver)
│       │   ├── database/
│       │   │   ├── inserters/      # 12 table-specific inserters
│       │   │   ├── readers/        # Query builders (SplitsQueryBuilder etc.)
│       │   │   └── migrations/     # Schema migrations
│       │   ├── handlers/           # base.py only (shared response helpers); domain dispatch lives in tools/ + server.py
│       │   ├── form_baseline/      # Form baseline training
│       │   ├── scripts/
│       │   │   └── regenerate/     # DuckDB regeneration utilities
│       │   ├── tools/              # ToolDef registry (single source for all MCP tools)
│       │   ├── tool_schemas.py     # thin wrapper: registry tools + 2 server tools
│       │   └── validation/         # Data validation
│       └── tests/
│   └── garmin-web/                 # Web app (see docs/garmin-web.md)
│       ├── src/garmin_web/         # FastAPI backend (api/, queries/, cli.py)
│       ├── frontend/               # Vite + React SPA
│       └── tests/
├── .claude/
│   ├── agents/                     # 6 agent defs: 3 analysis (unified+split+summary) + developer/proofreader/validation
│   ├── skills/                     # 7 user-invocable skills (/analyze-activity, /decompose, /implement, /project-status, /set-goal, /ship, /weekly-review)
│   ├── rules/                      # Shared rules (auto-loaded)
│   ├── workflows/                  # Workflow scripts (implement-tier.js = /implement tier orchestration)
│   ├── tasks/                      # todo.md, lessons.md (session tracking)
│   └── settings.local.json
├── data/                           # GARMIN_DATA_DIR (configurable via .env)
│   ├── raw/                        # API responses (8 files/activity)
│   └── database/                   # garmin_performance.duckdb
├── result/                         # GARMIN_RESULT_DIR (configurable via .env)
├── docs/
└── CLAUDE.md
```

### Agent System

**3 Section Analysis Agents (run in parallel by the `analyze-activity` workflow):**
1. **unified-section-analyst** (sonnet): produces efficiency / phase / environment; the
   `analyze-activity` workflow calls it once per section (per-section mode).
   - **efficiency**: Form (GCT/VO/VR) + power + cadence + HR efficiency
   - **phase**: Phase evaluation (warmup/run/cooldown[/recovery], training-type-aware)
   - **environment**: Environmental impact (temperature, humidity, wind, terrain)
2. **summary-section-analyst** (sonnet): focused, leaner agent for `summary.json` only —
   Activity type + 4-axis overall assessment + recommendations. Split out of unified so the
   summary call does not load the full unified def (perf).
3. **split-section-analyst**: 1km split analysis (pace, HR, form)

> Section agents receive prefetched CONTEXT inline in the prompt (no file reads); split needs
> no CONTEXT. Each section is written as a separate `{section}.json` consumed by
> `merge_section_analyses`. summary derives cross-section consistency from the shared CONTEXT
> (it runs in parallel with the others, not after them).

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
