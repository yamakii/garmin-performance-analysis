# Prohibited Practices

## Data Access

- Direct DuckDB queries: `conn = duckdb.connect(...)`
- Direct file reads: `Read("/path/to/database/garmin_performance.duckdb")`
- Using deprecated tools: `get_splits_all()`, old `get_section_analysis()`
- Querying non-existent columns (check schema if unsure)

## Development

- Edit code without Serena MCP: `Edit("packages/garmin-mcp-server/src/garmin_mcp/ingest/worker.py", ...)`
- Implement on main branch (use worktree)
- Remove worktree without checking status: `git worktree remove --force`
- Force push to main/master

## Database

- Delete database without user approval: `rm *.duckdb`, `--delete-db`
- Propose `--delete-db` as first solution for errors

## Testing

- Tests depending on real production data: `conn.execute("SELECT * FROM activities")`
