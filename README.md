# Garmin Performance Analysis System

> **⚠️ Unofficial Tool**: This is a community-developed project for personal use, not affiliated with Garmin Ltd.

A comprehensive running performance analysis system that integrates with Garmin Connect to provide detailed split-by-split analysis with environmental integration. Built on a **DuckDB-first** storage layer and a **MCP-first** tooling layer.

## Features

- **Garmin MCP Integration**: 46 token-optimized MCP tools for data retrieval and analysis, declared from a single-source `tools/` registry
- **DuckDB Backend**: Normalized storage (14 tables, 100+ activities) for efficient querying
- **Multi-agent Analysis**: 2 section-analysis agents (`unified-section-analyst` + `split-section-analyst`) that run in parallel
- **Japanese Analysis**: All analysis stored in DuckDB and viewed via the web app (`packages/garmin-web`)
- **Environmental Integration**: Weather, terrain, and body condition analysis
- **Performance Tracking**: Historical trend analysis, race readiness, ACWR load, and workout comparison

## Architecture

### Data Flow

```
Garmin API → Raw JSON → DuckDB → MCP Tools → Analysis → Web App (packages/garmin-web)
```

### Core Components

The project is a uv workspace with two packages:

- **`packages/garmin-mcp-server`**: Python MCP server
  - `src/garmin_mcp/ingest/`: API → raw data collection (`ApiClient`, `RawDataFetcher`, `DuckDBSaver`)
  - `src/garmin_mcp/database/`: DuckDB read/write layer (`inserters/`, `readers/`, `migrations/`)
  - `src/garmin_mcp/tools/`: `ToolDef` registry — single source for all 46 MCP tools
  - `src/garmin_mcp/scripts/`: ingestion, regeneration, and backfill utilities
- **`packages/garmin-web`**: FastAPI backend + Vite/React SPA that renders analysis stored in DuckDB
- **Analysis Agents & Skills** (`.claude/`): section-analysis agents and user-invocable skills (`/analyze-activity`, `/plan-training`, etc.)

See `CLAUDE.md` for the full architecture and DuckDB schema reference.

## Installation

```bash
# Install dependencies (including development tools)
uv sync --extra dev

# Configure data/result directories and auto-load env
cp .env.example .env   # edit GARMIN_DATA_DIR, GARMIN_RESULT_DIR
direnv allow
```

## Usage

### Individual Activity Analysis

Run inside Claude Code — ingests the data, runs the section-analysis agents in parallel, and stores results in DuckDB:

```
/analyze-activity <date>      # e.g. /analyze-activity 2025-10-15 (defaults to today)
```

### Fetch Raw Data

```bash
# Fetch raw data from a start date
uv run python -m garmin_mcp.scripts.bulk_fetch_raw_data --start-date 2025-10-01

# Fetch detailed activity data for specific activities
uv run python -m garmin_mcp.scripts.bulk_fetch_activity_details --activity-ids 12345 67890
```

### Surgical DuckDB Update

```bash
# Regenerate selected tables for selected activities
uv run python -m garmin_mcp.scripts.regenerate_duckdb --tables splits --activity-ids 12345 --force
```

## Development

### Code Quality

```bash
# Format code
uv run black .

# Lint
uv run ruff check .

# Type check
uv run mypy .

# Run tests
uv run pytest
```

### Pre-commit Hooks

```bash
# Install hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

## Data Structure

- `data/raw/`: Immutable Garmin API responses (one set of files per activity)
- `data/database/`: DuckDB database file (`garmin_performance.duckdb`)
- `result/training_plans/`: Generated training plans

> `data/` and `result/` are git-ignored and configurable via `.env` (`GARMIN_DATA_DIR`, `GARMIN_RESULT_DIR`).

### Configurable Data Paths

**Privacy Protection**: Keep your personal health data separate from the codebase by configuring custom data directories.

#### Setup

1. **Copy the example configuration**:
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` with your preferred paths**:
   ```bash
   # Use absolute paths for safety
   GARMIN_DATA_DIR=/home/user/garmin_data/data
   GARMIN_RESULT_DIR=/home/user/garmin_data/results
   ```

3. **Run the application**:
   The system automatically uses the configured paths. No code changes needed!

4. **(Optional) Setup direnv for automatic environment loading**:
   ```bash
   # Install direnv if not already installed
   # Ubuntu/Debian: sudo apt install direnv
   # Or: curl -sfL https://direnv.net/install.sh | bash

   # Add direnv hook to your shell (~/.bashrc or ~/.zshrc)
   eval "$(direnv hook bash)"  # For bash
   # eval "$(direnv hook zsh)"  # For zsh

   # Allow direnv to load .envrc
   direnv allow
   ```

   With direnv configured, environment variables are automatically loaded when you `cd` into the project directory.

#### Default Behavior

If `.env` is not configured, the system uses default directories:
- Data: `./data`
- Results: `./result`

#### Benefits

- **Privacy**: Personal health data stored outside the Git repository
- **Flexible Storage**: Use external drives or NAS for large datasets
- **Environment Separation**: Different paths for development/production

## MCP Servers

MCP servers are configured per-user in a local, git-ignored `.mcp.json`:

- **garmin-db**: DuckDB-based performance data queries and section analysis storage (46 tools)
- **serena**: Symbol-aware code navigation and editing operations

## Configuration

See `CLAUDE.md` for detailed configuration and usage guidelines.

## Disclaimer

**This is an unofficial, community-developed tool and is not affiliated with, endorsed by, or supported by Garmin Ltd. or its affiliates.**

- This project uses the third-party Python library [`garminconnect`](https://github.com/cyberjunky/python-garminconnect) (MIT License) to access personal Garmin Connect data
- This tool is intended for **personal use only** to analyze your own fitness data
- Users are responsible for complying with Garmin's Terms of Service
- Use at your own risk - the authors assume no liability for any issues arising from the use of this software

**Privacy Note:** This tool processes your personal health data locally. Ensure you keep your data directories (configured via `.env`) secure and never commit personal data to version control.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

The project uses the following third-party libraries:
- [`garminconnect`](https://github.com/cyberjunky/python-garminconnect) - MIT License
- Other dependencies are listed in `pyproject.toml` with their respective licenses
