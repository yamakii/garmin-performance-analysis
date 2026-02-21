# Prohibited Practices

## Data Access

- Direct DuckDB queries: `conn = duckdb.connect(...)`
- Direct file reads: `Read("/path/to/database/garmin_performance.duckdb")`
- Querying non-existent columns (check schema if unsure)

## Development

- Edit code without Serena MCP: `Edit("packages/garmin-mcp-server/src/garmin_mcp/ingest/worker.py", ...)`
- Implement on main branch (use worktree)
- Remove worktree without checking status: `git worktree remove --force`
- Force push to main/master
- 複数の無関係な変更を1コミットに混在させる（1 commit = 1 concern）

## Database

- Delete database without user approval: `rm *.duckdb`, `--delete-db`
- Propose `--delete-db` as first solution for errors

## Configuration

- Put rules in CLAUDE.md directly: use `.claude/rules/` instead (auto-loaded)
- Create rule files outside `.claude/rules/`: all rules must be in `.claude/rules/`

## Testing

- Tests depending on real production data: `conn.execute("SELECT * FROM activities")`
