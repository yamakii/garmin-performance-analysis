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
- **dispatch** (`server.py` looks up `ALL_DEFS_BY_NAME` — O(1) — and calls the
  handler),
- the **`garmin-db` CLI** (Typer subcommands from `cli_group` / `cli_name`), and
- the **generated tool reference** ([`docs/mcp-tools-reference.md`](mcp-tools-reference.md)).

**Why:** previously schema, dispatch (`elif` chains), and CLI lived in separate
places and drifted. One declaration eliminates that class of bug. A byte-parity
golden snapshot and an output-shape snapshot guard the MCP surface in CI, and a
sync test keeps the generated reference current — so adding a tool is just
"add a `ToolDef`", and forgetting to regenerate fails CI. The two server tools
(`get_server_info`, `reload_server`) are intentionally outside the registry
because they act on the server process itself, not on data.

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

## Related references

- Development workflow, validation tiers, testing → `CLAUDE.md` + `.claude/rules/`
- Web app internals → [`docs/garmin-web.md`](garmin-web.md)
- Column-level schema → [`docs/spec/duckdb_schema_mapping.md`](spec/duckdb_schema_mapping.md)
- Tool catalog → [`docs/mcp-tools-reference.md`](mcp-tools-reference.md)
