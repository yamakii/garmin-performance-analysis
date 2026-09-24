# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Overview

Garmin running performance analysis system with **DuckDB-first architecture** and **MCP-first tool usage**.

**System Pipeline:** Raw Data (API) → DuckDB → MCP Tools → Analysis

**Key Features:**
- DuckDB normalized storage (28 tables, 100+ activities)
- Token-optimized MCP tools (70-98.8% reduction), declared via a single-source `tools/` registry (see `docs/mcp-tools-reference.md` for the full set)
- 1 analysis agent (run-note-analyst) writing the coach review on top of the deterministic run report
- Japanese analysis stored in DuckDB, viewed via the Web app (code/docs in English)

**Two Use Cases:**
1. **Activity Analysis** - Analyze running data using MCP tools (→ See "For Activity Analysis")
2. **Tool Development** - Develop/improve the analysis system (→ See "For Tool Development")

---

## For Activity Analysis

**When:** Analyzing activities, finding trends, comparing workouts.

All MCP tools have docstrings describing their parameters. Use `mcp__garmin-db__*` tools directly.

### Common Analysis Workflows

**1. Single Activity Analysis**
```
1. Get activity ID: mcp__garmin-db__get_activity_by_date(date="2025-10-15")
2. Get the run report: mcp__garmin-db__get_run_report(activity_id)
   → plan vs actual, signals vs the athlete's own normal range, scenes, conditions
3. Then only what the report does not carry:
   - Splits: mcp__garmin-db__get_splits_comprehensive(activity_id, statistics_only=True)
   - Form inputs: mcp__garmin-db__get_form_evaluations(activity_id)
   - HR zones: mcp__garmin-db__get_hr_efficiency_analysis(activity_id)
   - Trends: mcp__garmin-db__get_performance_trends(activity_id)
```
> A single run is judged by the run report's two questions (plan vs actual, today vs the athlete's own normal range) — `signals[].status` of `within` / `edge` is not a finding, and form stars are legacy display values.

**2. Multi-Activity Trends**
```
1. Get IDs for date range using analyze_performance_trends
2. Compare: mcp__garmin-db__analyze_performance_trends(
     metric="pace",
     start_date="2025-10-01",
     end_date="2025-10-31",
     activity_ids=[...]
   )
```

**3. Similar Workout Comparison**
```
mcp__garmin-db__compare_similar_workouts(
  activity_id=12345,
  pace_tolerance=0.1,
  distance_tolerance=0.1
)
```

---

## For Data Analysis

**When:** Statistical analysis, multi-month trends, race prediction, adhoc queries involving 10+ activities.

Use the export-based 5-step workflow (Plan → Export → Code → Result → Interpret).
See `.claude/rules/analysis/analysis-standards.md` for workflow details and `docs/data-analysis-guide.md` for examples.

---

## Common Pitfalls

**Intent disambiguation:** See `.claude/rules/intent-disambiguation.md`

**Training plan rules:** See `.claude/rules/analysis/analysis-standards.md`

**Project conventions:** Rule files go in `.claude/rules/` (auto-loaded). CLAUDE.md is for overview and workflows only.

---

## For Tool Development

**When:** Modifying code, adding features, fixing bugs, running tests.

**Workflow:** Plan (tiered) → Issue → Worktree → Implement → Ship

Four things hold before any file is opened (the detailed rules below load once you touch
`packages/`, `.claude/`, `scripts/`, `docker/`, `.github/` or `docs/`):
- Every code change needs an Issue with Design + Test Plan, a plan sized by the Phase 0 tier in `implementation-workflow.md` (a `design-approved` Issue is the plan; plan-mode approval only for risky changes; a light plan otherwise), and a worktree + PR (never commit on `main`).
- GitHub is operated only through `mcp__github__*` tools; `gh` is denied.
- Code investigation starts with `mcp__serena__activate_project()`.
- Python always runs through uv — `uv run --directory <checkout> python <script>` — including throwaway
  scripts on transcripts or temp files; bare `python` / `python3` is blocked by `guard-bare-python.sh`.

Key rules (path-scoped, under `.claude/rules/dev/`):
- `workflow-orchestration.md` — plan-first, elegance check, autonomy boundaries, core principles
- `implementation-workflow.md` — the default single-session worktree → PR checklist
- `git.md` — git principles with their reasons, canonical commands, output budget for git reads
- `dev-reference.md` — testing, code quality, architecture (参照辞書)
- `worktree-validation-protocol.md` — validation levels, ship steps, auto-merge gate
- `github-mcp-only.md` — gh → MCP tool mapping, CI log access

### Worktree 検証

検証レベル（L1/L2/L3/skip）、Ship 手順、auto-merge ゲートの正本は
`.claude/rules/dev/worktree-validation-protocol.md`。承認済み Issue はそのセッションが worktree で実装して PR を作りマージする（`implementation-workflow.md` Phase 1）。`/implement <epic>` は `implementation-workflow.md` の起動条件（依存ティア 2 段以上、または依存の無い 4 件以上でファイル非共有）を満たすときに使う。

### Quick Commands
| Command | Purpose |
|---------|---------|
| `uv sync --extra dev` | Initial setup |
| `direnv allow` | Auto-load env |
| `uv run python -m garmin_mcp.scripts.regenerate_duckdb --tables X --activity-ids N --force` | Surgical DuckDB update |
| `uv run python -m garmin_mcp.scripts.bulk_fetch_raw_data --start-date YYYY-MM-DD` | Fetch raw data |
| `uv run python -m garmin_mcp.scripts.bulk_fetch_activity_details --activity-ids N` | Fetch activity details |
| `uv run python -m garmin_mcp.scripts.backfill_wellness [--start-date YYYY-MM-DD]` | Rate-limit-safe full-history daily_wellness backfill (monthly chunks, 429 backoff, auto data-floor stop, resume) |
| `uv run python -m garmin_mcp ingest catch-up --domains wellness --start-date YYYY-MM-DD` | Backfill daily wellness (RHR/HRV/sleep) over a date range |

---

## Architecture

**Pipeline:** API → Raw JSON → DuckDB → MCP Tools → Analysis (viewed via Web app)

> Module layout: `packages/garmin-mcp-server/src/garmin_mcp/` (ingest/, database/, tools/ registry, worker) and `packages/garmin-web/` (FastAPI + Vite SPA, see `docs/garmin-web.md`). Full column-level DuckDB schema: `docs/spec/duckdb_schema_mapping.md`. Design rationale: `docs/architecture.md`.

### Agent System

**1 Analysis Agent (called by the `analyze-activity` workflow):**
1. **run-note-analyst** (opus, medium effort): writes the `run_note` coach review — the only section an
   LLM writes. Every number, range verdict, prescription verdict and scene is already
   computed by `get_run_report`, so the agent adds only the prose on top of it: meaning,
   causality, how the run unfolded, weighting, the next step, recurrence and at most one
   question.
2. **proofreader** (haiku): checks the Japanese of `run_note.json` before the merge.

> The agent fetches the deterministic REPORT and the CONTEXT subset in one `get_run_note_inputs`
> call (no file reads) and writes `run_note.json`, which `merge_section_analyses` validates against
> the section schema and the grounding gate (every claim carries an evidence key that resolves
> against the report) before inserting it into `section_analyses`.

### Critical Data Sources

**Split Analysis:**
- `splits.json` (lapDTOs) - 1km lap data
- NOT `typed_splits.json` - Aggregated only

**Temperature:**
- `weather.json` - External weather station
- NOT `splits.json` temperature - Device temp (+5-8 C body heat)

**Elevation:**
- Source: `lapDTOs` → DuckDB
- Classification: flat/undulating/hilly/mountainous
