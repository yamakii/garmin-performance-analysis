# Scheduled Auto-Sync

The scheduled sync entrypoint runs a catch-up ingest across every domain
(running / weight / strength / wellness) and records the run in the `sync_runs`
table. It replaces the previously manual `catch-up` / `backfill` invocations
with a single command that is safe to trigger unattended from cron or a systemd
timer (issue #712, parent #701).

## What it does

`garmin_mcp.scripts.scheduled_sync:run_sync` delegates to `catch_up_ingest`, which
resolves an independent `[start, end]` window per domain from each domain's
latest stored date (see `ingest/catch_up.py`). It then writes one row to
`sync_runs`:

| Column | Meaning |
|--------|---------|
| `run_id` | Surrogate key (sequence `seq_sync_runs_id`) |
| `started_at` / `finished_at` | Run wall-clock bounds |
| `domains` | CSV of requested domains |
| `results` | `json.dumps` of the `catch_up_ingest` payload (per-domain result or `{"error": ...}`, plus resolved windows) |
| `status` | `success` (all OK) / `partial` (≥1 domain error) / `error` (run itself raised) |

## Exit code

`main()` returns `0` on `success` and `1` otherwise (`partial` or `error`), so
cron/systemd can alert on failure.

## Usage

```bash
# All domains (default)
uv run --directory packages/garmin-mcp-server \
  python -m garmin_mcp.scripts.scheduled_sync

# Restrict to specific domains
uv run --directory packages/garmin-mcp-server \
  python -m garmin_mcp.scripts.scheduled_sync --domains wellness,running

# Explicit database path
uv run --directory packages/garmin-mcp-server \
  python -m garmin_mcp.scripts.scheduled_sync --db-path /path/to/garmin_performance.duckdb
```

## cron example

Run every day at 05:30 local time, logging output for later inspection:

```cron
30 5 * * * cd /home/you/garmin-performance-analysis && \
  /usr/bin/env uv run --directory packages/garmin-mcp-server \
  python -m garmin_mcp.scripts.scheduled_sync \
  >> /home/you/garmin-performance-analysis/result/sync.log 2>&1
```

> Ensure the environment provides Garmin credentials the same way the manual
> ingest scripts do (e.g. via `.env` / `direnv`), otherwise the run records a
> `partial`/`error` status.

## systemd timer example

`~/.config/systemd/user/garmin-sync.service`:

```ini
[Unit]
Description=Garmin scheduled auto-sync

[Service]
Type=oneshot
WorkingDirectory=%h/garmin-performance-analysis
ExecStart=/usr/bin/env uv run --directory packages/garmin-mcp-server python -m garmin_mcp.scripts.scheduled_sync
```

`~/.config/systemd/user/garmin-sync.timer`:

```ini
[Unit]
Description=Run Garmin scheduled auto-sync daily

[Timer]
OnCalendar=*-*-* 05:30:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable with:

```bash
systemctl --user enable --now garmin-sync.timer
```

## Inspecting run history

```sql
SELECT run_id, started_at, status, domains
FROM sync_runs
ORDER BY run_id DESC
LIMIT 10;
```
