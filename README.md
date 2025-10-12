# Garmin Performance Analysis System

> **⚠️ Unofficial Tool**: This is a community-developed project for personal use, not affiliated with Garmin Ltd.

A comprehensive running performance analysis system that integrates with Garmin Connect to provide detailed split-by-split analysis with environmental integration.

## Features

- **Garmin MCP Integration**: Direct connection to Garmin Connect for data retrieval
- **DuckDB Backend**: Efficient storage and querying of performance data
- **Multi-agent Analysis**: Specialized agents for different analysis types
- **Japanese Reports**: All analysis reports generated in Japanese
- **Environmental Integration**: Weather, terrain, and body condition analysis
- **Performance Tracking**: Historical trend analysis and workout comparison

## Architecture

### Data Flow

```
Garmin API → Raw Data → Performance Analysis → DuckDB → Analysis Reports
```

### Core Components

- **Data Ingestion** (`tools/ingest/`): Collects and processes Garmin data
- **Database Layer** (`tools/database/`): DuckDB integration for efficient queries
- **Analysis Agents** (configured in `.claude/`): Specialized analysis workflows
- **MCP Servers** (`servers/`): Custom MCP servers for data access
- **Reporting** (`tools/reporting/`): Template-based report generation

## Installation

```bash
# Install dependencies
uv sync

# Install with development tools
uv sync --extra dev
```

## Usage

### Individual Activity Analysis

```bash
# Analyze a specific activity
/analyze-activity <activity_id> <date>
```

### Batch Analysis

```bash
# Run batch analysis for date range
uv run python tools/batch/batch_planner.py
```

### Bulk Fetch Activity Details

Fetch detailed activity data (maxchart=2000) for all activities missing `activity_details.json`:

```bash
# Show what would be fetched (dry run)
uv run python tools/bulk_fetch_activity_details.py --dry-run

# Fetch missing activity_details.json files
uv run python tools/bulk_fetch_activity_details.py

# Force re-fetch even if files exist
uv run python tools/bulk_fetch_activity_details.py --force

# Adjust API rate limit delay (default: 1.0 seconds)
uv run python tools/bulk_fetch_activity_details.py --delay 2.0
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

- `data/raw/`: Immutable Garmin API responses
- `data/performance/`: Pre-processed performance metrics
- `data/database/`: DuckDB database files
- `result/`: Final analysis reports

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

#### Default Behavior

If `.env` is not configured, the system uses default directories:
- Data: `./data`
- Results: `./result`

#### Benefits

- **Privacy**: Personal health data stored outside the Git repository
- **Flexible Storage**: Use external drives or NAS for large datasets
- **Environment Separation**: Different paths for development/production

For more details, see `docs/GITHUB_PUBLISHING_CHECKLIST.md`.

## MCP Servers

This project uses the following MCP servers (configured in `.mcp.json`):

- **garmin-db**: DuckDB-based performance data queries and section analysis storage
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
