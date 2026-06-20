# Testing Guidelines

Quick reference for test markers and execution. The authoritative rules for
test budgets, fixtures, and parallel-safety live in
`.claude/rules/dev/dev-reference.md` §4 (auto-loaded).

## Monorepo layout

Tests live in two packages, each with its own `pyproject.toml` pytest config:

- `packages/garmin-mcp-server/tests/`
- `packages/garmin-web/tests/`

Run them via `uv run --directory <package> pytest ...`. The canonical CI
command set is `scripts/ci-check.sh` (server: `pytest -m unit`; web:
`pytest -m "unit or integration"`).

## Test Markers

Defined in each package's `pyproject.toml` (`[tool.pytest.ini_options]`):

| Marker | Meaning |
|--------|---------|
| `unit` | Fast, isolated — mocks only, no I/O, < 100ms |
| `integration` | Moderate speed — mock DuckDB / filesystem / Parquet |
| `performance` | Benchmarks; real data OK (skipped if unavailable) |
| `slow` | Slow tests, deselected by default |
| `garmin_api` | Requires Garmin API auth; rate-limited, manual only |

## Default Behavior

`addopts` deselects three markers by default, so a bare `pytest` skips
`garmin_api`, `slow`, and `performance`:

```toml
addopts = "-m 'not garmin_api and not slow and not performance' --strict-markers -n 4 ..."
```

```bash
# From a package dir — runs unit + integration only
uv run --directory packages/garmin-mcp-server pytest

# Unit only
uv run --directory packages/garmin-mcp-server pytest -m unit

# Integration only
uv run --directory packages/garmin-mcp-server pytest -m integration

# Garmin API tests (override the default deselect)
uv run --directory packages/garmin-mcp-server pytest -m garmin_api

# Everything, including deselected markers
uv run --directory packages/garmin-mcp-server pytest -m ""
```

## pre-commit vs CI

- **pre-commit runs no tests.** Its hooks are formatting/lint/type only:
  `black`, `ruff`, `mypy`, `no-direct-duckdb-connect`, `check-banned-patterns`
  (plus whitespace/EOF/yaml/json utility hooks). See `.pre-commit-config.yaml`.
- **Tests run in CI** (`ci-guard`) and locally via `scripts/ci-check.sh`.
  Run `scripts/ci-check.sh` before pushing to reproduce the CI gate
  (whole-package `black --check` / `mypy` / `pytest`), which per-file
  pre-commit does not cover.

## Best Practices

1. **Tag Garmin-API tests with `@pytest.mark.garmin_api`** so they are
   deselected by default and only run manually (avoids 429 rate limits).
2. **Integration tests use cached raw data** under `data/raw/` instead of live
   API calls. Assert the cache exists: `assert cache_file.exists()`.
3. **Combine markers** when a test is both:
   ```python
   @pytest.mark.integration
   @pytest.mark.garmin_api
   def test_api_integration():
       ...
   ```

## Garmin API Rate Limit

- Garmin API returns `429 Too Many Requests` under load; repeated auth failures
  can trigger a temporary block.
- Isolate such tests behind `@pytest.mark.garmin_api` and run them manually.
