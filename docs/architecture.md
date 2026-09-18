# Architecture

This document explains the **why** behind the system's design. For the **what**
(commands, schema, workflows) see the [README](../README.md), `CLAUDE.md`,
[`docs/garmin-web.md`](garmin-web.md), and
[`docs/spec/duckdb_schema_mapping.md`](spec/duckdb_schema_mapping.md).

## Pipeline & module map

```
Garmin Connect API
   │  (ApiClient — authenticated singleton)
   ▼
Raw JSON  (data/raw/activity/{id}/*.json, data/raw/weight/*.json)
   │  (RawDataFetcher — cache-first)
   ▼
DuckDB  (garmin_performance.duckdb, 19 domain tables)
   │  (DuckDBSaver + GarminDBWriter — 13 table inserters, transaction-batched)
   ▼
MCP Tools  (46 tools, token-optimized; ToolDef registry)
   │
   ├──▶ Analysis agents (unified + split section analysts) → section_analyses
   └──▶ Web app (FastAPI + React, read-only viewer)
```

Key modules (see `CLAUDE.md` for the full table):

- **`ingest/`** — `ApiClient` (auth singleton), `RawDataFetcher` (cache-first
  raw collection), `DuckDBSaver` (transaction-batched insertion), orchestrated by
  `GarminIngestWorker`.
- **`database/`** — `GarminDBWriter` (write, 13 inserters), `GarminDBReader`
  (read, query builders), `migrations/` (numbered, registry-driven).
- **`tools/`** — the `ToolDef` registry (single source for all 46 MCP tools).
- **`packages/garmin-web/`** — FastAPI backend + Vite/React SPA over the DuckDB.

## DuckDB-first

All analysis reads from a normalized DuckDB, never from raw JSON or the live API.

**Why:** raw Garmin JSON is large, nested, and inconsistent across activity
types. Querying it directly per analysis would be slow, repetitive, and
token-expensive for an LLM. A normalized columnar store (DuckDB) makes
multi-activity aggregation, trends, and joins cheap, gives every consumer (MCP
tools, web app, scripts) one consistent shape, and decouples analysis latency
from Garmin API availability and rate limits. Raw JSON is kept only as an
immutable cache so the DB can be regenerated deterministically.

## Filter at ingest

Data cleaning and derivation happen **once, at ingest time** — not in query-side
`WHERE` clauses.

**Why:** masking dirty data at read time means every consumer must re-apply the
same filters and can silently disagree. Doing the transformation once (unit
conversions, phase classification, environmental calculations, HR-zone mapping)
yields a single clean source of truth. Corollary: derived/evaluation columns are
materialized in the schema (see `splits` "CALCULATED" fields), so the same
values back the MCP tools and the web app without recomputation. When data is
wrong, fix the inserter and regenerate — don't add a query-side guard.

## Concurrency: single writer

DuckDB is embedded and allows one writer at a time.

**Why & how:** ingest is the only writer and runs as a single process;
everything else (web app, analysis) opens **read-only** connections. All access
goes through `get_connection()` / `get_write_connection()` (never raw
`duckdb.connect()`), which centralizes path resolution and read-only handling.
The web app opens one connection per request and closes it, so it never holds a
write lock alongside ingest. On the rare `database is locked` error, writers
retry (3×, 2s backoff) rather than failing the run. This keeps the model simple
(no pooling, no shared mutable state) while staying safe under the
ingest-while-browsing case.

## MCP ToolDef registry (single source)

Every tool is declared once as a `ToolDef` in `tools/<domain>.py`; `ALL_DEFS`
aggregates them. From that single declaration the system derives:

- the **MCP `inputSchema`** (normalized from a Pydantic `params` model, or an
  explicit override),
- **dispatch** (the worker looks up `ALL_DEFS_BY_NAME` — O(1) — and calls the
  handler via `dispatch()`),
- the **`garmin-db` CLI** (Typer subcommands from `cli_group` / `cli_name`), and
- the **generated tool reference** ([`docs/mcp-tools-reference.md`](mcp-tools-reference.md)).

**Why:** previously schema, dispatch (`elif` chains), and CLI lived in separate
places and drifted. One declaration eliminates that class of bug. A byte-parity
golden snapshot and an output-shape snapshot guard the MCP surface in CI, and a
sync test keeps the generated reference current — so adding a tool is just
"add a `ToolDef`", and forgetting to regenerate fails CI. The two server tools
(`get_server_info`, `reload_server`) are intentionally outside the registry
because they act on the server process itself, not on data.

## MCP server: stable shim + swappable worker

The MCP server is split into a tiny, *unchanging* **shim** and a *swappable*
**worker** (Epic #478):

```
Claude Code (MCP client)
   │  stdio (one long-lived MCP session)
   ▼
server.py — SHIM (owns the MCP session; never imports volatile domain code)
   │  newline-JSON IPC over a WorkerClient
   ▼
garmin_mcp.worker — WORKER (fresh process; imports the latest on-disk
   tool registry + DB readers and runs dispatch())
```

- **`server.py` (shim)** owns only the MCP protocol session. `list_tools`
  returns the worker's schema plus the two server tools; every other
  `call_tool` is delegated to the worker over the IPC.
- **`garmin_mcp.worker`** is a fresh process that imports the volatile
  `tools/` registry and `database` readers and executes
  `dispatch(defs_by_name, reader, name, arguments)`.
- **`reload_server`** restarts *only the worker* (so it re-imports the latest
  on-disk code) and emits a `notifications/tools/list_changed`. The shim
  process stays alive, so the MCP session — and any subagent's tool access —
  survives the reload.

**Why:** the old `reload_server` killed its own process with `os._exit(0)` and
depended on the launcher (`scripts/start-mcp-server.sh`, with an override-dir
file) to respawn the client. That respawn was an unsupported client behaviour
and the root cause of instability — lost subagent tools (#243), flush races,
non-deterministic startup, and stale override files. Keeping the session in an
immutable shim while replacing only the worker removes that whole failure class.
The `reload_server` `server_dir` argument is gone too: the worker always
re-imports the latest on-disk code rather than being pointed at a directory.

**Reflection model (verified):**

- **Signature-compatible changes** (reader logic / bug fixes — the large
  majority of edits) reflect into the *same* session with **zero touch**: the
  next `reload_server` (or next tool call) re-imports the new code.
- **Schema-shape changes** (added/removed tools or changed args = changed
  `inputSchema`) are cached by the client, so a `list_changed` notification
  alone does not refresh them — **only this kind needs one `/mcp` reconnect**.
- Corollary: tools whose shape tends to churn can accept a generic
  `options: dict` so their `inputSchema` stays fixed; such edits then count as
  logic changes and keep the zero-touch path.

## Section-analysis agents & prefetch context

A single activity is analyzed by two agents run in parallel via the Task tool:

- **`unified-section-analyst`** — emits `efficiency`, `phase`, `environment`,
  `summary` sections.
- **`split-section-analyst`** — emits the per-kilometer `split` section.

Each section is written as a separate `{section}.json`, validated, then merged
into the `section_analyses` table (one row per `(activity_id, section_type)`).

**Prefetch-context pattern:** the orchestrator calls
`prefetch_activity_context` once and passes the bundled CONTEXT to the unified
agent, so the agent does not issue many small MCP round-trips. The agent trusts
the prefetched data and only makes additional MCP calls when something is
missing.

**Why this shape:**

- **Parallelism + isolation** — sections are independent, so running them
  concurrently cuts wall-clock; writing separate JSON files means a single
  section failure degrades gracefully (4/5 success still stores 4 sections)
  instead of failing the whole analysis.
- **Token economy** — prefetching one context bundle beats dozens of
  per-metric tool calls, and the agents narrate pre-computed numbers rather than
  recomputing them (form scores, HR zones come from the DB, not the LLM).
- **Authority boundaries** — derived values (form `★` ratings, HR-zone
  distribution) are computed in the pipeline and treated as the source of truth;
  the agents add Japanese narrative, not new numbers. HR zones always come from
  Garmin-native zones, never a `220−age` formula.

### Continuous scores in the CONTEXT

Two ratings the agents used to derive from a *band table* are pre-computed as
continuous numbers, because an LLM applying a step function made near-identical
runs jump a whole star at a band edge (#1236). Both are computed on read in
`prefetch_activity_context`, so the whole history is covered without a
re-ingest, and the agents anchor on them (adjusting by at most ±0.5) instead of
re-deriving:

- `zone_distribution_score` — the continuous form of
  `zone_distribution_rating`. The run's intensity category (easy / moderate /
  tempo / threshold / vo2max) selects the HR-zone band it is judged on;
  `zone_band_pct` is the share of the run spent in that band, and the score
  interpolates linearly over the *same* `ZONE_BAND_CUTS` the label uses —
  excellent cut → 5.0, good → 4.0, fair → 3.0, continuing on that slope down to
  a floor of 1.0. `null` for the "unknown" category, which has no intended band.
  It feeds the summary's `hr_management` axis and the phase section's
  `hr_control` axis.
- `form_scores.integrated_star_score` — the 100-point `integrated_score` on the
  star scale: `clamp(5.0 − (100 − score) / 20, 1.0, 5.0)`, i.e. 20 points per
  star, the same mapping `scorer.compute_star_rating` uses (#1233).

Both keys are additive and `null` when their source row is missing, so an agent
whose CONTEXT lacks them falls back to the categorical judgement.

## Related references

- Development workflow, validation tiers, testing → `CLAUDE.md` + `.claude/rules/`
- Web app internals → [`docs/garmin-web.md`](garmin-web.md)
- Column-level schema → [`docs/spec/duckdb_schema_mapping.md`](spec/duckdb_schema_mapping.md)
- Tool catalog → [`docs/mcp-tools-reference.md`](mcp-tools-reference.md)
