# garmin-web

Web app for browsing Garmin running analysis results stored in DuckDB.

- **Backend**: FastAPI (`packages/garmin-web/src/garmin_web/`)
- **Frontend**: Vite + React + TypeScript (`packages/garmin-web/frontend/`)

## Running the app

### Production-style (single process)

Build the frontend once, then start the server. FastAPI serves the built
SPA from `frontend/dist` with an `index.html` fallback for client-side
routes (deep links like `/activities/123` work).

```bash
# 1. Build the frontend
npm --prefix packages/garmin-web/frontend run build

# 2. Start the server (default: http://127.0.0.1:8765)
uv run garmin-web
uv run garmin-web --host 0.0.0.0 --port 8888   # custom bind
```

If `frontend/dist` does not exist, the server logs a warning and serves
the API only.

### Development (two processes)

Run uvicorn with auto-reload and the Vite dev server side by side.
Vite proxies `/api` to port 8765 (see `frontend/vite.config.ts`).

```bash
# Terminal 1: backend (port 8765)
uv run --directory packages/garmin-web uvicorn garmin_web.app:create_app --factory --reload --port 8765

# Terminal 2: frontend dev server (port 5173)
npm --prefix packages/garmin-web/frontend run dev
```

Open http://localhost:5173 during development.

## API

All endpoints are read-only `GET` under `/api`.

| Endpoint | Description |
|----------|-------------|
| `/api/activities?from=YYYY-MM-DD&to=YYYY-MM-DD` | Activity list, date descending. `from`/`to` are optional inclusive bounds |
| `/api/activities/{id}` | Aggregated detail (splits, form efficiency, HR zones, performance trends, form evaluation). 404 if unknown |
| `/api/activities/{id}/time-series?metrics=heart_rate,speed&max_points=500` | Downsampled time series. `metrics` is a required comma-separated list; unknown metrics → 422 |
| `/api/activities/{id}/track` | GPS track points. Indoor runs return an empty `points` array |
| `/api/activities/{id}/sections` | Section analyses (split / phase / efficiency / environment / summary) |
| `/api/trends/volume?from=...&to=...` | Weekly distance / duration / run-count aggregates |
| `/api/trends/physiology?from=...&to=...` | VO2max and lactate threshold history |
| `/api/trends/form?from=...&to=...` | Form evaluation score history |
| `/api/trends/efficiency?from=...&to=...` | Pace/HR efficiency and HR zone distribution history |

## Architecture

```
Browser (React SPA)
  └── /api/*  → FastAPI routers (api/)
                  └── queries/  → SQL query functions
                        └── garmin_mcp.database.connection.get_connection()
                              └── DuckDB (read-only)
  └── /*      → SPA fallback (frontend/dist/index.html)
```

- **Read-only DB access**: reuses `get_connection()` from
  `garmin-mcp-server` (workspace dependency). The DB path resolves from
  `GARMIN_DATA_DIR` unless `create_app(db_path=...)` is given.
- **Connection per request**: each request opens and closes its own
  connection via a context manager. No connection pooling or shared
  state, which keeps the app safe alongside the single-writer ingest
  process.
- **App factory**: `create_app(db_path=None, static_dir=None)`.
  `static_dir` overrides the default package-relative `frontend/dist`
  (used by tests).
- **Route precedence**: API routers are registered before the SPA
  catch-all, so `/api/*` is never shadowed; unknown `/api/*` paths
  return 404 JSON, not HTML.

## Tests

```bash
uv run --directory packages/garmin-web pytest -m unit -v
uv run --directory packages/garmin-web pytest -m integration -v
npm --prefix packages/garmin-web/frontend run test
```

CI runs both backend (pytest + ruff) and frontend (tsc + vitest + build)
jobs when `packages/garmin-web/**` changes (`.github/workflows/ci.yml`).
