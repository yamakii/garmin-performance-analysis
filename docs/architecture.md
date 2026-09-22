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
   ├──▶ Analysis agent (run-note-analyst) → section_analyses
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

## The analysis agent & prefetch context

A single activity is analyzed by one agent via the Task tool:

- **`run-note-analyst`** — emits the `run_note` coach review, the only
  LLM-written section.

The section is written as `run_note.json`, validated against its schema and the
grounding gate, then merged into the `section_analyses` table (append-only, one
row per analysis run).

**Prefetch-context pattern:** the orchestrator calls `prefetch_run_report` and
`prefetch_activity_context` once and passes the REPORT and the bundled CONTEXT
inline, so the agent does not issue many small MCP round-trips. The agent trusts
the prefetched data and only makes additional MCP calls when something is
missing.

**Why this shape:**

- **Determinism first** — everything a number can decide (range verdicts,
  prescription verdicts, scenes, the next target) is computed in the pipeline,
  so every past run gets the current page without being re-analysed by an LLM.
- **Token economy** — prefetching one context bundle beats dozens of
  per-metric tool calls, and the agent narrates pre-computed numbers rather than
  recomputing them (HR zones come from the DB, not the LLM).
- **Authority boundaries** — the agent adds Japanese prose, not new numbers,
  and the merge-time grounding gate rejects any claim whose evidence key does
  not resolve against the report. HR zones always come from Garmin-native
  zones, never a `220−age` formula.

### What the CONTEXT carries

The run itself — plan vs actual, signals, scenes, conditions — is the report's.
`prefetch_activity_context` carries only what the report cannot say: why the day
was prescribed and how it was answered (`prescription`, `prescription_for_run`,
`prescription_verdict`), where the day sits in the week (`week_position`), how
the athlete woke up (`morning_wellness`), the previous run of the same kind
(`previous_same_type`, `vs_previous`), `similar_workouts`, the `long_run_gate`
verdict for runs of 10 km and more, and the shoe (`gear`). Every key has a
reader — `buildRunNoteContext` in `.claude/workflows/analyze-activity.js` — and
a test keeps the two in step (#1287). Weather, HR zones and form are read
through the report or their own tools.

As a side effect the call trains the form baseline of the activity's month (and
the month before) when it is missing; nothing else does, and ingest grades form
against that baseline (#266, #1088).

## Run report and the run note

One activity is read as **one deterministic report** — `get_run_report(activity_id)`
(`database/readers/run_report.py`), also served as web
`GET /api/activities/{id}/report`. The page, the run-note agent, `/run-debrief`
and `/daily-checkin` all read that same dict, so they cannot disagree about what
happened, and every past run gets the current page without being re-analysed by
an LLM (Epic #1247).

**Structured by the reader's questions**, not by the analyst's data families:
*did I do the plan* (`plan`), *was anything unusual* (`signals`, `moments`,
`recurrence`), *what next* (`next_run_target`). Everything else — `phases`,
`zones`, `conditions`, `vs_previous` — is the record.

**Only two judgements exist on a single run**, and neither is a grade:

1. **Plan vs actual** — `compute_prescription_verdict` scores the day's
   prescription axis by axis (`target` / `actual` / `on_plan`, plus the HR
   ceiling's `seconds_over` / `pct_over`) into ✅ / 🟡 / 🔴. `plan` is `null`
   when the day carried no prescription. The ceiling is judged on steady
   running only (`analysis/hr_windows.py`): stops, auto-pause resumes, bursts
   and stride / recovery laps are masked together with the HR recovery after
   each, read off the HR trace; `judged_share` reports how much of the run was
   left, and form signals are not judged below half.
2. **Today vs the athlete's own normal range** — per metric, not against a
   population or a fixed band.

### Run-level normal range

`analysis/normal_range.py` owns the run-level thresholds, and
`analysis/run_signals.py` applies them to seven oriented signals (`gct`, `vo`,
`vr`, `cadence`, `power`, `hr_vs_expected`, `hr_drift`; `z > 0` is always the
unfavourable side, so `adverse` is simply "outside on the bad side"):

- **Window** — the athlete's own prior runs over the trailing `WINDOW_DAYS`
  (60).
- **Robust centre and spread** — median and `1.4826 × MAD`, not mean ± SD. A
  mean/SD band over mixed families put the drift band at −13 %…+22 %, wide
  enough that nothing was ever outside it; the same runs judged robustly within
  one family give −1 %…+10 %.
- **Status** — `outside` at `|z| ≥ 2.0`, `edge` at `≥ 1.5` (text only, no
  colour), otherwise `within`. A `streak` counts consecutive judged runs at
  `|z| ≥ 1.0` — repetition of a mild lean, which is why the streak threshold is
  deliberately lower than the edge.
- **Not judged** (`insufficient` + a `reason`) — fewer than 3 valid running
  splits, fewer than 10 comparable prior runs, a missing value, a pace outside
  the form model's trained speed range, or — for HR drift — a run hot enough
  that the drift is thermal rather than durability. Silence beats a confident
  number built on three runs.
- **Same-family baselines for the HR signals** — the four form metrics are
  already pace-corrected, so every prior run is comparable; `hr_vs_expected`
  (expected HR from the `HeatAdjustmentModel`) and `hr_drift` are not comparable
  across sessions, so their baseline is restricted to the same intensity family.

`normal_low` / `normal_high` come back in the metric's display unit (ms, cm, %,
spm, bpm), so a page prints "260 ms, usual 252–262" without knowing how the band
was built. This replaces grading a run mean against a *split-level* sigma: over
63 runs that score was uncorrelated with HR or rest and clustered low on short
runs, because a run mean is naturally far less variable than one split.

### Scene candidates

`analysis/run_moments.py` detects the turning points deterministically (2–5 per
run) so the LLM selects and explains, but cannot invent one: `ceiling_touch`,
`self_correction`, `fade`, `walk_break`, `strong_finish`, `surge`, `climb`,
`start` (plus `steady` for an uneventful run), in that priority order — a
kilometre matching several rules gets the single highest-priority kind, and the
same order decides which scenes survive the cap. Fragments below the shared
`MIN_SPLIT_KM` are dropped before anything is measured, and the median every
rule is measured against is taken over running splits only, so walk breaks do
not raise the bar that would expose them. `detect_recurrence` then reports the
kinds that keep happening at the same kilometre across the previous same-family
runs.

### What earns prose

`run_note` is the one LLM-written section. A sentence stays only if deleting it
loses something a figure or table cannot give — **six roles**: *meaning* (what
the run was for and whether it served that), *causality* (a signal tied to its
likely cause in the order intensity → terrain → weather + start time → recovery
→ form, saying so when the cause is uncertain), *flow* (scene by scene, not
kilometre by kilometre), *weighting* (what matters and what to ignore today),
*next action* (one step, numbers transcribed from `next_run_target`, an HR
ceiling written as a guard), *recurrence and questions* (what keeps recurring;
at most one question about what the sensors cannot see).

Never written: numeric readouts already in the figures, restated deterministic
verdicts ("接地時間は理想範囲内です" — the range badge already says it), generic
textbook criteria, a within-range deviation dressed up as a strength or a
weakness, the same point in two places, a pass/fail judgement of the athlete, or
a scene or cause no evidence key supports. Every claim carries the key of the
datum behind it (`signals.<metric>`, `moments.<id>`, `plan.<axis>`, …) and
merge-time guards in `validation/validators.py` reject unknown keys, a growth
point resting on a within-range signal or an on-plan axis, and a timeline item
pointing at a scene that does not exist.

The canonical text of all of the above is the contract itself —
`get_analysis_contract("run_note")` (`validation/contracts.py`), which the agent
reads at run time. This section summarises it; the contract is what changes
behaviour.

## Related references

- Development workflow, validation tiers, testing → `CLAUDE.md` + `.claude/rules/`
- Web app internals → [`docs/garmin-web.md`](garmin-web.md)
- Column-level schema → [`docs/spec/duckdb_schema_mapping.md`](spec/duckdb_schema_mapping.md)
- Tool catalog → [`docs/mcp-tools-reference.md`](mcp-tools-reference.md)
