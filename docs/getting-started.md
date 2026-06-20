# Getting Started

This guide walks a new user through the full cold-start path: install →
authenticate → fetch data → build the DuckDB → run your first analysis →
view it in the web app.

> This is an unofficial personal-use tool, not affiliated with Garmin. It reads
> **your own** Garmin Connect data. See the README disclaimer.

## 1. Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package/runtime manager)
- [direnv](https://direnv.net/) (optional, for auto-loading `.env`)
- A Garmin Connect account with running activities
- For the `/analyze-activity` workflow: Claude Code (the MCP server is driven by it)

## 2. Install

```bash
uv sync --extra dev
```

## 3. Configure `.env`

Copy the template and fill in your data directories and Garmin credentials:

```bash
cp .env.example .env
```

Edit `.env`:

```bash
# Where to store raw data and the DuckDB (keep personal data outside the repo)
GARMIN_DATA_DIR=/home/you/garmin_data
GARMIN_RESULT_DIR=/home/you/garmin_results

# Garmin Connect credentials (required to fetch data)
GARMIN_EMAIL=you@example.com
GARMIN_PASSWORD=your-garmin-connect-password
# GARMINTOKENS=~/.garth   # optional OAuth token cache dir (default ~/.garth)
```

If you use direnv:

```bash
direnv allow
```

Otherwise `.env` is auto-loaded by python-dotenv. `.env`, `data/`, and `result/`
are git-ignored — your personal data never enters version control.

### Authentication notes

On the first fetch the system performs a token-based login and caches OAuth
tokens under `GARMINTOKENS` (default `~/.garth`). Later runs reuse the cache and
do **not** resend your password. A `429 Too Many Requests` means you should wait
before retrying — repeated auth failures can trigger a temporary block.

## 4. Fetch data and build the DuckDB

`batch_ingest` fetches raw data from the Garmin API **and** inserts it into the
DuckDB for every date in a range. The DuckDB file (`garmin_performance.duckdb`)
is created automatically under `GARMIN_DATA_DIR/database/` on first write.

```bash
# Fetch + ingest a date range (creates/updates the DuckDB)
uv run python -m garmin_mcp.scripts.batch_ingest \
  --start-date 2025-10-01 --end-date 2025-10-31

# Preview the dates without fetching
uv run python -m garmin_mcp.scripts.batch_ingest \
  --start-date 2025-10-01 --end-date 2025-10-31 --dry-run
```

Alternative two-step flow (fetch raw files first, build the DB later with no API
calls):

```bash
uv run python -m garmin_mcp.scripts.bulk_fetch_raw_data --start-date 2025-10-01
uv run python -m garmin_mcp.scripts.regenerate_duckdb --start-date 2025-10-01 --end-date 2025-10-31
```

> Surgical updates: `regenerate_duckdb --tables splits --activity-ids <id> --force`
> rebuilds selected tables for selected activities from already-fetched raw data
> (no API calls). See `docs/spec/duckdb_schema_mapping.md` for the table list.

## 5. Run your first analysis

Inside Claude Code, analyze a single activity by date. This ingests (if needed),
runs the section-analysis agents in parallel, and stores 5 section results in
DuckDB:

```
/analyze-activity 2025-10-15
```

(With no argument it defaults to today.) For multi-activity statistical analysis
(10+ activities, trends, predictions), see `docs/data-analysis-guide.md`.

## 6. View results in the web app

The web app renders the analysis stored in DuckDB.

```bash
# Build the frontend once, then start the server (http://127.0.0.1:8765)
npm --prefix packages/garmin-web/frontend run build
uv run garmin-web
```

For the dev server (auto-reload + Vite) and the full API reference, see
[`docs/garmin-web.md`](garmin-web.md).

## Troubleshooting

| Symptom | Likely cause / fix |
|---------|--------------------|
| `Set GARMIN_EMAIL and GARMIN_PASSWORD…` error | Credentials missing from the environment — fill them into `.env` |
| `429 Too Many Requests` | Garmin rate limit; wait and retry, avoid rapid repeated logins |
| Fetch succeeds but analysis finds no data | DuckDB not built yet — run `batch_ingest` (step 4) for the activity's date |
| Web app shows "API only" warning | `frontend/dist` not built — run `npm --prefix packages/garmin-web/frontend run build` |
| Empty web pages | No analyses stored yet — run `/analyze-activity` (step 5) first |

## Next steps

- **Single-activity analysis** workflow → README "Usage" + `/analyze-activity`
- **Bulk/statistical analysis** → `docs/data-analysis-guide.md`
- **Schema reference** → `docs/spec/duckdb_schema_mapping.md`
- **Web app** → `docs/garmin-web.md`
- **Development** → `CLAUDE.md` + `.claude/rules/`
