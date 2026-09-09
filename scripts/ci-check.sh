#!/bin/bash
# CI parity check — reproduces the GitHub Actions `lint-and-test` job
# (+ web-backend / web-frontend when packages/garmin-web/ changed) locally,
# whole-package, mirroring .github/workflows/ci.yml.
#
# Use this before completing Phase 2b and before any `--no-verify` commit.
#   scripts/ci-check.sh               → runs unit + integration (CI-identical)
#   scripts/ci-check.sh --unit-only   → skips integration (faster, for iteration)
#   scripts/ci-check.sh --detect-only → print the change-detection decision, exit 0
#   scripts/ci-check.sh --resources-only → print the memory/worker/lock decision, exit 0
# exit 0 (all pass) / exit 1 (something failed, or lock wait timed out) / exit 2 (bad usage)
#
# Only ONE ci-check runs per container at a time (flock on CI_CHECK_LOCK), and the
# heavy steps wait for cgroup memory headroom — see "container resources" below.
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
RESOURCES_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --unit-only)
      PYTEST_MARKER="unit"
      ;;
    --detect-only)
      DETECT_ONLY=1
      ;;
    --resources-only)
      RESOURCES_ONLY=1
      ;;
    *)
      echo "unknown argument: $arg" >&2
      echo "usage: ci-check.sh [--unit-only] [--detect-only] [--resources-only]" >&2
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

# --- per-package, per-worktree virtualenvs (#1003, #1047) ---
# One venv per (checkout, package), outside the bind-mounted repo, so parallel
# ci-check runs and the MCP server never share a mutable environment. The
# mapping lives in docker/lib/uv-venv.sh — the same code the sandbox's
# /usr/local/bin/uv wrapper uses — so this script and every other `uv` call in
# the container agree on the path. CI_CHECK_VENV_BASE is kept for the tests.
export UV_VENV_BASE="${CI_CHECK_VENV_BASE:-${UV_VENV_BASE:-${HOME:-/home/claude}/uv-venvs}}"
# shellcheck source=../docker/lib/uv-venv.sh
. "$ROOT/docker/lib/uv-venv.sh"
SERVER_VENV="$(uv_venv_path "$SERVER" 2>/dev/null || printf '%s/%s-server' "$UV_VENV_BASE" "$(printf '%s' "$ROOT" | cksum | cut -d' ' -f1)")"
WEB_VENV="$(uv_venv_path "$WEB" 2>/dev/null || printf '%s/%s-web' "$UV_VENV_BASE" "$(printf '%s' "$ROOT" | cksum | cut -d' ' -f1)")"

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

# --- container resources: one ci-check at a time + memory headroom gate (#1009) ---
# The sandbox is a small container (docker/run.sh: --memory / --cpus / --pids-limit).
# Measured 2026-09-06 in the 4 GiB / 2-CPU box: `mypy .` peaks +600 MB, `pytest
# -n auto` +1.4 GB (2 workers + controller), and every live Claude session already
# costs ~600 MB (claude + its own MCP servers). Two ci-checks — or one ci-check
# next to an analyze-activity workflow — drove the cgroup to memory.max and Docker
# answered with SIGKILL(137) on whole sessions (daemon.log 09-05 22:27Z, 09-06
# 03:31Z / 07:29Z / 07:47Z); each restarted session then relaunched ci-check, so
# the kills cascaded. Two guards:
#   1. a container-wide flock, so ci-check runs strictly one at a time — but only
#      while the container is small (memory.max < CI_CHECK_LOCK_BELOW, or unknown).
#      On a large cgroup two runs coexist comfortably and the owner wants parallel
#      validation to actually be parallel (#1011), so there the lock is skipped and
#      guard 2 is the only brake;
#   2. before each heavy step, wait until the cgroup has enough headroom, and size
#      the pytest worker pool from what is actually free.
# Everything is overridable (tests, other hosts). Without cgroup v2 memory
# accounting (memory.max=max, non-Linux, no /sys/fs/cgroup) the gate is a no-op.
CI_CHECK_LOCK="${CI_CHECK_LOCK-/tmp/ci-check.lock}"   # empty → no lock
CI_CHECK_LOCK_WAIT="${CI_CHECK_LOCK_WAIT:-1800}"      # seconds
CI_CHECK_LOCK_BELOW="${CI_CHECK_LOCK_BELOW:-$((16 * 1024 * 1024 * 1024))}"  # bytes of memory.max
CI_CHECK_CGROUP_DIR="${CI_CHECK_CGROUP_DIR:-/sys/fs/cgroup}"
# `nproc` clamps to OMP_NUM_THREADS (exported to 1 above for the BLAS pools), so
# unset it for the query; the affinity-aware count is what xdist would pick.
CI_CHECK_CPUS="${CI_CHECK_CPUS:-$(env -u OMP_NUM_THREADS -u OMP_THREAD_LIMIT nproc 2>/dev/null || echo 2)}"
# Hard cap on the xdist pool, whatever the CPU count (#1061, raised in #1080).
# The cap exists because every test writes its own DuckDB file: on the overlay
# /tmp (2026-09-08) more workers were slower (4 → 51-56 s, 8 → 186 s, 12 →
# 97-131 s). With /tmp on tmpfs (#1078, measured 2026-09-09 on the 12-CPU
# sandbox, host I/O pressure 28-54 %): 4 workers 32-36 s, 8 workers 24 s,
# 12 workers 26 s — 8 is the knee, 12 only adds ~2 GB of worker memory.
# Each worker costs ~500 MB; pick_pytest_workers still sizes down from cgroup
# headroom when the box is busy.
CI_CHECK_MAX_WORKERS="${CI_CHECK_MAX_WORKERS:-8}"
CI_CHECK_MEM_MYPY="${CI_CHECK_MEM_MYPY:-$((800 * 1024 * 1024))}"               # bytes
CI_CHECK_MEM_PYTEST_BASE="${CI_CHECK_MEM_PYTEST_BASE:-$((700 * 1024 * 1024))}" # controller
CI_CHECK_MEM_PER_WORKER="${CI_CHECK_MEM_PER_WORKER:-$((500 * 1024 * 1024))}"   # per xdist worker
CI_CHECK_MEM_WAIT="${CI_CHECK_MEM_WAIT:-600}"         # seconds
CI_CHECK_MEM_POLL="${CI_CHECK_MEM_POLL:-10}"          # seconds

# cgroup_memory_max — memory.max in bytes, or "unknown" (no cgroup v2 / "max").
cgroup_memory_max() {
  local max
  if [ ! -r "$CI_CHECK_CGROUP_DIR/memory.max" ]; then
    echo unknown
    return 0
  fi
  max="$(cat "$CI_CHECK_CGROUP_DIR/memory.max")"
  case "$max" in
    ''|*[!0-9]*) echo unknown ;;
    *) echo "$max" ;;
  esac
}

# lock_enforced — "yes" when the container is too small for two ci-checks to
# coexist (memory.max < CI_CHECK_LOCK_BELOW) or its size is unknown; "no" on a
# large cgroup, where the headroom gate alone is protection enough.
lock_enforced() {
  local max
  max="$(cgroup_memory_max)"
  if [ "$max" = unknown ] || [ "$max" -lt "$CI_CHECK_LOCK_BELOW" ]; then
    echo yes
  else
    echo no
  fi
}

# cgroup_headroom_bytes — bytes the cgroup can still allocate before memory.max,
# counting only what reclaim cannot give back (anon + kernel + shmem + swap).
# Page cache is excluded on purpose: memory.current includes it, and a box that
# just synced a venv would look full while being fine. Prints "unknown" when the
# cgroup v2 files are missing or the limit is "max".
cgroup_headroom_bytes() {
  local max stat anon kernel shmem swap used
  if [ ! -r "$CI_CHECK_CGROUP_DIR/memory.max" ] || [ ! -r "$CI_CHECK_CGROUP_DIR/memory.stat" ]; then
    echo unknown
    return 0
  fi
  max="$(cat "$CI_CHECK_CGROUP_DIR/memory.max")"
  case "$max" in
    ''|*[!0-9]*) echo unknown; return 0 ;;
  esac
  stat="$(cat "$CI_CHECK_CGROUP_DIR/memory.stat")"
  anon="$(sed -n 's/^anon //p' <<<"$stat")"
  kernel="$(sed -n 's/^kernel //p' <<<"$stat")"
  shmem="$(sed -n 's/^shmem //p' <<<"$stat")"
  swap=0
  if [ -r "$CI_CHECK_CGROUP_DIR/memory.swap.current" ]; then
    swap="$(cat "$CI_CHECK_CGROUP_DIR/memory.swap.current")"
  fi
  used=$(( ${anon:-0} + ${kernel:-0} + ${shmem:-0} + ${swap:-0} ))
  if [ "$max" -gt "$used" ]; then
    echo $(( max - used ))
  else
    echo 0
  fi
}

# pick_pytest_workers <headroom|unknown> <cpus> — min(cpus, what fits,
# CI_CHECK_MAX_WORKERS), never < 1.
pick_pytest_workers() {
  local headroom="$1" cpus="$2" fit
  if [ "$headroom" = unknown ]; then
    fit="$cpus"
  else
    fit=$(( (headroom - CI_CHECK_MEM_PYTEST_BASE) / CI_CHECK_MEM_PER_WORKER ))
    [ "$fit" -gt "$cpus" ] && fit="$cpus"
  fi
  [ "$fit" -gt "$CI_CHECK_MAX_WORKERS" ] && fit="$CI_CHECK_MAX_WORKERS"
  [ "$fit" -lt 1 ] && fit=1
  echo "$fit"
}

# wait_for_headroom <bytes> <label> — poll until the cgroup has `bytes` free or
# CI_CHECK_MEM_WAIT expires, then continue either way: the caller has already
# sized itself to the minimum, and blocking forever would only move the hang.
# One line per decision so the log shows why a run waited.
wait_for_headroom() {
  local need="$1" label="$2" waited=0 headroom
  headroom="$(cgroup_headroom_bytes)"
  [ "$headroom" = unknown ] && return 0
  while [ "$headroom" -lt "$need" ]; do
    if [ "$waited" -ge "$CI_CHECK_MEM_WAIT" ]; then
      echo "  ↳ WARNING: only $((headroom / 1048576)) MB free after ${waited}s — running $label anyway" >&2
      return 0
    fi
    if [ "$waited" -eq 0 ]; then
      echo "▶ $label needs $((need / 1048576)) MB, cgroup has $((headroom / 1048576)) MB free — waiting (max ${CI_CHECK_MEM_WAIT}s)"
    fi
    sleep "$CI_CHECK_MEM_POLL"
    waited=$((waited + CI_CHECK_MEM_POLL))
    headroom="$(cgroup_headroom_bytes)"
  done
  return 0
}

if [ "$RESOURCES_ONLY" -eq 1 ]; then
  HEADROOM="$(cgroup_headroom_bytes)"
  echo "headroom=$HEADROOM"
  echo "cpus=$CI_CHECK_CPUS"
  echo "max_workers=$CI_CHECK_MAX_WORKERS"
  echo "workers=$(pick_pytest_workers "$HEADROOM" "$CI_CHECK_CPUS")"
  echo "lock=${CI_CHECK_LOCK:-none}"
  echo "lock_enforced=$(lock_enforced)"
  exit 0
fi

# The lock fd is inherited by every child, so a pytest worker that outlives a
# killed session keeps the lock — deliberately: that orphan is still eating
# memory, which is exactly when the next run must wait.
if [ -n "$CI_CHECK_LOCK" ] && [ "$(lock_enforced)" = yes ]; then
  exec 9>"$CI_CHECK_LOCK"
  if ! flock -n 9; then
    echo "▶ another ci-check holds $CI_CHECK_LOCK — waiting (max ${CI_CHECK_LOCK_WAIT}s)"
    if ! flock -w "$CI_CHECK_LOCK_WAIT" 9; then
      echo "❌ ci-check: gave up waiting for lock $CI_CHECK_LOCK after ${CI_CHECK_LOCK_WAIT}s" >&2
      exit 1
    fi
  fi
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
# Worker count: min(cpus, cgroup headroom, CI_CHECK_MAX_WORKERS=8). Each worker
# costs ~500 MB (#1009), a hard pids.max sits behind the `can't start new thread`
# flake (#740), and beyond 8 workers the per-test DuckDB files stop paying off
# even on tmpfs (#1061 → #1080). Parity with CI's `-n 4` is about WHICH checks,
# markers and thresholds run — not the worker count.
run uv run --directory "$SERVER" ruff check .
run uv run --directory "$SERVER" black --check .
wait_for_headroom "$CI_CHECK_MEM_MYPY" "mypy"
run uv run --directory "$SERVER" mypy .
wait_for_headroom $((CI_CHECK_MEM_PYTEST_BASE + CI_CHECK_MEM_PER_WORKER)) "pytest"
HEADROOM="$(cgroup_headroom_bytes)"
PYTEST_WORKERS="$(pick_pytest_workers "$HEADROOM" "$CI_CHECK_CPUS")"
echo "▶ pytest workers: $PYTEST_WORKERS (cpus=$CI_CHECK_CPUS, headroom=$HEADROOM)"
run uv run --directory "$SERVER" pytest -m "$PYTEST_MARKER" --tb=short -n "$PYTEST_WORKERS" --maxfail=5 \
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
