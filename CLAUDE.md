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

Data and result directories can be configured via environment variables for privacy protection.

**Environment Variables:**
- `GARMIN_DATA_DIR`: Base data directory (default: `./data`)
- `GARMIN_RESULT_DIR`: Result directory (default: `./result`)

**Setup:** Copy `.env.example` to `.env` and set paths. The `.env` file is automatically loaded by `tools/__init__.py`. Optional: Use `direnv` for automatic environment loading (`.envrc` provided).

**Path Utility Module:** `tools/utils/paths.py` provides `get_data_base_dir()`, `get_result_dir()`, `get_raw_dir()`, `get_performance_dir()`, `get_precheck_dir()`, `get_database_dir()`, `get_weight_raw_dir()`

### Data Files Naming Convention

**Raw Data:**
- Activity: `data/raw/activity/{activity_id}/{api_name}.json` (per-API caching, 8 API files)
- Weight: `data/raw/weight/{YYYY-MM-DD}.json` (daily weigh-ins)
- Legacy activity: `{activity_id}_raw.json` (backward compatible)

**Processed Data:**
- Performance: `data/performance/{activity_id}.json`
- Precheck: `data/precheck/{activity_id}.json`
- Section analysis: DuckDB `data/database/` (primary storage)

Migration tools: `migrate_raw_data_structure.py`, `migrate_weight_data.py`

### Performance.json Structure

Contains 11 sections: (1-8) Base metrics (basic, HR zones, efficiency, training effect, power/weight, splits, VO2 max, lactate threshold), (9-10) Phase 1 optimizations (form efficiency, HR efficiency with ★-ratings), (11) Phase 2 optimization (performance trends with phase analysis).

**Token Optimization:** Phases 1-3 reduce analysis token usage by ~40% (~2,100 tokens/activity).

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

*Interval Analysis:*
- `mcp__garmin-db__get_interval_analysis`: Analyze interval training Work/Recovery segments
  - Auto-detects Work/Recovery intervals from pace changes
  - Calculates fatigue indicators (HR increase, pace degradation, GCT degradation)
  - Computes HR recovery rate (bpm/min)
  - Supports custom thresholds (pace_threshold_factor, min_work_duration, min_recovery_duration)
  - Use for: Interval training analysis, recovery efficiency assessment

*Time Series Detail:*
- `mcp__garmin-db__get_split_time_series_detail`: Get second-by-second metrics for a specific 1km split
  - Extracts 26 metrics × 1000+ seconds from activity_details.json
  - Returns time series with statistics (avg, std, min, max)
  - Detects anomalies using z-score thresholding
  - Use for: Split-level detailed analysis, anomaly investigation

- `mcp__garmin-db__get_time_range_detail`: Get second-by-second metrics for arbitrary time range
  - Supports custom start_time_s and end_time_s specification
  - More flexible than split-based analysis
  - Use for: Work/Recovery interval analysis, warmup/cooldown analysis

*Form Anomaly Detection:*
- `mcp__garmin-db__detect_form_anomalies`: Detect GCT/VO/VR anomalies and identify causes
  - Z-score based anomaly detection (customizable threshold)
  - Correlates anomalies with elevation changes, pace changes, and fatigue
  - Provides context (before/after 30s window)
  - Generates improvement recommendations
  - Use for: Form efficiency issues, terrain impact analysis

**RAG Query Tools (Phase 3: Trend Analysis & Performance Insights):**

- `analyze_performance_trends`: Long-term trend analysis for 10 metrics (linear regression, filtering by activity_type/temperature/distance)
- `extract_insights`: Keyword-based search in section analyses (improvements, concerns, patterns)
- `classify_activity_type`: Auto-classify into 6 training types (Base Endurance, Threshold Run, Sprint Intervals, etc.)
- `compare_similar_workouts`: Find and compare similar past workouts (Phase 4.5)

**Note:** activity_details.json provides 26 second-by-second metrics (HR, speed, cadence, GCT, VO, VR, elevation, power, etc.)

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

#### DuckDB Regeneration from Raw Data

**✅ RECOMMENDED: Use `regenerate_duckdb.py` script**

Regenerates DuckDB from existing raw data (performance.json is automatically generated as intermediate file):

```bash
# Regenerate all activities
uv run python tools/scripts/regenerate_duckdb.py

# Regenerate by date range
uv run python tools/scripts/regenerate_duckdb.py --start-date 2025-01-01 --end-date 2025-01-31

# Regenerate specific activity IDs
uv run python tools/scripts/regenerate_duckdb.py --activity-ids 12345 67890

# Delete old DuckDB before regeneration (complete reset)
uv run python tools/scripts/regenerate_duckdb.py --delete-db

# Dry run (show what would be regenerated)
uv run python tools/scripts/regenerate_duckdb.py --dry-run
```

**When to use:**
- After modifying performance.json or DuckDB schema
- After data corruption or inconsistency
- After adding new fields to normalized tables

**What it does:**
- Reads from `data/raw/activity/`
- Automatically generates performance.json (intermediate file)
- Inserts into DuckDB normalized tables
- **No API calls**: Only processes existing cached raw data

**Single Activity Regeneration:**
```python
from tools.ingest.garmin_worker import GarminIngestWorker

worker = GarminIngestWorker()

# If DuckDB cache exists: Returns cached data (no regeneration)
# If DuckDB cache missing but raw data exists: Regenerates from raw data
# If raw data missing: Fetches from API
result = worker.process_activity(activity_id, "YYYY-MM-DD")
```

#### API Fetching Scripts

**✅ RECOMMENDED: Use `bulk_fetch_raw_data.py` for comprehensive raw data fetching**

Fetch missing raw data from Garmin API (skips existing files by default):

```bash
# Fetch by date range (missing files only)
uv run python tools/scripts/bulk_fetch_raw_data.py --start-date 2025-01-01 --end-date 2025-01-31

# Fetch specific API types only
uv run python tools/scripts/bulk_fetch_raw_data.py --start-date 2025-01-01 --end-date 2025-01-31 --api-types weather vo2_max

# Fetch specific activity IDs
uv run python tools/scripts/bulk_fetch_raw_data.py --activity-ids 12345 67890 11111

# Force re-fetch even if files exist
uv run python tools/scripts/bulk_fetch_raw_data.py --start-date 2025-01-01 --end-date 2025-01-31 --force

# Dry run (show what would be fetched)
uv run python tools/scripts/bulk_fetch_raw_data.py --start-date 2025-01-01 --end-date 2025-01-31 --dry-run
```

**Legacy: `bulk_fetch_activity_details.py`** (specific to activity_details.json)

```bash
# Fetch activity_details.json for all activities
uv run python tools/scripts/bulk_fetch_activity_details.py

# Dry run
uv run python tools/scripts/bulk_fetch_activity_details.py --dry-run

# Force re-fetch
uv run python tools/scripts/bulk_fetch_activity_details.py --force
```

**When to use:**
- Adding new raw data to the system
- Fetching missing API data for specific activities
- Updating specific API data that has changed
- **Note**: Only fetches files that don't exist (unless `--force` is used)

#### Data Migration Scripts

```bash
# Migrate raw data structure (legacy → per-API format)
uv run python tools/scripts/migrate_raw_data_structure.py

# Migrate weight data structure
uv run python tools/scripts/migrate_weight_data.py --all

# Dry run (show what would be migrated)
uv run python tools/scripts/migrate_weight_data.py --dry-run --all

# Verify migration
uv run python tools/scripts/migrate_weight_data.py --verify
```

**Purpose:** Migrate data between different storage formats

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

Basic commands: `git worktree add -b feature/name ../path`, `git worktree list`, `git worktree remove ../path`

**Project Workflow:**
1. **Planning**: On main branch, commit planning.md (no worktree)
2. **Implementation**: Create worktree from main, run `uv sync`, activate Serena MCP
3. **Completion**: Merge to main, remove worktree

**Key points:** Run `uv sync` after worktree creation, activate Serena with worktree path, planning on main/implementation in worktree.

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

Current active projects in development (no completion report):

- **2025-10-12_mcp_tool_refactoring**: MCP server tool refactoring and optimization
- **2025-10-12_hr_zone_percentage_precalc**: Heart rate zone percentage pre-calculation optimization
- **2025-10-11_cache_partial_refetch**: Cache partial refetch feature with `force_refetch` parameter
- **2025-10-10_rag_unified_plan**: RAG system unified planning and architecture
- **2025-10-10_batch_section_analysis**: Batch section analysis implementation
- **2025-10-09_split_stability_precalculation**: Split stability metrics pre-calculation
- **2025-10-09_rag_interval_analysis_tools**: RAG interval analysis tools with activity_details.json
- **2025-10-07_restore_core_system**: Core system restoration and fixes
- **2025-10-07_report_generation_update**: Worker-based report generation system
- **2025-10-05_rag_system**: RAG system foundation and architecture

### Archived Projects

Completed projects are moved to `docs/project/_archived/` and contain `completion_report.md`:

- 2025-10-10_splits_time_range_duckdb
- 2025-10-10_section_analyst_normalized_access
- 2025-10-10_duckdb_inserter_cleanup
- 2025-10-10_configurable_data_paths
- 2025-10-09_weight_data_migration
- 2025-10-09_garmin_ingest_refactoring
- 2025-10-09_cleanup_unused_parquet
- 2025-10-09_bulk_activity_details_fetch
- 2025-10-07_planner_date_resolution
- 2025-10-07_db_writer_schema_sync

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
