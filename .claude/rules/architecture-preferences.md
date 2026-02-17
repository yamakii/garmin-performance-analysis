# Architecture Preferences

## Filter at ingest, not query

- Apply data transforms in `GarminIngestWorker` / `DuckDBSaver` during ingestion
- Do NOT add WHERE clauses to filter out dirty data at query time
- If bad data exists in DuckDB, fix the ingest pipeline and re-ingest — don't mask it in readers

## Use Garmin native HR zones

- Always read HR zones from the `heart_rate_zones` table (Garmin-calculated)
- NEVER calculate HR zones from formulas (220-age, Karvonen, etc.)
- NEVER hardcode zone boundaries — they vary per user and are updated by Garmin

## DuckDB connection lifecycle

- Always use context managers: `get_connection(db_path)` for reads, `get_write_connection(db_path)` for writes
- Keep write transactions short — insert and commit promptly
- Verify schema before column access: `PRAGMA table_info(table_name)`
- NEVER use raw `duckdb.connect()` — it bypasses connection management and conflicts with `prohibited-practices.md`
