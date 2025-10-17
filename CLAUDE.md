# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## System Overview

Garmin running performance analysis system with **DuckDB-first architecture** (raw → DuckDB → analysis), multi-agent analysis, normalized storage, and token optimization (~40% reduction).

**Key Features:**
- 5 specialized section analysis agents (split/phase/summary/efficiency/environment)
- DuckDB-backed storage with normalized tables (single source of truth)
- Direct raw data insertion (no intermediate performance.json)
- Token-optimized queries (70-98.8% reduction via MCP tools)
- Environment variable support for configurable data/result paths
- Japanese analysis reports (code/docs in English)

## Architecture

### Data Processing Pipeline

```
Raw Data (API) → DuckDB (Direct Insertion) → Analysis → Reports
```

**Two-tier transformation:**
1. **Raw Layer** (`data/raw/`): Garmin API responses (per-API caching: 8 API files/activity)
2. **Storage & Analysis Layer** (`data/database/`, `result/`): DuckDB normalized tables + section analyses → final reports (Markdown)

**Key Changes (DuckDB-First Migration):**
- ~~Performance Layer removed~~ - data flows directly: Raw → DuckDB
- No intermediate `performance.json` generation
- All inserters use single-mode raw data pipeline (no backward compatibility)

**Key Classes:**
- `GarminIngestWorker`: API → raw → DuckDB pipeline
  - `collect_data(activity_id, force_refetch=None)`: Fetch from API with selective cache refresh
  - `process_activity(activity_id, date, force_refetch=None)`: Full pipeline orchestration
- `GarminDBWriter`: DuckDB insertion (8 normalized tables including time_series_metrics)
- `ReportGeneratorWorker`: Template-based report generation

**DuckDB Schema:**
- Normalized tables: `splits`, `form_efficiency`, `heart_rate_zones`, `hr_efficiency`, `performance_trends`, `vo2_max`, `lactate_threshold`
- **Time series table**: `time_series_metrics` (26 metrics × 1000-2000 rows/activity, 98.8% token reduction)
- Metadata: `activities` (foreign key relationships)
- Analysis: `section_analyses` (agent results)

### Directory Structure

```
├── data/              # Configurable via GARMIN_DATA_DIR (default: ./data)
│   ├── raw/          # API responses (activity/{id}/{api}.json, weight/{date}.json)
│   └── database/     # DuckDB files (primary storage)
├── result/           # Configurable via GARMIN_RESULT_DIR (default: ./result)
│   ├── individual/   # Activity reports (YEAR/MONTH/YYYY-MM-DD_id.md)
│   └── monthly/      # Trend analysis
├── tools/            # Data processing (ingest/, database/, reporting/, rag/)
├── docs/project/     # Project planning (active: 2025-*, archived: _archived/)
└── .claude/          # Agent definitions and slash commands
```

**Note:** `data/performance/` directory removed - all data now stored in DuckDB.

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
- **Normalized Tables**:
  - `get_form_efficiency_summary`: Form metrics (GCT, VO, VR)
  - `get_hr_efficiency_analysis`: HR efficiency + **training type** (used by phase-section-analyst for adaptive evaluation)
  - `get_heart_rate_zones_detail`: HR zone boundaries and time distribution
  - `get_vo2_max_data`: VO2 max estimation
  - `get_lactate_threshold_data`: Lactate threshold metrics
- **Splits Data** (lightweight, with statistics mode):
  - `get_splits_pace_hr(activity_id, statistics_only=False)` (split/phase)
  - `get_splits_form_metrics(activity_id, statistics_only=False)` (form)
  - `get_splits_elevation(activity_id, statistics_only=False)` (environment)
  - Set `statistics_only=True` for 80% token reduction (summary only)
- **Deprecated** ⚠️:
  - `get_splits_all` → Use `export()` (Phase 1) or lightweight splits + statistics mode
  - `get_section_analysis` → Use `extract_insights()`
- **Write**: `insert_section_analysis_dict` (recommended), `insert_section_analysis` (legacy)
- **RAG Queries**: `get_interval_analysis`, `get_split_time_series_detail` (DuckDB-based, 98.8% token reduction), `get_time_range_detail`, `detect_form_anomalies_summary` (lightweight, ~700 tokens, 95% reduction), `get_form_anomaly_details` (filtered details, variable size), `analyze_performance_trends`, `extract_insights`, `compare_similar_workouts`

**Note:** Prefer lightweight splits APIs for targeted analysis. Time series tools use DuckDB for 98.8% token reduction. activity_details.json provides 26 second-by-second metrics.

### MCP Function Selection Guidelines (Phase 0 Architecture)

**Token Optimization Strategy:**
- Use `statistics_only=True` for trend analysis and overview queries
- Use full data mode only when individual split details are needed

**Function Categories:**

1. **Statistical Queries (Recommended)** - ~200-300 bytes
   - `get_splits_pace_hr(activity_id, statistics_only=True)`
   - `get_splits_form_metrics(activity_id, statistics_only=True)`
   - `get_splits_elevation(activity_id, statistics_only=True)`
   - Returns: mean, median, std, min, max for each metric

2. **Full Data Queries** - ~500-1000 bytes
   - `get_splits_pace_hr(activity_id, statistics_only=False)` (default)
   - `get_splits_form_metrics(activity_id, statistics_only=False)` (default)
   - `get_splits_elevation(activity_id, statistics_only=False)` (default)
   - Returns: per-split data (10-20 splits)

3. **Deprecated Functions** ⚠️ - Use alternatives
   - `get_splits_all(activity_id)` → Use `export()` (Phase 1) or lightweight splits + `statistics_only=True`
   - `get_section_analysis(activity_id, section_type)` → Use `extract_insights()`
   - Both have `max_output_size` limits (default 10KB)

#### Statistics Mode Examples

**Use Case 1: Trend Analysis (statistics_only=True)**
```python
# Get pace statistics across all splits (200 bytes vs 1KB)
stats = get_splits_pace_hr(activity_id=12345, statistics_only=True)
# Returns: {"pace": {"mean": 305.2, "median": 303.1, ...}}
```

**Use Case 2: Individual Split Analysis (statistics_only=False)**
```python
# Get pace for each 1km split (default behavior)
splits = get_splits_pace_hr(activity_id=12345, statistics_only=False)
# Returns: [{"split": 1, "pace": 303.5, "hr": 162}, ...]
```

**Use Case 3: Agent Usage**
```markdown
# In agent prompts (.claude/agents/*.md):
Use `get_splits_pace_hr(activity_id, statistics_only=True)` for overview analysis.
Use `statistics_only=False` only when individual split comparison is needed.
```

**Form Anomaly Detection (v2 - 95% Token Reduction):**
- **Summary First**: Always start with `detect_form_anomalies_summary()` for multi-activity overview (~700 tokens)
- **Details On Demand**: Use `get_form_anomaly_details()` with filters for specific analysis (variable size)
- **Migration**: Old `detect_form_anomalies()` API removed (breaking change) - see examples below

```python
# Before (14.3k tokens per activity):
detect_form_anomalies(activity_id=12345)

# After - Summary for overview (700 tokens):
summary = detect_form_anomalies_summary(activity_id=12345)
# Returns: total count, severity distribution, temporal clusters, top 5 anomalies, recommendations

# After - Details with filtering (e.g., 1.5k tokens for 5 IDs):
details = get_form_anomaly_details(
    activity_id=12345,
    filters={"anomaly_ids": [1, 3, 5, 12, 15], "limit": 5}  # Specific anomalies only
)

# Filter by time range (15-20 minutes):
details = get_form_anomaly_details(
    activity_id=12345,
    filters={"time_range": (900, 1200)}
)

# Filter by cause (elevation-related only):
details = get_form_anomaly_details(
    activity_id=12345,
    filters={"causes": ["elevation_change"], "limit": 10}
)

# Filter by severity (z_score > 3.0):
details = get_form_anomaly_details(
    activity_id=12345,
    filters={"min_z_score": 3.0}
)
```

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

#### Training Type-Aware Phase Evaluation

The **phase-section-analyst** uses training type categorization for adaptive phase evaluation:

**Training Type Categories** (retrieved via `get_hr_efficiency_analysis()`):

1. **low_moderate** (recovery, aerobic_base):
   - Warmup/cooldown not required
   - No warnings for missing phases
   - Relaxed, positive tone
   - 3-phase structure (warmup/run/cooldown)

2. **tempo_threshold** (tempo, lactate_threshold):
   - Warmup/cooldown recommended
   - Suggestive/educational tone ("推奨", "お勧め")
   - Moderate ratings if missing (★★★☆☆)
   - 3-phase structure (warmup/run/cooldown)

3. **interval_sprint** (vo2max, anaerobic_capacity, speed):
   - Warmup/cooldown required
   - Assertive tone with injury warnings ("⚠️", "怪我リスク")
   - Lower ratings if missing (★★☆☆☆)
   - 4-phase structure (warmup/run/recovery/cooldown)

This enables adaptive evaluation where missing phases are treated as critical for high-intensity workouts but acceptable for recovery runs, providing contextually appropriate feedback.

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
uv sync                          # Basic (runtime only)
uv sync --extra dev              # With dev tools (REQUIRED for development: pytest-xdist, black, ruff, mypy, pre-commit)
uv sync --extra performance      # With performance monitoring (rich, pygments)

# Git Worktree (MANDATORY for project development)
git worktree add -b feature/name ../path main
cd ../path
uv sync --extra dev  # MANDATORY: Setup dev environment (includes pytest-xdist for pre-commit hooks)
mcp__serena__activate_project("/absolute/path")  # MANDATORY for agents

# Worktree management
git worktree list                # List all worktrees
git worktree remove ../path      # Remove after merge
git worktree prune               # Cleanup stale worktrees

# Worktree Safety Rules (CRITICAL)
# Before removing ANY worktree:
# 1. cd /path/to/worktree && git status
# 2. If uncommitted changes exist, report to user and ask for confirmation
# 3. NEVER use --force without explicit user approval

# Example:
# ❌ NEVER: git worktree remove ../some-worktree --force
# ✅ ALWAYS: cd ../some-worktree && git status  # Check first!
#           # If clean, then: git worktree remove ../some-worktree
```

**Worktree Workflow:**
- Planning: On main branch (no worktree)
- Implementation: Create worktree from main
- Completion: Merge to main, remove worktree

### Data Processing Scripts

| Operation | Script | Use Case |
|-----------|--------|----------|
| **Regenerate DuckDB** | `regenerate_duckdb.py` | After schema changes, data corruption, table-specific regeneration |
| **Fetch raw data** | `bulk_fetch_raw_data.py` | Add missing API data |
| **Fetch activity details** | `bulk_fetch_activity_details.py` | Specific to activity_details.json |
| **Migrate data** | `migrate_raw_data_structure.py`, `migrate_weight_data.py` | Format migrations |

**DuckDB Regeneration Options:**
- `--tables <table1> <table2> ...`: Regenerate specific tables only (11 available: activities, splits, form_efficiency, hr_efficiency, heart_rate_zones, performance_trends, vo2_max, lactate_threshold, time_series_metrics, section_analyses, body_composition)
- `--force`: Delete existing records before re-insertion (requires `--tables`)
- `--delete-db`: Delete database file before full regeneration (cannot be used with `--tables`)
- `--start-date`, `--end-date`: Filter by date range
- `--activity-ids`: Filter by specific activity IDs
- `--dry-run`: Preview changes without execution

**Usage Examples:**
```bash
# Single table regeneration after schema change
python tools/scripts/regenerate_duckdb.py --tables splits --start-date 2025-01-01 --end-date 2025-01-31

# Multiple tables for specific activities
python tools/scripts/regenerate_duckdb.py --tables splits form_efficiency --activity-ids 12345 67890

# Force re-insertion (delete + insert)
python tools/scripts/regenerate_duckdb.py --tables splits --activity-ids 12345 --force

# Full database regeneration
python tools/scripts/regenerate_duckdb.py --delete-db

# Dry run to preview
python tools/scripts/regenerate_duckdb.py --tables splits --dry-run
```

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

### Test Data Strategy

**CRITICAL: Automated tests must NEVER depend on real production data.**

**Test Type Guidelines:**

1. **Unit Tests** - Self-contained fixtures
   - Use `@pytest.fixture` for test data
   - No external dependencies (no database, no files)
   - Fast execution (<100ms per test)

2. **Integration Tests** - Mocks and fixtures only
   - ✅ USE: `pytest-mock` (`mocker.Mock()`, `mocker.patch()`)
   - ✅ USE: Factory fixtures (e.g., `mock_reader_factory`)
   - ❌ NEVER: Real DuckDB data queries
   - ❌ NEVER: Dependencies on section_analyses cache existence
   - Mock DuckDB connections for database integration tests

3. **Performance Tests** - Real data acceptable with safeguards
   - May use real data but must handle missing data gracefully
   - Skip test if required data unavailable (not fail)
   - Document data requirements in test docstrings

**Rationale:**
- Eliminates test flakiness from data modifications
- Tests pass regardless of production data state
- Clear test intent through explicit mock data
- Faster test execution (no I/O)

**Example (Integration Test):**
```python
@pytest.fixture
def mock_analysis_data():
    """Mock section analysis data for testing."""
    return {"evaluation": "テスト評価", "rating": "★★★★☆"}

@pytest.fixture
def mock_reader_factory(mocker):
    """Factory for creating mocked readers."""
    def _create_reader(analysis_data):
        reader = mocker.Mock()
        reader.get_section_analysis.return_value = analysis_data
        return reader
    return _create_reader

def test_evaluation_logic(mock_reader_factory, mock_analysis_data):
    """Test evaluation with mocked data (no real data dependency)."""
    reader = mock_reader_factory(mock_analysis_data)
    analysis = reader.get_section_analysis(12345, "phase")
    assert analysis["evaluation"] == "テスト評価"
```

## Critical Data Source Requirements

**Split Analysis:**
- ✅ USE: `splits.json` (lapDTOs) for 1km lap data
- ❌ NEVER: `typed_splits.json` (aggregated, no individual splits)

**Temperature:**
- ✅ USE: `weather.json` (external weather station)
- ❌ NEVER: `splits.json` temperature (device temperature, +5-8°C body heat)

**Elevation:**
- Source: `lapDTOs` → DuckDB (via inserters)
- Classification: 平坦/起伏/丘陵/山岳

## DuckDB Database Safety Rules

**CRITICAL: Database contains valuable activity data (100+ activities). Follow these rules strictly:**

1. **NEVER delete database without explicit user approval**
   - ❌ Do NOT propose `rm database.duckdb` or `--delete-db` as first solution
   - ✅ Always check data integrity first with read-only connection

2. **Error diagnosis protocol:**
   ```python
   # ALWAYS start with read-only check
   conn = duckdb.connect(db_path, read_only=True)
   count = conn.execute('SELECT COUNT(*) FROM activities').fetchone()[0]
   # If successful → data is intact, find alternative solution
   ```

3. **When database deletion is acceptable:**
   - User explicitly requests full regeneration
   - Read-only check confirms data corruption (not just write errors)
   - User confirms after seeing data loss impact

4. **Alternative solutions (try first):**
   - Delete specific records: `DELETE FROM section_analyses WHERE activity_id = X`
   - Regenerate specific tables: `--tables splits --activity-ids X`
   - Use new Python process (errors are often process-specific, not data corruption)

**Remember:** DuckDB errors during INSERT/UPDATE do not always mean data corruption. Check data first, delete last.

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
