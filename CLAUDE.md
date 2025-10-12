# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## System Overview

This is a Garmin running performance analysis system that uses the Garmin MCP server to collect data and generate comprehensive running analysis reports. The system focuses on detailed split-by-split analysis with environmental integration (terrain, weather, body condition).

**Key Features:**
- Three-tier data transformation pipeline (raw → performance → analysis)
- Multi-agent analysis system with 5 specialized section analysts
- DuckDB-backed storage for efficient data access
- Token-optimized performance data (40% reduction via Phase 1-3 optimizations)
- Japanese analysis reports for end-users (code/docs remain in English)

## Architecture

### Core Components

- **Garmin MCP Integration**: Uses `garmin-mcp` server configured in `.mcp.json` for data collection
- **Multi-agent Analysis System**: 5 section analysis agents process different performance aspects in parallel
- **Data Processing Pipeline**: Three-tier transformation: raw → performance → analysis
- **DuckDB Storage**: Primary storage for performance and section analysis data
- **Token Optimization**: Phase 1-3 optimizations reduce analysis token usage by ~40%

### Data Processing Architecture

The system follows a three-tier data transformation pipeline:

1. **Raw Data Layer** (`data/raw/`): Complete Garmin API responses collected and cached
2. **Performance Data Layer** (`data/performance/`): Pre-processed metrics for analysis
3. **Analysis Layer** (`result/`, DuckDB): Section analyses and final reports

#### Key Processing Classes

- **GarminIngestWorker** (`tools/ingest/garmin_worker.py`): Complete data pipeline manager
  - `collect_data(activity_id, force_refetch=None)`: Calls Garmin MCP functions to fetch activity data from API
    - Cache-first strategy: Loads from cache when available
    - **Partial refetch support**: `force_refetch` parameter allows selective API refetching of specific files
    - Supported files: `['activity_details', 'splits', 'weather', 'gear', 'hr_zones', 'vo2_max', 'lactate_threshold']`
    - Example: `collect_data(12345, force_refetch=['weather'])` refetches only weather data, preserving other cached files
  - `process_activity(activity_id, date, force_refetch=None)`: Orchestrates the full pipeline from API to analysis-ready data
    - DuckDB cache has priority: If complete performance data exists in DuckDB, `force_refetch` is ignored
    - Raw cache refetch: When DuckDB cache is incomplete, `force_refetch` controls which raw API files to update
  - `create_parquet_dataset()`: Transforms raw lapDTOs into structured DataFrames
  - `_calculate_split_metrics()`: Pre-calculates performance metrics including elevation data
  - `save_data()`: Outputs performance.json and precheck files

#### Data Flow

```
GarminIngestWorker: [API calls → raw_data.json → create_parquet_dataset() → {performance.json, precheck.json}]
                    ↓
           save_data() → 7 DuckDB inserters → Normalized tables (splits, form_efficiency, etc.)
                    ↓
         Section Analysis Agents (5 parallel) → DuckDB (section_analyses table)
                    ↓
              Report Generation → result/
```

**DuckDB Schema (2025-10-10 Update):**
- **Normalized tables**: `splits`, `form_efficiency`, `heart_rate_zones`, `hr_efficiency`, `performance_trends`, `vo2_max`, `lactate_threshold`
- **Metadata table**: `activities` (activity metadata with foreign key relationships)
- **Analysis table**: `section_analyses` (section analysis results from agents)
- **Note**: `performance_data` (JSON storage) table was removed in favor of normalized schema

### Directory Structure

```
├── data/              # Multi-tier data storage
│   ├── raw/          # Immutable Garmin API responses
│   ├── performance/  # Pre-processed analysis-ready data (performance.json)
│   ├── precheck/     # Data validation results
│   ├── database/     # DuckDB database files (primary storage for section analysis)
│   └── individual/   # [LEGACY] Section analysis JSON files (migrating to DuckDB)
├── result/           # Final analysis reports
│   ├── individual/   # Individual activity reports (YEAR/MONTH/YYYY-MM-DD_activity_ID.md)
│   ├── monthly/      # Monthly trend analysis
│   └── special/      # Specialized analyses
├── tools/            # Data processing and utility scripts
│   ├── ingest/       # Core data ingestion pipeline (GarminIngestWorker)
│   ├── database/     # Database operations (reader, writer, inserters)
│   └── reporting/    # Report generation (worker, renderer, templates)
├── docs/             # Documentation and specifications
│   └── project/      # Project planning and progress tracking
│       └── {YYYY-MM-DD}_{project_name}/  # Individual project directories
├── daily/            # Daily reflection notes
└── .claude/          # Claude Code configuration (agents, commands)
```

### Configurable Data Paths

**NEW (2025-10-11): Data and result directories can now be configured via environment variables for privacy and data separation.**

The system supports custom data directory locations to enable secure code publishing while keeping personal health data separate from the codebase.

**Environment Variables:**
- `GARMIN_DATA_DIR`: Base data directory (default: `./data`)
- `GARMIN_RESULT_DIR`: Result directory (default: `./result`)

**Configuration Setup:**
```bash
# 1. Copy .env.example to .env
cp .env.example .env

# 2. Set custom paths in .env
GARMIN_DATA_DIR=/home/user/private/garmin_data
GARMIN_RESULT_DIR=/home/user/private/garmin_results

# 3. Paths are automatically loaded by all components
```

**Affected Components:**
- `GarminIngestWorker`: Uses `get_raw_dir()`, `get_performance_dir()`, `get_precheck_dir()`, `get_weight_raw_dir()`
- `GarminDBReader/Writer`: Uses `get_database_dir()` for default db_path
- `ReportTemplateRenderer`: Uses `get_result_dir()` for report output
- Migration/bulk scripts: Use path utilities for default arguments

**Benefits:**
- **Privacy Protection**: Keep personal health data outside the Git repository
- **Flexible Deployment**: Different paths for development/production environments
- **Backward Compatible**: Existing code works without configuration (uses defaults)

**Path Utility Module:**
- Module: `tools/utils/paths.py`
- Functions: `get_data_base_dir()`, `get_result_dir()`, `get_raw_dir()`, `get_performance_dir()`, `get_precheck_dir()`, `get_database_dir()`, `get_weight_raw_dir()`

### Data Files Naming Convention

**Raw Data Structure (Phase 0 Refactoring):**
- **Activity data** (preferred): `data/raw/activity/{activity_id}/{api_name}.json`
  - Per-API caching for granular cache control
  - API files: `activity.json`, `activity_details.json`, `splits.json`, `weather.json`, `gear.json`, `hr_zones.json`, `vo2_max.json`, `lactate_threshold.json`
  - Allows partial re-fetching (e.g., weather data only)
  - Migration tool: `tools/migrate_raw_data_structure.py`
- **Activity data** (legacy, backward compatible): `{activity_id}_raw.json`
  - Single-file format with all API responses
  - Automatically detected by `collect_data()` for backward compatibility

**Weight Data Structure (2025-10-09 Migration):**
- **Current format**: `data/raw/weight/{YYYY-MM-DD}.json`
  - Flat file structure (one file per date)
  - Contains daily weigh-ins with full body composition metrics
  - Replaces old `data/weight_cache/raw/weight_{date}_raw.json` structure
- **Weight index**: `data/weight/index.json`
  - Metadata index for quick date lookups
  - Maps dates to raw file paths and summary stats
  - Replaces old `data/weight_cache/weight_index.json`
- **Migration tool**: `tools/migrate_weight_data.py`
  - Options: `--dry-run`, `--all`, `--date`, `--verify`, `--cleanup`
  - Full migration completed on 2025-10-09 (111 files)

**Processed Data:**
- **Performance data**: `{activity_id}.json` (pre-processed metrics with Phase 1, 2 optimizations)
- **Precheck data**: `{activity_id}.json` (validation results)
- **Monthly activities**: `activities_{YYYY-MM}.json`

**Note**: Section analysis data is stored in DuckDB (`data/database/`) and accessed via `mcp__garmin-db__get_section_analysis`. Intermediate JSON files in `data/individual/` are legacy files for migration purposes.

### Performance.json Structure (Phase 1, 2 Enhanced)

The `data/performance/{activity_id}.json` file contains 11 main sections:

**Base Sections (1-8):**
1. `basic_metrics`: Distance, time, pace, HR, cadence, power
2. `heart_rate_zones`: Zone boundaries, time in zones, percentages
3. `efficiency_metrics`: Cadence stability, power efficiency, pace variability
4. `training_effect`: Aerobic/anaerobic training effect values
5. `power_to_weight`: W/kg ratio with statistical weight calculation
6. `split_metrics`: Per-split detailed metrics (22 fields per split)
7. `vo2_max`: VO2 max estimation data
8. `lactate_threshold`: Lactate threshold metrics

**Phase 1 Additions (9-10):**
9. `form_efficiency_summary`: Pre-calculated GCT/VO/VR statistics
   - Average, min, max, std, variability for each metric
   - ★-rating evaluation (★★★★★ to ★★★☆☆)
   - Textual evaluation (e.g., "優秀な接地時間、効率的な地面反力利用")

10. `hr_efficiency_analysis`: Pre-calculated HR zone analysis
    - Zone distribution summary with percentages
    - Primary zone identification
    - Training type classification (aerobic_base/tempo_run/threshold_work/mixed_effort)
    - HR stability assessment (優秀/良好/変動あり)

**Phase 2 Additions (11):**
11. `performance_trends`: Pre-calculated phase-based analysis
    - `warmup_phase`: Splits, avg metrics, evaluation
    - `main_phase`: Splits, avg metrics, pace stability
    - `finish_phase`: Splits, avg metrics, fatigue assessment
    - `pace_consistency`: Coefficient of variation (lower = more consistent)
    - `hr_drift_percentage`: HR drift from warmup to finish (< 5% ideal)
    - `cadence_consistency`: "高い安定性" or "変動あり"
    - `fatigue_pattern`: "適切な疲労管理" / "軽度の疲労蓄積" / "顕著な疲労蓄積"

**Performance Optimization Impact:**
- **Phase 1** (performance.json): Form & HR efficiency pre-calculation (~1,100 tokens saved/activity)
- **Phase 2** (performance.json): Performance trends pre-calculation (~1,000 tokens saved/activity)
- **Phase 3** (Garmin DB MCP): RAG query tools for trend analysis & workout comparison
- **Total Impact**: ~2,100 tokens saved per activity (~40% reduction in analysis token usage)

**Current Status:** Phases 1-3 implemented and operational.

## Tools & Integration Guide

### Tool Selection Decision Tree

**1. Code Files** (`.py`, `.ts`, `.js`, `.go`, etc.)
   - ✅ **MANDATORY:** Use Serena MCP
   - Tools: `find_symbol`, `replace_symbol_body`, `insert_after_symbol`
   - Reason: Symbol-aware editing, token-efficient code navigation

**2. JSON/Markdown/Text Files** (`.json`, `.md`, `.yaml`, `.txt`)
   - ✅ Use direct `Read`, `Edit`, `Write` tools
   - Reason: Simple structured text, no abstraction needed

**3. Performance Data Access**
   - ✅ **MANDATORY:** Use Garmin DB MCP
   - Tools: `get_performance_trends`, `get_weather_data`, `get_splits_*`, `insert_section_analysis_dict`
   - Reason: Efficient DuckDB access, 70-80% token reduction

**4. Other Files** (logs, binary, CSV, parquet)
   - ✅ Use direct `Read`/`Write` tools

### Tool Matrix

| Operation | Tool | Reason |
|-----------|------|--------|
| Code editing | Serena MCP | Symbol-aware operations |
| JSON/Markdown editing | Direct Read/Edit/Write | Simple text operations |
| Performance data queries | Garmin DB MCP | Token-efficient DuckDB access |
| Data insertion | Garmin DB MCP | DuckDB write operations |
| Binary/log files | Direct Read | Raw data access |

### Garmin DB MCP Server

**⚠️ RECOMMENDED: Use this MCP server for efficient DuckDB access to performance data**

Provides efficient section-based access to DuckDB performance data, write capabilities, and RAG query tools for trend analysis.

**Read Tools (70-80% token reduction):**

*Performance Data Access:*
- `mcp__garmin-db__get_performance_trends`: Get performance trends data (pace consistency, HR drift, phase analysis)
- `mcp__garmin-db__get_weather_data`: Get weather data (temperature, humidity, wind) from activity
- `mcp__garmin-db__get_section_analysis`: Get pre-calculated section analysis from DuckDB

*Normalized Table Access (2025-10-10 added - Direct DuckDB table queries):*
- `mcp__garmin-db__get_form_efficiency_summary`: Form efficiency (GCT/VO/VR) summary with ratings
- `mcp__garmin-db__get_hr_efficiency_analysis`: HR efficiency analysis with zone distribution
- `mcp__garmin-db__get_heart_rate_zones_detail`: Heart rate zone boundaries and time distribution
- `mcp__garmin-db__get_vo2_max_data`: VO2 max estimation data
- `mcp__garmin-db__get_lactate_threshold_data`: Lactate threshold metrics
- `mcp__garmin-db__get_splits_all`: All split data (all 22 fields per split)

*Splits Data Access (Lightweight - Token-efficient targeted queries):*
- `mcp__garmin-db__get_splits_pace_hr`: Pace & HR progression (~9 fields/split) - **Use for split/phase analysis**
- `mcp__garmin-db__get_splits_form_metrics`: Form efficiency GCT/VO/VR (~6 fields/split) - **Use for form analysis**
- `mcp__garmin-db__get_splits_elevation`: Elevation & terrain data (~7 fields/split) - **Use for environment analysis**

*Note: Only use `get_splits_all` when multiple data categories are needed (e.g., summary analysis). For targeted analysis, always prefer lightweight APIs to reduce token usage.*

**Write Tools (DuckDB data insertion):**
- `mcp__garmin-db__insert_section_analysis_dict`: **[RECOMMENDED]** Insert section analysis dict directly into DuckDB (no file creation)
- `mcp__garmin-db__insert_section_analysis`: Insert section analysis JSON file into DuckDB (legacy)

**RAG Query Tools (Phase 2.5: Interval Analysis & Time Series Detail):**
- `mcp__garmin-db__get_interval_analysis`: Analyze interval training Work/Recovery segments with fatigue detection
- `mcp__garmin-db__get_split_time_series_detail`: Get second-by-second detailed metrics for a specific 1km split
- `mcp__garmin-db__detect_form_anomalies`: Detect form metric anomalies and identify causes (elevation/pace/fatigue)

**RAG Query Tools (Phase 3: Trend Analysis & Comparison):**
- `mcp__garmin-db__compare_similar_workouts`: Find and compare similar past activities
- `mcp__garmin-db__get_performance_trends`: Analyze performance trends for specific metrics over time
- `mcp__garmin-db__extract_insights`: Extract insights from section analyses using keyword-based search

### Serena MCP Integration

**Mandatory Serena Usage for Code Operations:**

#### Code Navigation and Understanding
```bash
# Get file/directory overview
mcp__serena__list_dir
mcp__serena__get_symbols_overview

# Search and locate code
mcp__serena__find_symbol
mcp__serena__search_for_pattern
mcp__serena__find_referencing_symbols
```

#### Code Modifications
```bash
# Safe code editing
mcp__serena__replace_symbol_body
mcp__serena__insert_after_symbol
mcp__serena__insert_before_symbol
```

#### Project Understanding
```bash
# Project memory and knowledge
mcp__serena__read_memory
mcp__serena__write_memory
mcp__serena__list_memories
```

**Serena First Principle:**

Before using direct file operations (Read, Edit, Write), always consider:

1. **Code Exploration**: Use `get_symbols_overview` before reading entire files
2. **Targeted Reading**: Use `find_symbol` with `include_body=true` for specific functions/classes
3. **Safe Editing**: Use symbol-based editing instead of line-based editing
4. **File Operations**: Use `list_dir` and `find_file` instead of bash `ls` and `find`
5. **Pattern Search**: Use `search_for_pattern` instead of bash `grep`

**When NOT to Use Serena:**
- JSON/Markdown/text files → Use Direct Read/Edit/Write
- Performance data access → Use Garmin DB MCP
- Binary/log files → Use Direct Read

## Agent System

### Specialized Agents

The system uses specialized agents that cannot call each other directly. Use the main Claude instance to orchestrate workflows.

#### Section Analysis Agents

These agents analyze specific aspects of running performance and store results in DuckDB. **All 5 agents must be run in parallel** for efficiency:

- **split-section-analyst**: Individual 1km split analysis with pace, HR, and form metrics
- **phase-section-analyst**: Training phase evaluation (warmup/main/cooldown for normal runs, warmup/run/recovery/cooldown for interval training)
- **summary-section-analyst**: Activity type determination and overall assessment with improvement suggestions
- **efficiency-section-analyst**: Form efficiency (GCT/VO/VR) and heart rate efficiency (zone distribution)
- **environment-section-analyst**: Environmental impact analysis (temperature, humidity, wind, terrain)

#### Development Process Agents

These agents support software development workflow (Planning → Implementation → Completion):

- **project-planner**: Project planning, requirement definition, test planning
- **tdd-implementer**: TDD cycle execution, code quality checks, commits
- **completion-reporter**: Test result collection, coverage reports, completion documentation

See "Development Process Agents" section below for detailed usage instructions.

### Workflow Execution

**Standard Individual Activity Analysis:**

1. **Data Collection & DuckDB Insertion** (Python direct execution):
   ```python
   from tools.ingest.garmin_worker import GarminIngestWorker

   worker = GarminIngestWorker()

   # Basic usage (cache-first)
   result = worker.process_activity(activity_id, "YYYY-MM-DD")

   # Partial refetch: Update only specific cached files (e.g., weather data)
   result = worker.process_activity(
       activity_id,
       "YYYY-MM-DD",
       force_refetch=['weather', 'vo2_max']
   )

   # Note: save_data() automatically inserts into DuckDB normalized tables
   # Note: DuckDB cache has priority - force_refetch only applies when DuckDB cache is incomplete
   ```

2. **Section Analysis** (5 agents in parallel):
   ```bash
   Task: efficiency-section-analyst
   prompt: "Activity ID {id} ({date}) のフォーム効率と心拍効率を分析してください。"

   Task: environment-section-analyst
   prompt: "Activity ID {id} ({date}) の環境要因（気温、風速、地形）の影響を分析してください。"

   Task: phase-section-analyst
   prompt: "Activity ID {id} ({date}) のフェーズ評価を実行してください。"

   Task: split-section-analyst
   prompt: "Activity ID {id} ({date}) の全スプリットを詳細分析してください。"

   Task: summary-section-analyst
   prompt: "Activity ID {id} ({date}) のアクティビティタイプ判定と総合評価を生成してください。"
   ```

3. **Report Generation** (Python worker or dedicated process):
   - Retrieve section analysis from DuckDB
   - Generate final report using templates

**Quick Command:** Use the `/analyze-activity {activity_id} {date}` slash command for automated workflow execution.

### Development Process Agents

**⚠️ PROACTIVE USAGE: Use these agents automatically when user intent matches the trigger conditions**

The system provides three specialized agents that enforce the DEVELOPMENT_PROCESS.md workflow (Planning → Implementation → Completion Report):

#### project-planner Agent

**Auto-invoke when:**
- User mentions: "新しいプロジェクト", "新機能", "機能追加", "planning", "計画"
- User wants to start new feature development
- User asks to create planning.md
- User expresses intent to begin development work

**Responsibilities:**
- Create project directory: `docs/project/{YYYY-MM-DD}_{project_name}/`
- Generate `planning.md` from template
- Guide requirement definition, design, and test planning
- Define acceptance criteria

**Example invocation:**
```bash
Task: project-planner
prompt: "DuckDBにセクション分析結果を保存する機能を追加したい。プロジェクト名は 'duckdb_section_analysis' で計画を立ててください。"
```

#### tdd-implementer Agent

**Auto-invoke when:**
- `planning.md` exists and is complete
- User mentions: "実装", "implement", "TDD", "テスト書いて"
- User wants to start coding after planning
- Planning phase is confirmed complete

**Responsibilities:**
- Execute TDD cycle: Red (failing test) → Green (minimal implementation) → Refactor
- Run code quality checks (Black, Ruff, Mypy, pytest)
- Create Conventional Commits
- Manage Pre-commit hooks
- **Update `planning.md` with implementation progress and results**

**Example invocation:**
```bash
Task: tdd-implementer
prompt: "docs/project/2025-10-09_duckdb_section_analysis/planning.md に基づいて、TDDサイクルで実装してください。"
```

#### completion-reporter Agent

**Auto-invoke when:**
- Implementation is complete (all tests passing)
- User mentions: "完了", "レポート", "completion", "完了レポート"
- User asks for summary of what was implemented
- All acceptance criteria appear to be met

**Responsibilities:**
- Collect test results (Unit, Integration, Performance)
- Generate coverage report
- Verify code quality checks
- Create `completion_report.md` with all metrics
- Compare against acceptance criteria

**Example invocation:**
```bash
Task: completion-reporter
prompt: "docs/project/2025-10-09_duckdb_section_analysis/ の完了レポートを作成してください。"
```

#### Workflow Sequence

**IMPORTANT: Always follow this sequence, do not skip phases**

1. **Planning** → Use `project-planner` → Output: `planning.md`
2. **Implementation** → Use `tdd-implementer` → Output: Code + Tests + Commits
3. **Completion** → Use `completion-reporter` → Output: `completion_report.md`

**Proactive behavior:**
- When user says "新しい機能を追加したい", immediately suggest: "project-planner エージェントで計画を立てましょうか？"
- After planning.md is complete, suggest: "tdd-implementer エージェントで実装を始めますか？"
- After implementation is done, suggest: "completion-reporter エージェントで完了レポートを作成しますか？"

**Reference:** See `docs/AGENT_WORKFLOW.md` for detailed usage examples and troubleshooting.

## Common Development Commands

### Environment Setup
```bash
# Install dependencies
uv sync

# Install with development dependencies
uv sync --extra dev

# Install with performance monitoring tools
uv sync --extra performance
```

**⚠️ IMPORTANT: Git Worktree Setup**

When creating a new git worktree for isolated development:

```bash
# Create worktree
git worktree add -b <branch-name> <path> <base-branch>

# ALWAYS run uv sync immediately after
cd <path>
uv sync

# MANDATORY: Activate Serena MCP for the worktree (for agents)
# Agents must activate Serena with the worktree's absolute path
mcp__serena__activate_project("<absolute-path-to-worktree>")
```

**Why this is required:**
- Git worktrees create separate working directories
- Virtual environment and dependencies are not shared between worktrees
- `uv sync` must be run in each worktree to set up the Python environment
- **Serena MCP must be activated with the worktree path for code operations**
- Failure to run `uv sync` will result in missing dependencies and import errors
- Failure to activate Serena will prevent agents from using symbol-aware code editing tools

**Example:**
```bash
git worktree add -b feature/new-analysis ../garmin-feature main
cd ../garmin-feature
uv sync  # <- MANDATORY

# For agents working in this worktree
mcp__serena__activate_project("/home/user/workspace/garmin-feature")  # <- MANDATORY for agents
```

### Data Processing Scripts

**⚠️ CRITICAL PRINCIPLE: Always separate API fetching from data regeneration**

The system has two distinct operations that MUST NOT be mixed:
1. **API Fetching**: Fetching new data from Garmin Connect API (slow, rate-limited)
2. **Data Regeneration**: Regenerating performance.json and DuckDB from existing raw data (fast, no API calls)

**Why this matters:**
- API fetching is expensive and slow (824 activity calls + 500+ body composition calls for 103 activities)
- Data regeneration is fast and local (reads from cached raw data)
- Mixing them causes unnecessary API load and delays

#### Regeneration from Raw Data (Preferred Method)

**Use `GarminIngestWorker` directly for regeneration:**

```python
# Regenerate single activity from existing raw data
from tools.ingest.garmin_worker import GarminIngestWorker

worker = GarminIngestWorker()

# If DuckDB cache exists: Returns cached data (no regeneration)
# If DuckDB cache missing but raw data exists: Regenerates from raw data
# If raw data missing: Fetches from API
result = worker.process_activity(activity_id, "YYYY-MM-DD")
```

**Bulk regeneration pattern:**
```python
# Example: Regenerate all activities after schema change
from tools.ingest.garmin_worker import GarminIngestWorker
from pathlib import Path
import json

worker = GarminIngestWorker()

# Get all activity IDs from raw data
raw_dir = Path("data/raw/activity")
for activity_dir in sorted(raw_dir.iterdir()):
    if activity_dir.is_dir():
        activity_id = int(activity_dir.name)
        # Load date from activity.json
        activity_file = activity_dir / "activity.json"
        if activity_file.exists():
            with open(activity_file) as f:
                data = json.load(f)
                date = data.get("startTimeLocal", "").split()[0]

            # Process activity (will regenerate if DuckDB cache missing)
            worker.process_activity(activity_id, date)
```

#### API Fetching Scripts

```bash
# Fetch activity_details.json for all activities
uv run python tools/bulk_fetch_activity_details.py

# Dry run (show what would be fetched)
uv run python tools/bulk_fetch_activity_details.py --dry-run

# Force re-fetch even if files exist
uv run python tools/bulk_fetch_activity_details.py --force
```

**Purpose:** Fetch specific missing data from Garmin API (e.g., activity_details.json for interval analysis)

#### Data Migration Scripts

```bash
# Migrate raw data structure (legacy → per-API format)
uv run python tools/migrate_raw_data_structure.py

# Migrate weight data structure
uv run python tools/migrate_weight_data.py --all

# Dry run (show what would be migrated)
uv run python tools/migrate_weight_data.py --dry-run --all

# Verify migration
uv run python tools/migrate_weight_data.py --verify
```

**Purpose:** Migrate data between different storage formats

#### ⚠️ PROHIBITED Scripts

**DO NOT USE: `tools/scripts/reingest_duckdb_data.py`**

**Why prohibited:**
- **Violates separation principle**: Mixes API fetching with regeneration
- **Deletes DuckDB database** then re-fetches ALL data from Garmin API
- Makes 1,300+ unnecessary API calls (824 activity + 500+ body composition)
- Should only re-fetch if raw data is missing

**What it does wrong:**
1. Deletes existing DuckDB
2. For each activity: Calls `process_activity()` without checking raw data cache first
3. `collect_data()` re-fetches from API even when raw data exists

**Correct approach instead:**
1. Delete DuckDB if needed
2. Use `GarminIngestWorker.process_activity()` which checks raw data cache first
3. Only fetches from API if raw data is missing

**Exception:** Only use if you need to completely rebuild from fresh API data (rare case)

```bash
# ONLY use if you need fresh API data (will make 1,300+ API calls!)
uv run python tools/scripts/reingest_duckdb_data.py --keep-old
```

### Code Quality
```bash
# Format code
uv run black .

# Lint code
uv run ruff check .

# Type checking
uv run mypy .

# Run tests
uv run pytest

# Run specific test markers
uv run pytest -m unit
uv run pytest -m integration
uv run pytest -m performance
```

### Performance Analysis
```bash
# Run performance optimization tests
uv run python tools/test_performance_optimization.py
```

### Git Worktree Workflow

**⚠️ MANDATORY: All project development MUST use git worktree for isolation**

Git worktree allows multiple working directories from a single repository, enabling parallel development without branch switching conflicts.

#### Benefits
- **Isolation**: Each project works in its own directory
- **No branch switching**: Main branch stays clean for analysis work
- **Parallel development**: Multiple projects can progress simultaneously
- **Clean separation**: Easy to review changes per project

#### Basic Worktree Operations

```bash
# Create new worktree with new branch
git worktree add -b feature/project-name ../garmin-project-name

# Create worktree from existing branch
git worktree add ../garmin-project-name feature/project-name

# List all worktrees
git worktree list

# Remove worktree (after merging)
git worktree remove ../garmin-project-name

# Cleanup stale worktrees
git worktree prune
```

#### Project Development Workflow

**1. Planning Phase** (project-planner agent):
```bash
# Agent works on main branch directly
# Creates planning.md in docs/project/{YYYY-MM-DD}_{project_name}/
# Commits planning.md to main branch
# No worktree created at this stage

# Benefits:
# - Planning document immediately visible to all
# - Easy review and approval process
# - Main branch history includes planning
```

**2. Implementation Phase** (tdd-implementer agent):
```bash
# Agent creates worktree from latest main
git worktree add -b feature/{project_name} ../garmin-{project_name} main
cd ../garmin-{project_name}
uv sync  # MANDATORY

# Agent works within worktree directory
# All file operations use worktree paths
# Commits are made to feature branch
# planning.md is referenced from main branch
# Main branch code remains untouched

# Benefits:
# - Fresh start from latest main (no stale code)
# - Isolated development environment
# - Planning changes don't conflict with implementation
```

**3. Completion Phase**:
```bash
# Review changes in worktree
git diff main..feature/project-name

# Merge to main (from main repo directory)
git checkout main
git merge feature/project-name

# Remove worktree after successful merge
git worktree remove ../garmin-project-name
```

#### Worktree Directory Structure

```
claude_workspace/
├── garmin/                                    # Main worktree (main branch)
│   ├── data/                                  # Shared data (not project-specific)
│   ├── docs/project/                          # Planning documents
│   └── ...
├── garmin-rag-interval-analysis/              # Project worktree
│   ├── tools/rag/queries/                     # New code
│   ├── tests/rag/                             # New tests
│   └── docs/project/.../planning.md           # Planning doc (symlinked or copied)
└── garmin-split-stability/                    # Another project worktree
    └── ...
```

#### Best Practices

**DO:**
- ✅ Planning on main: Commit planning.md to main directly
- ✅ Implementation in worktree: Create worktree when starting implementation
- ✅ Use descriptive branch names: `feature/split-stability-precalc`
- ✅ Run `uv sync` immediately after worktree creation
- ✅ Commit regularly within worktree
- ✅ Merge to main only after all tests pass
- ✅ Remove worktree after successful merge

**DON'T:**
- ❌ Create worktree during planning phase
- ❌ Edit main branch directly for implementation work
- ❌ Create worktree without branch name
- ❌ Leave stale worktrees after project completion
- ❌ Share data/ directory modifications across worktrees

#### Agent Integration

**project-planner Agent:**
1. Works on main branch directly
2. Creates `docs/project/{YYYY-MM-DD}_{project_name}/planning.md`
3. Commits planning.md to main
4. **Does NOT create worktree**

**tdd-implementer Agent:**
1. Reads planning.md from main branch
2. Creates git worktree from latest main
3. Runs `uv sync` in worktree
4. Works within worktree directory
5. Creates commits in feature branch
6. After completion, merges to main and removes worktree

**Why this separation:**
- Planning can be reviewed/modified without worktree overhead
- Implementation starts from latest main (avoids stale code issues)
- Reduces worktree lifetime (only during active implementation)

See agent definitions (`.claude/agents/`) for implementation details.

## Critical Data Source Requirements

### Split Analysis Data Sources
- **MUST USE**: `splits.json` (lapDTOs array) for individual 1km lap analysis
- **NEVER USE**: `typed_splits.json` (contains aggregated data, cannot provide individual split details)

### Temperature Data Sources
- **MUST USE**: `weather.json` external temperature (accurate weather station data)
- **NEVER USE**: `splits.json` temperature (device temperature affected by body heat, 5-8°C higher)

### Elevation Data Processing
- **Source**: Raw data `lapDTOs` contains `elevationGain`, `elevationLoss`, `maxElevation`, `minElevation`
- **Processing**: `GarminIngestWorker.create_parquet_dataset()` extracts elevation data to performance.json
- **Analysis**: `_calculate_split_metrics()` generates terrain classifications (平坦/起伏/丘陵/山岳)
- **Issue Fixed**: Elevation data was previously missing from pre-formatted data, causing "0m elevation" in reports

## Project Management

### Project Directory Structure

Development projects are organized under `docs/project/`:

```
docs/project/
└── {YYYY-MM-DD}_{project_name}/
    ├── planning.md                  # [REQUIRED] Project planning (from project-planner agent)
    ├── completion_report.md         # [REQUIRED] Completion report (from completion-reporter agent)
    └── {specification_files}.md     # [OPTIONAL] Additional specifications
```

### Active Projects

- **2025-10-11_cache_partial_refetch**: Cache partial refetch feature with `force_refetch` parameter for selective API data updates (Phases 1-5 completed)
- **2025-10-10_duckdb_inserter_cleanup**: Added 7 missing normalized table schemas to db_writer._ensure_tables(), body composition optimization, deprecated code removal (Phases 1-4 completed)
- **2025-10-09_rag_interval_analysis_tools**: RAG interval analysis tools implementation with activity_details.json integration - ActivityDetailsLoader, IntervalAnalyzer, TimeSeriesDetailExtractor, FormAnomalyDetector, MCP server integration (Phases 1-6 completed)
- **2025-10-09_garmin_ingest_refactoring**: GarminIngestWorker refactoring for cache-first approach and process_activity unification (Phases 0-5 completed)
- **2025-10-07_core_system_restoration**: Body composition data specification fix and DuckDB schema documentation
- **2025-10-07_report_generation_update**: Worker-based report generation system implementation

### Project Workflow

1. **Planning Phase**
   - Create project directory under `docs/project/`
   - Write project plan document with goals and phases
   - Move/create specification documents
   - Set up implementation progress tracking

2. **Development Phase**
   - Follow implementation phases defined in project plan
   - Update progress regularly in implementation_progress.md
   - Commit changes with logical separation
   - Run tests and quality checks

3. **Completion Phase**
   - Write completion report
   - Update relevant documentation (CLAUDE.md, etc.)
   - Archive project artifacts
   - Document lessons learned

### Standard Project Files

**planning.md** (generated by project-planner agent):
- Overview: Project summary and background
- Goals: Clear, measurable objectives
- Architecture: System design and data flow
- Implementation Phases: Step-by-step breakdown
- Acceptance Criteria: Measurable completion criteria
- Test Plan: Unit, integration, performance tests

**completion_report.md** (generated by completion-reporter agent):
- Test Results: Unit, integration, performance test metrics
- Coverage Report: Code coverage statistics
- Code Quality: Black, Ruff, Mypy check results
- Acceptance Criteria Review: Comparison against planning.md
- Implementation Summary: What was built and how

## Important Notes

- Subagents cannot execute Task tools to call other subagents
- Use the main Claude instance to orchestrate multi-step workflows
- Data caching is aggressive to avoid API rate limits
- Always validate data sources (splits.json vs typed_splits.json) before analysis
- Japanese language is required for all analysis reports (output to `result/`); system documentation and code remain in English
