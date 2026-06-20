# Contributing

Thanks for your interest. This is a personal-use Garmin running-analysis project,
but contributions and bug reports are welcome.

## Development setup

See the [Getting Started guide](docs/getting-started.md) for full setup. In short:

```bash
uv sync --extra dev          # install (with dev tools)
cp .env.example .env         # configure data dirs + Garmin credentials
direnv allow                 # optional: auto-load env
```

This is a `uv` workspace with two packages:

- `packages/garmin-mcp-server/` — Python MCP server (data + analysis tools)
- `packages/garmin-web/` — FastAPI backend + Vite/React frontend

## Workflow

All changes go through **Issue → branch → Pull Request** (the `main` branch is
protected; direct pushes are rejected).

1. **Open or pick an Issue** describing the change.
2. **Branch** from `main` using a descriptive name (e.g. `fix/...`, `feat/...`,
   `docs/...`, `chore/...`).
3. **Implement** with a single concern per PR — if your description needs "and",
   split it.
4. **Open a PR** with a Conventional Commits title and `Closes #<issue>` in the body.

### Commits & PRs

- **Conventional Commits**: `type(scope): summary` (`feat`, `fix`, `docs`,
  `chore`, `refactor`, `test`, …).
- One PR = one concern. Keep unrelated cleanup in its own PR.
- PRs merge via merge commit; CI (`ci-guard`) must be green.

## Testing & quality

Run the canonical CI gate locally before pushing:

```bash
scripts/ci-check.sh
```

This runs the same checks as CI (whole-package `black --check`, `ruff`, `mypy`,
and `pytest`) for both packages. Notes:

- Every test needs a pytest marker (`unit` / `integration` / `performance` /
  `garmin_api`). See [`docs/testing_guidelines.md`](docs/testing_guidelines.md).
- `pre-commit` runs formatting/lint/type hooks only (no tests). Install with
  `pre-commit install`.
- No test may depend on production data.

## Conventions

- **DuckDB access** goes through `get_connection()` / `get_write_connection()` —
  never raw `duckdb.connect()`.
- **Paths** resolve from env vars (`get_db_path()`, `GARMIN_DATA_DIR`) — never
  hardcode absolute paths.
- **Data safety**: `data/` and `result/` are git-untracked and unrecoverable if
  deleted. Never delete them without explicit confirmation.

The detailed engineering rules (architecture, validation tiers, schema) live in
`CLAUDE.md` and `.claude/rules/` — these are written for the project's AI coding
agent but are an accurate reference for human contributors too.

## Reporting bugs

Open a GitHub Issue with steps to reproduce, expected vs actual behavior, and
relevant logs (redact any personal data). For security issues, see
[SECURITY.md](SECURITY.md).
