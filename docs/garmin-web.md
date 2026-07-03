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

> ⚠️ **Security:** The web app has **no authentication** and displays personal
> health data. The default `127.0.0.1` bind keeps it local-only. Binding to a
> non-loopback address (e.g. `--host 0.0.0.0`) exposes that data to everyone on
> the network. Only do so on a trusted LAN; the CLI logs a warning when the host
> is not `127.0.0.1`/`localhost`.

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

The table below is generated from the FastAPI routers; each description is the
first line of the route handler's docstring. Regenerate after route changes:
`uv run --directory packages/garmin-web python -m garmin_web.scripts.generate_api_doc`
(append `--check` to verify drift). Path parameters appear as `{name}`; query
parameters are documented in each handler's docstring.

<!-- BEGIN GENERATED: web-api-table -->
| Endpoint | Description |
|----------|-------------|
| `/api/activities` | Return activities sorted by date descending. |
| `/api/activities/{activity_id}` | Return aggregated detail for one activity, or 404 if unknown. |
| `/api/activities/{activity_id}/sections` | Return section analyses keyed by section_type. |
| `/api/activities/{activity_id}/sections/versions` | Return saved analysis batches for an activity (newest first). |
| `/api/activities/{activity_id}/time-series` | Return downsampled time series for the requested metrics. |
| `/api/activities/{activity_id}/track` | Return the GPS track for an activity. |
| `/api/body-composition-trend` | Body-composition trend over the trailing ``weeks`` weeks (#501). |
| `/api/durability-trend` | Return the long-run decoupling trend over a date window. |
| `/api/form-anomaly-flags` | "今週の注意点": form-anomaly flags across the trailing ``weeks`` runs (#636). |
| `/api/goal` | Return the athlete goal payload (profile + goals + retrospectives). |
| `/api/planned-workouts/today` | Return the planned workout for ``date`` (defaults to today). |
| `/api/race-readiness` | Return current VDOT, race-time predictions, and goal progress. |
| `/api/recovery-status` | Morning go/no-go recovery status for ``date`` (#500). |
| `/api/recovery-trend` | RHR / HRV recovery trend over the trailing ``weeks`` weeks (#499). |
| `/api/training-load` | Return the current ACWR snapshot plus the weekly load/ACWR trend. |
| `/api/trends/critical-speed` | Quarterly threshold-anchored Critical Speed fit (CS pace + R^2). |
| `/api/trends/efficiency` | HR efficiency trend with zone distribution. |
| `/api/trends/form` | Form evaluation score trend. |
| `/api/trends/heat-adjusted` | Climate-neutral HR-at-pace trend with per-run heat_cost. |
| `/api/trends/objective-fitness` | Objective (real-run derived) fitness curve vs Garmin VO2max + optimism gap. |
| `/api/trends/physiology` | VO2max and lactate threshold time series. |
| `/api/trends/volume` | Running volume aggregated per calendar week or calendar month. |
| `/api/weekly-reviews` | Return recent weekly reviews (newest first), one per week. |
| `/api/weekly-reviews/{week_start_date}` | Return a single weekly review by its week-start date. |
| `/api/weekly-reviews/{week_start_date}/versions` | Return all saved versions for a single week (newest first). |
| `/api/weight-economy-coupling` | Weight <-> easy-run economy (EF) coupling over the trailing ``weeks`` (#554). |
| `/api/wellness-baseline-deviation` | Personal-baseline deviation for HRV / readiness / RHR on ``date`` (#555). |
<!-- END GENERATED: web-api-table -->

> Weekly reviews are versioned: re-running `/weekly-review` for the same week appends a new row instead of overwriting (Epic #311). The list view de-duplicates to the latest version per week; the detail page fetches `/versions` to switch between past versions.

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
