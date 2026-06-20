#!/bin/bash
# CI parity check — reproduces the GitHub Actions `lint-and-test` job
# (+ web-backend / web-frontend when packages/garmin-web/ changed) locally,
# whole-package, mirroring .github/workflows/ci.yml exactly.
#
# Use this before completing Phase 2b and before any `--no-verify` commit.
#   scripts/ci-check.sh  → exit 0 (all pass) / exit 1 (something failed)
#
# `-e` is intentionally NOT set: we want to run every step and aggregate
# failures so a single run surfaces all problems.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER="$ROOT/packages/garmin-mcp-server"
WEB="$ROOT/packages/garmin-web"
FRONTEND="$WEB/frontend"

FAILED=0

run() {
  echo "▶ $*"
  if ! "$@"; then
    echo "  ↳ FAILED: $*" >&2
    FAILED=1
  fi
}

# --- lint-and-test (garmin-mcp-server, whole-package) ---
run uv run --directory "$SERVER" ruff check .
run uv run --directory "$SERVER" black --check .
run uv run --directory "$SERVER" mypy .
run uv run --directory "$SERVER" pytest -m unit --tb=short -n 4 --maxfail=5 \
  --cov=garmin_mcp --cov-report=term-missing --cov-fail-under=60

# --- web checks: only when packages/garmin-web/ changed vs main ---
if git -C "$ROOT" diff --name-only main...HEAD | grep -q '^packages/garmin-web/'; then
  echo "▶ web changes detected — running web-backend / web-frontend checks"

  # web-backend (packages/garmin-web)
  run uv run --directory "$WEB" ruff check src/ tests/
  run uv run --directory "$WEB" pytest -m "unit or integration" --tb=short

  # web-frontend (packages/garmin-web/frontend)
  run npm --prefix "$FRONTEND" run lint
  echo "▶ ( cd $FRONTEND && npx tsc --noEmit )"
  if ! ( cd "$FRONTEND" && npx tsc --noEmit ); then
    echo "  ↳ FAILED: tsc --noEmit" >&2
    FAILED=1
  fi
  echo "▶ ( cd $FRONTEND && npx vitest run )"
  if ! ( cd "$FRONTEND" && npx vitest run ); then
    echo "  ↳ FAILED: vitest run" >&2
    FAILED=1
  fi
  echo "▶ ( cd $FRONTEND && npm run build )"
  if ! ( cd "$FRONTEND" && npm run build ); then
    echo "  ↳ FAILED: npm run build" >&2
    FAILED=1
  fi
else
  echo "▶ no packages/garmin-web/ changes vs main — skipping web checks"
fi

if [ "$FAILED" -ne 0 ]; then
  echo "❌ ci-check FAILED" >&2
  exit 1
fi

echo "✅ ci-check passed"
exit 0
