# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## System Overview

This is a Garmin running performance analysis system that uses the Garmin MCP server to collect data and generate comprehensive running analysis reports. The system focuses on detailed split-by-split analysis with environmental integration (terrain, weather, body condition).

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

### Data Processing
```bash
# Regenerate all performance data from raw_data
uv run python tools/bulk_regenerate.py

# Create activity date mapping
uv run python tools/create_activity_date_mapping.py

# Fix directory date inconsistencies
uv run python tools/fix_directory_dates.py
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

## Architecture

### Core Components

- **Garmin MCP Integration**: Uses `garmin-mcp` server configured in `.mcp.json` for data collection
- **Multi-agent Analysis System**: Specialized agents for different analysis types (environment, wellness, performance, etc.)
- **Data Processing Pipeline**: Three-tier data transformation: raw → performance → analysis
- **Japanese Documentation**: All analysis reports are generated in Japanese

### Data Processing Architecture

The system follows a three-tier data transformation pipeline:

1. **Raw Data Layer** (`data/raw/`): Complete Garmin API responses collected and cached
2. **Performance Data Layer** (`data/performance/`, `data/parquet/`): Pre-processed metrics for analysis
3. **Analysis Layer** (`result/`): Final reports and insights

#### Key Processing Classes

- **GarminIngestWorker** (`tools/ingest/garmin_worker.py`): Complete data pipeline manager
  - `collect_data()`: Calls Garmin MCP functions to fetch activity data from API
  - `process_activity()`: Orchestrates the full pipeline from API to analysis-ready data
  - `create_parquet_dataset()`: Transforms raw lapDTOs into structured DataFrames
  - `_calculate_split_metrics()`: Pre-calculates performance metrics including elevation data
  - `save_data()`: Outputs parquet, performance.json, and precheck files

#### Data Flow

```
GarminIngestWorker: [API calls → raw_data.json → create_parquet_dataset() → {performance.json, .parquet, precheck.json}] → Analysis Agents → Reports
```

### Directory Structure

```
├── data/              # Multi-tier data storage
│   ├── raw/          # Immutable Garmin API responses
│   ├── performance/  # Pre-processed analysis-ready data
│   ├── parquet/      # Columnar data for efficient querying
│   ├── precheck/     # Data validation results
│   ├── database/     # DuckDB database files
│   └── individual/   # Section analysis intermediate data (organized by activity_id/)
├── result/           # Final analysis reports
│   └── individual/   # Individual activity reports (YEAR/MONTH/YYYY-MM-DD_activity_ID.md)
├── tools/            # Data processing and utility scripts
│   ├── ingest/       # Core data ingestion pipeline
│   ├── database/     # Database operations (reader, writer, inserters)
│   └── reporting/    # Report generation (worker, renderer, templates)
├── docs/             # Documentation and specifications
│   └── project/      # Project planning and progress tracking
│       └── {DATE}_project_name/  # Individual project directories
├── daily/            # Daily reflection notes
└── .claude/          # Claude Code configuration
```

### Data Files Naming Convention

- **Raw data**: `{activity_id}_raw.json` (complete Garmin API response)
- **Performance data**: `{activity_id}.json` (pre-processed metrics with Phase 1, 2 optimizations)
- **Parquet data**: `{activity_id}.parquet` (columnar format)
- **Precheck data**: `{activity_id}.json` (validation results)
- **Legacy formats**: `activity_{activity_id}_*.json` (splits, weather, gear, hr_zones)
- **Monthly activities**: `activities_{YYYY-MM}.json`

### Performance.json Structure (Phase 1, 2 Enhanced)

The `data/performance/{activity_id}.json` file contains 11 main sections:

**Existing Sections:**
1. `basic_metrics`: Distance, time, pace, HR, cadence, power
2. `heart_rate_zones`: Zone boundaries, time in zones, percentages
3. `efficiency_metrics`: Cadence stability, power efficiency, pace variability
4. `training_effect`: Aerobic/anaerobic training effect values
5. `power_to_weight`: W/kg ratio with statistical weight calculation
6. `split_metrics`: Per-split detailed metrics (22 fields per split)
7. `vo2_max`: VO2 max estimation data
8. `lactate_threshold`: Lactate threshold metrics

**Phase 1 Additions (2025-09-30):**
9. `form_efficiency_summary`: Pre-calculated GCT/VO/VR statistics
   - Average, min, max, std, variability for each metric
   - ★-rating evaluation (★★★★★ to ★★★☆☆)
   - Textual evaluation (e.g., "優秀な接地時間、効率的な地面反力利用")

10. `hr_efficiency_analysis`: Pre-calculated HR zone analysis
    - Zone distribution summary with percentages
    - Primary zone identification
    - Training type classification (aerobic_base/tempo_run/threshold_work/mixed_effort)
    - HR stability assessment (優秀/良好/変動あり)
    - Training quality description

**Phase 2 Additions (2025-09-30):**
11. `performance_trends`: Pre-calculated phase-based analysis
    - `warmup_phase`: Splits, avg metrics, evaluation
    - `main_phase`: Splits, avg metrics, pace stability
    - `finish_phase`: Splits, avg metrics, fatigue assessment
    - `pace_consistency`: Coefficient of variation (lower = more consistent)
    - `hr_drift_percentage`: HR drift from warmup to finish (< 5% ideal)
    - `cadence_consistency`: "高い安定性" or "変動あり"
    - `fatigue_pattern`: "適切な疲労管理" / "軽度の疲労蓄積" / "顕著な疲労蓄積"

**Performance Optimization Impact:**
- Phase 1: ~1,100 tokens saved per activity (form + HR efficiency pre-calculation)
- Phase 2: ~1,000 tokens saved per activity (performance trends pre-calculation)
- **Total**: ~2,100 tokens saved per activity (~40% reduction in analysis token usage)

## Agent System

### Specialized Agents

The system uses specialized agents that cannot call each other directly. Use the main Claude instance to orchestrate workflows:

- **data-collector**: Garmin MCP data collection and caching
- **data-validator**: Data integrity verification and quality checks
- **split-analyst**: Individual split analysis with environmental integration
- **performance-analyst**: Heart rate zones, biomechanics, performance trends
- **report-generator**: Final report compilation from intermediate results
- **monthly-analyst**: Monthly trend analysis and goal tracking
- **wellness-analyst**: Sleep, stress, recovery assessment
- **environment-analyst**: Weather condition impact analysis
- **body-composition-analyst**: Weight and body composition trends

### Workflow Execution

Use the documented workflow in `WORKFLOW.md`. The standard individual activity analysis follows:

1. **data-collector** → 2. **data-validator** → 3. **split-analyst** + **performance-analyst** (parallel) → 4. **report-generator**

Example execution:
```bash
# Individual activity analysis
Task: data-collector
prompt: "Activity ID 20464005432 (2025-09-22) のGarminデータを収集・キャッシュしてください。"

Task: split-analyst
prompt: "Activity ID 20464005432 (2025-09-22) のスプリット分析を実行してください。splits.jsonのlapDTOs配列使用、weather.json気温データ使用必須。"
```

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

## Result Directory Structure

Results are organized hierarchically:
```
data/individual/         # Section analysis intermediate data (DuckDB-backed)
└── {ACTIVITY_ID}/      # Section analysis JSON files (legacy, for DuckDB migration)

result/
├── individual/         # Individual activity final reports
│   └── {YEAR}/{MONTH}/{YYYY-MM-DD}_activity_{ACTIVITY_ID}.md
├── monthly/{YEAR}/{MONTH}/
└── special/            # Specialized analyses
```

**Note**: Section analysis data is now stored in DuckDB and accessed via `mcp__garmin-db__get_section_analysis`. Intermediate JSON files in `data/individual/` are legacy files for migration purposes.

## MCP Integration

The system uses multiple MCP servers configured in `.mcp.json`:

### Garmin MCP Server
Connects to Garmin Connect for data retrieval:
- Activity data retrieval
- Split and performance metrics
- Environmental conditions
- Body composition tracking
- Training status and readiness

### Garmin DB MCP Server
**⚠️ RECOMMENDED: Use this MCP server for efficient DuckDB access to performance data**

Provides efficient section-based access to DuckDB performance data, plus write capabilities for data insertion, **and advanced RAG query tools for trend analysis and workout comparison**.

**Read Tools (70-80% token reduction):**
- `mcp__garmin-db__get_performance_section`: Get specific sections from performance data
- `mcp__garmin-db__get_section_analysis`: Get section analysis data from DuckDB
- `mcp__garmin-db__get_splits_pace_hr`: Get pace and HR progression from splits (lightweight, ~9 fields/split)
- `mcp__garmin-db__get_splits_form_metrics`: Get form efficiency metrics from splits (lightweight, ~6 fields/split)
- `mcp__garmin-db__get_splits_elevation`: Get elevation and terrain data from splits (lightweight, ~7 fields/split)

**Write Tools (DuckDB data insertion):**
- `mcp__garmin-db__insert_performance_data`: Insert performance.json into DuckDB
- `mcp__garmin-db__insert_section_analysis`: Insert section analysis JSON file into DuckDB (legacy)
- `mcp__garmin-db__insert_section_analysis_dict`: **[RECOMMENDED]** Insert section analysis dict directly into DuckDB (no file creation)

**RAG Query Tools (Phase 3: Trend Analysis & Comparison):**
- `mcp__garmin-db__compare_similar_workouts`: Find and compare similar past activities
- `mcp__garmin-db__get_performance_trends`: Analyze performance trends for specific metrics over time
- `mcp__garmin-db__extract_insights`: Extract insights from section analyses using keyword-based search

### JSON Utils MCP Server
**⚠️ MANDATORY: Always use these MCP tools instead of Read/Write for JSON files**

Provides safe JSON read/write operations for LLM agents:
- `mcp__json_utils__json_read`: Safe JSON reading with encoding auto-detection
- `mcp__json_utils__json_write`: Atomic JSON writing (temp file → rename for corruption prevention)
- `mcp__json_utils__json_update`: JSON merge operations (shallow/deep)
- `mcp__json_utils__json_get`: Nested key retrieval (dot notation: `metadata.activityId`)
- `mcp__json_utils__json_set`: Nested key modification
- `mcp__json_utils__json_validate`: JSON integrity validation

### Markdown Utils MCP Server
**⚠️ RECOMMENDED: Use these MCP tools for Markdown files to enable section-based operations**

Provides safe Markdown read/write operations for LLM agents:
- `mcp__markdown_utils__markdown_read`: Safe Markdown reading with encoding auto-detection
- `mcp__markdown_utils__markdown_write`: Atomic Markdown writing (temp file → rename for corruption prevention)
- `mcp__markdown_utils__markdown_list_headings`: List all headings with levels and line numbers
- `mcp__markdown_utils__markdown_get_section`: Extract specific section by heading
- `mcp__markdown_utils__markdown_update_section`: Update specific section by heading
- `mcp__markdown_utils__markdown_get_frontmatter`: Get YAML front matter
- `mcp__markdown_utils__markdown_set_frontmatter`: Set YAML front matter
- `mcp__markdown_utils__markdown_append`: Append content to file

### Report Generator MCP Server
**⚠️ MANDATORY: Use this MCP tool for efficient report generation**

Jinja2テンプレートベースでレポート構造を生成し、LLMが洞察のみを追加する効率的なレポート生成システム。

**提供するツール:**
- `mcp__report-generator__create_report_structure`: テンプレートからレポート構造を生成
- `mcp__report-generator__finalize_report`: 最終レポートを保存（一時ファイルから移動）

## Serena Integration Guidelines

### Mandatory Serena Usage

**Always use serena MCP tools for the following operations:**

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

### Serena First Principle

**Before using direct file operations (Read, Edit, Write), always consider:**

1. **Code Exploration**: Use `get_symbols_overview` before reading entire files
2. **Targeted Reading**: Use `find_symbol` with `include_body=true` for specific functions/classes
3. **Safe Editing**: Use symbol-based editing instead of line-based editing
4. **File Operations**: Use `list_dir` and `find_file` instead of bash `ls` and `find`
5. **Pattern Search**: Use `search_for_pattern` instead of bash `grep`

### When NOT to Use Serena

- Reading non-code files (JSON, MD, log files)
- Simple file existence checks
- Direct data file operations (parquet, JSON data files)
- MCP function calls for Garmin data

## Project Management

### Project Directory Structure

Development projects are organized under `docs/project/`:

```
docs/project/
└── {YYYY-MM-DD}_{project_name}/
    ├── project_plan.md              # Project overview, goals, and implementation phases
    ├── {specification_files}.md     # Technical specifications
    └── implementation_progress.md   # Implementation progress tracking
```

### Active Projects

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

### Project Plan Template

Each project should have:
- **Overview**: Project summary and background
- **Goals**: Clear, measurable objectives
- **Architecture**: System design and data flow
- **Implementation Phases**: Step-by-step breakdown
- **Success Criteria**: Measurable completion criteria
- **References**: Related files and documentation

## Important Notes

- Subagents cannot execute Task tools to call other subagents
- Use the main Claude instance to orchestrate multi-step workflows
- Data caching is aggressive to avoid API rate limits
- Always validate data sources (splits.json vs typed_splits.json) before analysis
- Japanese language is required for all analysis outputs
