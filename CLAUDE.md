# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## System Overview

Garmin running performance analysis system with three-tier data pipeline (raw → performance → analysis), multi-agent analysis, DuckDB storage, and token optimization (~40% reduction).

**Key Features:**
- 5 specialized section analysis agents (split/phase/summary/efficiency/environment)
- DuckDB-backed storage with normalized tables
- Token-optimized performance data (Phases 1-3: form efficiency, HR efficiency, performance trends)
- Environment variable support for configurable data/result paths
- Japanese analysis reports (code/docs in English)

## Architecture

### Data Processing Pipeline

```
Raw Data (API) → Performance Data (pre-processed) → Analysis (DuckDB) → Reports
```

**Three-tier transformation:**
1. **Raw Layer** (`data/raw/`): Garmin API responses (per-API caching: 8 API files/activity)
2. **Performance Layer** (`data/performance/`): Pre-processed metrics (11 sections including Phase 1-3 optimizations)
3. **Analysis Layer** (`data/database/`, `result/`): Section analyses (DuckDB) + final reports (Markdown)

**Key Classes:**
- `GarminIngestWorker`: API → raw → performance → DuckDB pipeline
  - `collect_data(activity_id, force_refetch=None)`: Fetch from API with selective cache refresh
  - `process_activity(activity_id, date, force_refetch=None)`: Full pipeline orchestration
- `GarminDBWriter`: DuckDB insertion (7 normalized tables)
- `ReportGeneratorWorker`: Template-based report generation

**DuckDB Schema:**
- Normalized tables: `splits`, `form_efficiency`, `heart_rate_zones`, `hr_efficiency`, `performance_trends`, `vo2_max`, `lactate_threshold`
- Metadata: `activities` (foreign key relationships)
- Analysis: `section_analyses` (agent results)

### Directory Structure

```
├── data/              # Configurable via GARMIN_DATA_DIR (default: ./data)
│   ├── raw/          # API responses (activity/{id}/{api}.json, weight/{date}.json)
│   ├── performance/  # Pre-processed metrics ({id}.json)
│   ├── database/     # DuckDB files
│   └── precheck/     # Validation results
├── result/           # Configurable via GARMIN_RESULT_DIR (default: ./result)
│   ├── individual/   # Activity reports (YEAR/MONTH/YYYY-MM-DD_id.md)
│   └── monthly/      # Trend analysis
├── tools/            # Data processing (ingest/, database/, reporting/, rag/)
├── docs/project/     # Project planning (active: 2025-*, archived: _archived/)
└── .claude/          # Agent definitions and slash commands
```

**Environment Configuration:**
- Copy `.env.example` → `.env`, set `GARMIN_DATA_DIR`/`GARMIN_RESULT_DIR`
- Auto-loaded by `tools/__init__.py`, `direnv` support (`.envrc` provided)
- Path utilities: `tools/utils/paths.py`

## Tools & Integration Guide

### Tool Selection Matrix

| Target | Tool | Reason |
|--------|------|--------|
| Code files (`.py`, `.ts`, etc.) | **Serena MCP** (mandatory) | Symbol-aware editing, token-efficient navigation |
| JSON/Markdown/Text | Direct Read/Edit/Write | Simple text operations |
| Performance data queries | **Garmin DB MCP** (mandatory) | 70-80% token reduction, DuckDB access |
| Binary/log files | Direct Read/Write | Raw data access |

### Garmin DB MCP Server

**Primary tool for DuckDB performance data access (70-80% token reduction).**

**Categories:**
- **Performance Data**: `get_performance_trends`, `get_weather_data`, `get_section_analysis`
- **Normalized Tables**: `get_form_efficiency_summary`, `get_hr_efficiency_analysis`, `get_heart_rate_zones_detail`, `get_vo2_max_data`, `get_lactate_threshold_data`
- **Splits Data** (lightweight): `get_splits_pace_hr` (split/phase), `get_splits_form_metrics` (form), `get_splits_elevation` (environment), `get_splits_all` (summary only)
- **Write**: `insert_section_analysis_dict` (recommended), `insert_section_analysis` (legacy)
- **RAG Queries**: `get_interval_analysis`, `get_split_time_series_detail`, `get_time_range_detail`, `detect_form_anomalies`, `analyze_performance_trends`, `extract_insights`, `classify_activity_type`, `compare_similar_workouts`

**Note:** Prefer lightweight splits APIs for targeted analysis. activity_details.json provides 26 second-by-second metrics.

### Serena MCP Integration

**Mandatory for all code operations (symbol-aware editing).**

**Key Tools:**
- Navigation: `list_dir`, `get_symbols_overview`, `find_symbol`, `search_for_pattern`, `find_referencing_symbols`
- Editing: `replace_symbol_body`, `insert_after_symbol`, `insert_before_symbol`
- Memory: `read_memory`, `write_memory`, `list_memories`

**When NOT to use:** JSON/Markdown/text files, performance data access, binary files.

## Agent System

### Section Analysis Agents (5 parallel)

- **split-section-analyst**: 1km split analysis (pace, HR, form)
- **phase-section-analyst**: Phase evaluation (warmup/main/cooldown or warmup/run/recovery/cooldown)
- **summary-section-analyst**: Activity type + overall assessment
- **efficiency-section-analyst**: Form (GCT/VO/VR) + HR efficiency
- **environment-section-analyst**: Environmental impact (temperature, humidity, wind, terrain)

**Usage:** Run all 5 in parallel via Task tool, results stored in DuckDB.

### Development Process Agents

- **project-planner**: Planning phase (creates planning.md on main branch)
- **tdd-implementer**: Implementation phase (TDD cycle in git worktree)
- **completion-reporter**: Completion phase (generates completion_report.md)

**Workflow:** Planning (main) → Implementation (worktree) → Completion (merge & close)

### GitHub Issue Integration

**All projects tracked as GitHub Issues (Open = Active, Closed = Archived).**

**Workflow:**
1. Planning: `project-planner` creates planning.md → commit to main → create Issue → link Issue in planning.md
2. Implementation: Create worktree → `uv sync` + activate Serena → reference Issue in commits (`#<number>`)
3. Completion: `completion-reporter` generates report → merge → close Issue → archive project

**Scripts:**
- `create_project_issues.py`: Bulk create Issues (active + archived)
- `update_issue_links.py`: Update Issue descriptions with GitHub URLs

**Issue Structure:** Title, Overview (500 chars), Project Directory, Planning Document (GitHub URL), Completion Report (GitHub URL if completed)

## Common Development Commands

### Environment Setup

```bash
# Install dependencies
uv sync                          # Basic
uv sync --extra dev              # With dev tools
uv sync --extra performance      # With performance monitoring

# Git Worktree (MANDATORY for project development)
git worktree add -b feature/name ../path main
cd ../path
uv sync  # MANDATORY: Setup Python environment
mcp__serena__activate_project("/absolute/path")  # MANDATORY for agents

# Worktree management
git worktree list                # List all worktrees
git worktree remove ../path      # Remove after merge
git worktree prune               # Cleanup stale worktrees
```

**Worktree Workflow:**
- Planning: On main branch (no worktree)
- Implementation: Create worktree from main
- Completion: Merge to main, remove worktree

### Data Processing Scripts

| Operation | Script | Use Case |
|-----------|--------|----------|
| **Regenerate DuckDB** | `regenerate_duckdb.py` | After schema changes, data corruption |
| **Fetch raw data** | `bulk_fetch_raw_data.py` | Add missing API data |
| **Fetch activity details** | `bulk_fetch_activity_details.py` | Specific to activity_details.json |
| **Migrate data** | `migrate_raw_data_structure.py`, `migrate_weight_data.py` | Format migrations |

**Options:** `--dry-run`, `--start-date`, `--end-date`, `--activity-ids`, `--force`, `--delete-db`

**Critical Principle:** Separate API fetching (slow) from DuckDB regeneration (fast, local).

### Code Quality & Testing

```bash
# Format & lint
uv run black .
uv run ruff check .
uv run mypy .

# Testing
uv run pytest                    # All tests
uv run pytest -m unit            # Unit only
uv run pytest -m integration     # Integration only
uv run pytest -m performance     # Performance only
```

## Critical Data Source Requirements

**Split Analysis:**
- ✅ USE: `splits.json` (lapDTOs) for 1km lap data
- ❌ NEVER: `typed_splits.json` (aggregated, no individual splits)

**Temperature:**
- ✅ USE: `weather.json` (external weather station)
- ❌ NEVER: `splits.json` temperature (device temperature, +5-8°C body heat)

**Elevation:**
- Source: `lapDTOs` → `create_parquet_dataset()` → performance.json
- Classification: 平坦/起伏/丘陵/山岳

## Project Management

**Structure:** `docs/project/{YYYY-MM-DD}_{project_name}/` (active) or `docs/project/_archived/` (completed)

**Files:**
- `planning.md` (required): Overview, Goals, Architecture, Phases, Acceptance Criteria, Test Plan
- `completion_report.md` (required): Test Results, Coverage, Code Quality, Acceptance Review, Implementation Summary

**Current Projects:**
- Active: 10 projects (see GitHub Issues #1-6 for details)
- Archived: 11 projects (see GitHub Issues #7-21 for details)

**Workflow:** Planning (main branch) → Implementation (git worktree) → Completion (merge, archive, close Issue)

## Important Notes

- Agents cannot call other agents (use main Claude instance for orchestration)
- Data caching is aggressive (avoid API rate limits)
- Validate data sources before analysis (splits.json vs typed_splits.json, weather.json vs device temperature)
- Analysis reports in Japanese, code/docs in English
- Git worktree mandatory for all project development
