#!/bin/bash
# CI parity check — reproduces the GitHub Actions `lint-and-test` job
# (+ web-backend / web-frontend when packages/garmin-web/ changed) locally,
# whole-package, mirroring .github/workflows/ci.yml.
#
# Use this before completing Phase 2b and before any `--no-verify` commit.
#   scripts/ci-check.sh               → runs unit + integration (CI-identical)
#   scripts/ci-check.sh --unit-only   → skips integration (faster, for iteration)
#   scripts/ci-check.sh --detect-only → print the change-detection decision, exit 0
# exit 0 (all pass) / exit 1 (something failed) / exit 2 (bad usage)
#
# The default pytest marker is `unit or integration`, exactly mirroring the CI
# `lint-and-test` job (.github/workflows/ci.yml). This keeps ci-check.sh a
# single source of CI parity — no need to run integration separately.
#
# `-e` is intentionally NOT set: we want to run every step and aggregate
# failures so a single run surfaces all problems.
set -uo pipefail

# --- flag parsing ---
PYTEST_MARKER="unit or integration"
DETECT_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --unit-only)
      PYTEST_MARKER="unit"
      ;;
    --detect-only)
      DETECT_ONLY=1
      ;;
    *)
      echo "unknown argument: $arg" >&2
      echo "usage: ci-check.sh [--unit-only] [--detect-only]" >&2
      exit 2
      ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER="$ROOT/packages/garmin-mcp-server"
WEB="$ROOT/packages/garmin-web"
FRONTEND="$WEB/frontend"

FAILED=0

# Cap BLAS/OpenMP thread pools so pytest-xdist workers don't exhaust the
# sandbox pid quota (`can't start new thread`). Mirrors conftest + CI env.
# See issue #740.
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"

# --- per-package, per-worktree virtualenvs (#1003) ---
# The image sets UV_PROJECT_ENVIRONMENT=/home/claude/uv-venv — ONE venv shared by
# every package AND every worktree. `uv sync --directory $SERVER --extra dev`
# followed later by `uv sync --directory $WEB` therefore evicts the server's dev
# extras, and every `uv run --directory X` implicitly re-syncs (the endless
# "Uninstalled 1 package / Installed N packages" churn). Worse,
# worktree-validation-protocol.md explicitly allows PARALLEL L1/L2 validation
# agents: two ci-check runs against one shared venv uninstall dependencies out
# from under each other mid-check.
#
# Give each (package, worktree) pair its own environment so there is no shared
# mutable resource to race over. The base stays OUTSIDE the bind-mounted repo,
# preserving the reason docker/Dockerfile set UV_PROJECT_ENVIRONMENT in the first
# place (no .venv inside /workspace). The global default is left untouched for
# the MCP server and ad-hoc commands. `cksum` keeps the directory name short —
# a long venv path would overflow the 127-byte shebang limit in its bin/ scripts.
VENV_BASE="${CI_CHECK_VENV_BASE:-${HOME:-/home/claude}/uv-venvs}"
ROOT_ID="$(printf '%s' "$ROOT" | cksum | cut -d' ' -f1)"
SERVER_VENV="$VENV_BASE/$ROOT_ID-server"
WEB_VENV="$VENV_BASE/$ROOT_ID-web"

run() {
  echo "▶ $*"
  if ! "$@"; then
    echo "  ↳ FAILED: $*" >&2
    FAILED=1
  fi
}

# --- change detection (base ref + working tree) ---
# The old test was `git diff --name-only main...HEAD | grep -q '^packages/...'`,
# which had two failure modes, both observed in the #996 session:
#
#   1. It sees COMMITTED history only. An uncommitted web edit skipped the web
#      checks while the run still reported success — a false green on the very
#      gate that decides auto-merge.
#   2. It compares against the LOCAL `main`, which is routinely stale. Measured
#      in a worktree: `main...HEAD` reported 7 changed files where
#      `origin/main...HEAD` reported 0, so web checks ran for files the branch
#      never touched — and would silently stop running after a `git pull`.
#
# Prefer the remote tip, and union in the working tree (staged, unstaged and
# untracked) so the decision reflects what is actually on disk.
#
# The result is captured into a variable rather than piped into `grep -q`:
# under `set -o pipefail`, `grep -q` exits at the first match and can SIGPIPE the
# upstream `git`, making the pipeline status non-zero and flipping the decision.
BASE_REF=""
for ref in origin/main main; do
  if git -C "$ROOT" rev-parse --verify --quiet "$ref" >/dev/null 2>&1; then
    BASE_REF="$ref"
    break
  fi
done

collect_changed_files() {
  if [ -n "$BASE_REF" ]; then
    git -C "$ROOT" diff --name-only "$BASE_REF...HEAD"
  fi
  git -C "$ROOT" diff --name-only HEAD                 # staged + unstaged
  git -C "$ROOT" ls-files --others --exclude-standard  # untracked
}

CHANGED_FILES="$(collect_changed_files 2>/dev/null | sort -u)"

WEB_CHANGED=no
if grep -q '^packages/garmin-web/' <<<"$CHANGED_FILES"; then
  WEB_CHANGED=yes
fi

if [ "$DETECT_ONLY" -eq 1 ]; then
  echo "base=${BASE_REF:-none}"
  echo "web=$WEB_CHANGED"
  exit 0
fi

echo "▶ change detection: base=${BASE_REF:-none} + working tree → web=$WEB_CHANGED"

# --- bootstrap (garmin-mcp-server) ---
# Fresh worktrees do not share a venv. `uv run` auto-syncs the default deps and
# the [dependency-groups] dev group, but NOT the [project.optional-dependencies]
# dev extra (pytest / black / mypy live there), so without this the checks below
# fail with "command not found". Idempotent — a no-op on an already-synced venv.
# Mirrors the CI lint-and-test install step (uv sync --extra dev).
export UV_PROJECT_ENVIRONMENT="$SERVER_VENV"
echo "▶ server venv: $UV_PROJECT_ENVIRONMENT"
run uv sync --directory "$SERVER" --extra dev

# --- lint-and-test (garmin-mcp-server, whole-package) ---
# `-n auto` instead of CI's `-n 4`: this sandbox has 2 CPUs and a hard
# pids.max=512, so 4 workers buy no speed and add pid/thread pressure behind the
# `can't start new thread` flake (#740). Parity here is about WHICH checks,
# markers and thresholds run — not the worker count.
run uv run --directory "$SERVER" ruff check .
run uv run --directory "$SERVER" black --check .
run uv run --directory "$SERVER" mypy .
run uv run --directory "$SERVER" pytest -m "$PYTEST_MARKER" --tb=short -n auto --maxfail=5 \
  --cov=garmin_mcp --cov-report=term-missing --cov-fail-under=60

# --- web checks: only when packages/garmin-web/ changed ---
if [ "$WEB_CHANGED" = yes ]; then
  echo "▶ web changes detected — running web-backend / web-frontend checks"

  # web bootstrap: fresh worktrees lack the web venv and node_modules.
  # Mirrors CI (web-backend: uv sync, web-frontend: npm ci). uv sync is
  # idempotent; npm ci is heavy, so only run it when node_modules is absent.
  export UV_PROJECT_ENVIRONMENT="$WEB_VENV"
  echo "▶ web venv: $UV_PROJECT_ENVIRONMENT"
  run uv sync --directory "$WEB"
  [ -d "$FRONTEND/node_modules" ] || run npm --prefix "$FRONTEND" ci

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
  echo "▶ no packages/garmin-web/ changes — skipping web checks"
fi

if [ "$FAILED" -ne 0 ]; then
  echo "❌ ci-check FAILED" >&2
  exit 1
fi

echo "✅ ci-check passed"
exit 0
