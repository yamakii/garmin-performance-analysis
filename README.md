# Garmin Performance Analysis System

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

- **garmin-mcp**: Garmin Connect data access
- **garmin-db**: DuckDB performance data queries
- **json-utils**: Safe JSON operations
- **markdown-utils**: Markdown file operations
- **report-generator**: Template-based report generation
- **serena**: Code navigation and editing

## Configuration

See `CLAUDE.md` for detailed configuration and usage guidelines.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
