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

## Pages

The SPA follows one information-architecture rule: **one page answers one
question** (Epic #890). The six nav entries are the six questions; detail and
fallback routes hang off a list page and stay out of the nav. Page components
live in `packages/garmin-web/frontend/src/pages/`.

| Route | Nav label | Question | Main content |
|-------|-----------|----------|--------------|
| `/` | ホーム | 今日どう動く? | Today's verdict hero → snapshot tiles (訓練負荷 / HRV / 安静時心拍 / フォーム注意点, each deep-linking into `/condition`) → this week's plan and next actions → race progress (compact) → recent runs |
| `/activities` | アクティビティ | 走った記録は? | Month-grouped run list with a date-range preset (直近4週 / 3ヶ月 / 1年 / 全期間) and a name search |
| `/condition` | コンディション | 今の体の状態は? | This week's cautions (form anomalies) as a full-width alert band, then today's condition, RHR/HRV recovery trend, personal-baseline deviation, training load (ACWR), body composition |
| `/performance` | パフォーマンス | 速くなっているか? | Coach narration and a page-level 週/月 toggle, then volume, physiology, efficiency, critical speed, objective fitness, climate-neutral HR, form score, durability, weight × economy |
| `/goal` | 目標 | 目標に届く? | Countdown hero, current phase, registered races, last season's retrospective |
| `/plan` | 計画 | この1ヶ月どう積むか? | Training-block bands over a month grid (rows = weeks, columns ordered from `week_start_day`, so the Sunday long run is last), each day showing its prescription vs the actual run, a per-week adherence chip linking to that week's review, and the month total |

Detail and fallback routes (no nav entry):

| Route | Reached from | Content |
|-------|--------------|---------|
| `/activities/:id` | activity list, recent runs | One run: section analyses, time series, GPS track, past-run version switch |
| `/weekly-reviews` | plan grid | Weekly review list, latest version per week |
| `/weekly-reviews/:weekStart` | plan grid, review list, home plan card | One week's review plus its version switch |
| `*` | mistyped or stale URLs | 404 page rendered inside the layout, so the nav stays one click away |

Cross-cutting behaviour worth knowing before editing a page:

- **`/trends` is retired.** The 16-card mega-page was split into `/condition`
  and `/performance` (#892); `/trends` now redirects to `/condition` and carries
  the hash and query string across, so old bookmarks and the home tiles'
  `#training-load` / `#recovery` / `#form-anomaly` deep links still land on
  their card.
- **Filters live in the URL.** `/activities` keeps its range preset and search
  text in `?range=` / `?q=`, so a filtered view survives reload, back
  navigation and bookmarking (#893).
- **Failures are per card, not per page.** Each card owns its query behind a
  `QueryBoundary`, which shows a skeleton while pending and a retryable in-card
  alert on error, so one broken endpoint no longer blanks a whole page.
- **No duplicated answers.** A number is owned by exactly one page: the home
  tiles link to the `/condition` card instead of restating it, and the race
  prediction sits in the `/goal` countdown tile rather than in a second card
  below it (#894, #895).
- **The review list is a detail route.** `/plan` replaced 週次レビュー in the nav
  (#983): the list was only an index over weeks, which the month grid now is, so
  the sixth question became 「この1ヶ月どう積むか?」. Both review routes stay
  reachable — the grid links each week row to `/weekly-reviews/:weekStart`, and
  the list links back to `/plan`.

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
| `/api/activities/{activity_id}/sections/versions` | Return saved analysis runs for an activity (newest first). |
| `/api/activities/{activity_id}/time-series` | Return downsampled time series for the requested metrics. |
| `/api/activities/{activity_id}/track` | Return the GPS track for an activity. |
| `/api/body-composition-trend` | Body-composition trend over the trailing ``weeks`` weeks (#501). |
| `/api/durability-trend` | Return the long-run decoupling trend over a date window. |
| `/api/form-anomaly-flags` | "今週の注意点": form-anomaly flags across the trailing ``weeks`` runs (#636). |
| `/api/goal` | Return the athlete goal payload (profile + goals + retrospectives). |
| `/api/plan/blocks` | Return the mesocycle block ledger in display order. |
| `/api/plan/month` | Return the monthly plan grid: weeks x days, prescriptions vs actuals. |
| `/api/race-readiness` | Return current VDOT, race-time predictions, and goal progress. |
| `/api/recovery-status` | Morning go/no-go recovery status for ``date`` (#500). |
| `/api/recovery-trend` | RHR / HRV recovery trend over the trailing ``weeks`` weeks (#499). |
| `/api/training-load` | Return the current ACWR snapshot plus the weekly load/ACWR trend. |
| `/api/trends/critical-speed` | Quarterly threshold-anchored Critical Speed fit (CS pace + R^2). |
| `/api/trends/efficiency` | HR efficiency trend with zone distribution. |
| `/api/trends/form` | Form evaluation score trend. |
| `/api/trends/heat-adjusted` | Climate-neutral HR-at-pace trend with per-run heat_cost. |
| `/api/trends/narration` | Latest-version narration for the most recent period of a granularity. |
| `/api/trends/narration/versions` | All saved narration versions for a single period, newest first. |
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

> Section analyses are versioned by **`run_id`** (#776): one analysis run shares a single `run_id` across its sections, so a full-activity analysis of 5 sections is one version, not five. `/sections/versions` returns one entry per run (newest first); the detail page pins `/sections?run_id=N` to view an older run (each section's latest version at or before that run).

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
