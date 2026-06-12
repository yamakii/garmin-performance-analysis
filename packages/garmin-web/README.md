# garmin-web

Web app for browsing Garmin running analysis results.

- **Backend**: FastAPI + DuckDB (read-only, reuses `garmin_mcp.database.connection`)
- **Frontend**: Vite + React + TypeScript (`frontend/`)

## Development

```bash
# Backend (port 8765)
uv run --directory packages/garmin-web uvicorn garmin_web.app:create_app --factory --port 8765

# Frontend dev server (port 5173, proxies /api to 8765)
cd packages/garmin-web/frontend
npm install
npm run dev
```

## Tests

```bash
uv run --directory packages/garmin-web pytest -m unit -v
uv run --directory packages/garmin-web pytest -m integration -v
cd packages/garmin-web/frontend && npx vitest run
```
