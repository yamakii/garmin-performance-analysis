# DuckDB Safety Rules

## CRITICAL: Database contains 100+ activities. NEVER delete without user approval.

## Error Protocol

1. Check integrity first: `conn = duckdb.connect(path, read_only=True)`
2. Try alternatives: Regenerate specific tables, use new Python process
3. NEVER propose `--delete-db` as first solution
4. NEVER delete without explicit user confirmation

**Remember:** INSERT/UPDATE errors != data corruption. Check data first, delete last.

## Safe Regeneration

```bash
# Surgical update (specific activity + tables)
uv run python -m garmin_mcp.scripts.regenerate_duckdb \
  --tables splits form_efficiency \
  --activity-ids 12345 \
  --force
```

Safety rules:
- Child tables require parent activities to exist (validated before deletion)
- Use `--activity-ids` for surgical updates, date range for batch
- Full database deletion (`--delete-db`) cannot be combined with `--tables`
