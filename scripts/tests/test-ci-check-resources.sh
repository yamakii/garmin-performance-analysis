#!/usr/bin/env bash
# Self-test for the container-resource guards in scripts/ci-check.sh (#1009):
# the pytest worker count derived from cgroup memory headroom, and the
# container-wide lock.
#
# Hermetic: a fake cgroup v2 dir stands in for /sys/fs/cgroup, `--resources-only`
# exits before any check runs, the lock cases use a private lock file, and the
# full-path cases stub every external command (uv, git, npm, npx, node) with a
# PATH shim — so no venv, network or toolchain is needed.
#
# Output contract of --resources-only (one line each):
#   headroom=<bytes|unknown>
#   cpus=<n>
#   workers=<n>
#   lock=<path|none>
#   lock_enforced=<yes|no>      (yes: memory.max < CI_CHECK_LOCK_BELOW or unknown)
#
# Usage: bash scripts/tests/test-ci-check-resources.sh   (run from repo root)
# Exit 0 if all cases pass; prints failing expectations and exits 1 otherwise.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CI_CHECK="$SCRIPT_DIR/ci-check.sh"
GiB=$((1024 * 1024 * 1024))
KERNEL=100000000   # bytes of `kernel` in every fake memory.stat

failures=0
fail() { echo "  FAIL: $*" >&2; failures=$((failures + 1)); }
expect() {  # expect <label> <actual> <wanted>
  if [ "$2" != "$3" ]; then
    fail "$1: got '$2', want '$3'"
  fi
}

# make_cgroup <dir> <memory.max> <anon> [swap] — a fake cgroup v2 memory dir.
# `file` is large on purpose: page cache must NOT count against headroom.
make_cgroup() {
  local dir="$1" max="$2" anon="$3" swap="${4:-0}"
  mkdir -p "$dir"
  echo "$max" >"$dir/memory.max"
  printf 'anon %s\nfile 900000000\nkernel %s\nshmem 0\n' "$anon" "$KERNEL" >"$dir/memory.stat"
  echo "$swap" >"$dir/memory.swap.current"
}

# resources <cgroup_dir> <key> — run --resources-only with cpus=2, echo `key`.
resources() {
  local out
  out="$(CI_CHECK_CGROUP_DIR="$1" CI_CHECK_CPUS=2 CI_CHECK_LOCK="" \
    bash "$CI_CHECK" --resources-only 2>/dev/null)"
  sed -n "s/^$2=//p" <<<"$out"
}

# Shims for the full-path cases: every external command echoes its argv, exit 0.
setup_shims() {
  local dir
  dir="$(mktemp -d)"
  for cmd in uv git npm npx node; do
    printf '#!/usr/bin/env bash\necho "SHIM $(basename "$0") $*"\nexit 0\n' >"$dir/$cmd"
    chmod +x "$dir/$cmd"
  done
  echo "$dir"
}

# ---------------------------------------------------------------------------

test_resources_ample_headroom_uses_all_cpus() {
  echo "test_resources_ample_headroom_uses_all_cpus"
  local cg; cg="$(mktemp -d)/cg"
  make_cgroup "$cg" $((4 * GiB)) $((1 * GiB))
  expect "headroom excludes page cache" "$(resources "$cg" headroom)" $((4 * GiB - 1 * GiB - KERNEL))
  expect "workers with ~2.9 GB free" "$(resources "$cg" workers)" 2
}

test_resources_tight_headroom_falls_back_to_one_worker() {
  echo "test_resources_tight_headroom_falls_back_to_one_worker"
  local cg; cg="$(mktemp -d)/cg"
  make_cgroup "$cg" $((4 * GiB)) $((3 * GiB))   # ~0.9 GB free < base + 1 worker
  expect "workers with ~0.9 GB free" "$(resources "$cg" workers)" 1
}

test_resources_swap_counts_as_used() {
  echo "test_resources_swap_counts_as_used"
  local cg; cg="$(mktemp -d)/cg"
  make_cgroup "$cg" $((4 * GiB)) $((2 * GiB)) $((1 * GiB))   # anon alone would allow 2
  expect "workers with 1 GB swapped out" "$(resources "$cg" workers)" 1
}

test_resources_over_limit_reports_zero_headroom() {
  echo "test_resources_over_limit_reports_zero_headroom"
  local cg; cg="$(mktemp -d)/cg"
  make_cgroup "$cg" $((4 * GiB)) $((5 * GiB))
  expect "headroom clamps at 0" "$(resources "$cg" headroom)" 0
  expect "workers never below 1" "$(resources "$cg" workers)" 1
}

test_resources_unlimited_cgroup_reports_unknown() {
  echo "test_resources_unlimited_cgroup_reports_unknown"
  local cg; cg="$(mktemp -d)/cg"
  make_cgroup "$cg" max $((1 * GiB))
  expect "memory.max=max → unknown" "$(resources "$cg" headroom)" unknown
  expect "unknown headroom → all cpus" "$(resources "$cg" workers)" 2
}

test_resources_missing_cgroup_reports_unknown() {
  echo "test_resources_missing_cgroup_reports_unknown"
  expect "absent dir → unknown" "$(resources /nonexistent/cgroup headroom)" unknown
  expect "absent dir → all cpus" "$(resources /nonexistent/cgroup workers)" 2
}

test_lock_held_times_out_with_exit_1() {
  echo "test_lock_held_times_out_with_exit_1"
  local lock out rc
  lock="$(mktemp)"
  exec 8>"$lock"
  flock 8 || fail "test setup: could not take the lock"
  out="$(CI_CHECK_LOCK="$lock" CI_CHECK_LOCK_WAIT=1 CI_CHECK_CGROUP_DIR=/nonexistent \
    bash "$CI_CHECK" 8>&- 2>&1)"
  rc=$?
  exec 8>&-
  expect "held lock → exit 1" "$rc" 1
  echo "$out" | grep -q "lock" || fail "held lock must be reported (got: $out)"
  if echo "$out" | grep -q "SHIM\|uv sync\|pytest"; then
    fail "no check may run while the lock is held"
  fi
}

test_lock_enforced_on_small_cgroup() {
  echo "test_lock_enforced_on_small_cgroup"
  local cg lock out rc
  cg="$(mktemp -d)/cg"
  make_cgroup "$cg" $((4 * GiB)) $((1 * GiB))
  lock="$(mktemp)"
  exec 8>"$lock"
  flock 8 || fail "test setup: could not take the lock"
  out="$(CI_CHECK_LOCK="$lock" CI_CHECK_LOCK_WAIT=1 CI_CHECK_CGROUP_DIR="$cg" \
    bash "$CI_CHECK" 8>&- 2>&1)"
  rc=$?
  exec 8>&-
  expect "4 GiB cgroup + held lock → exit 1" "$rc" 1
  echo "$out" | grep -q "lock" || fail "held lock must be reported (got: $out)"
}

test_lock_skipped_on_large_cgroup() {
  echo "test_lock_skipped_on_large_cgroup"
  local cg lock shims out rc
  cg="$(mktemp -d)/cg"
  make_cgroup "$cg" $((32 * GiB)) $((1 * GiB))
  lock="$(mktemp)"
  shims="$(setup_shims)"
  exec 8>"$lock"
  flock 8 || fail "test setup: could not take the lock"
  out="$(CI_CHECK_LOCK="$lock" CI_CHECK_LOCK_WAIT=1 CI_CHECK_CGROUP_DIR="$cg" CI_CHECK_CPUS=2 \
    PATH="$shims:$PATH" bash "$CI_CHECK" 8>&- 2>&1)"
  rc=$?
  exec 8>&-
  expect "32 GiB cgroup + held lock → runs anyway, exit 0" "$rc" 0
  echo "$out" | grep -q "pytest -m unit or integration --tb=short -n 2 " \
    || fail "pytest step must run with all cpus on a large cgroup (got: $(echo "$out" | grep 'pytest -m' || true))"
  if echo "$out" | grep -q "waiting"; then
    fail "a large cgroup must not queue on the lock or the memory gate"
  fi
}

test_lock_enforced_when_cgroup_unknown() {
  echo "test_lock_enforced_when_cgroup_unknown"
  expect "absent cgroup → lock enforced" "$(resources /nonexistent/cgroup lock_enforced)" yes
}

test_resources_reports_lock_enforced() {
  echo "test_resources_reports_lock_enforced"
  local small large
  small="$(mktemp -d)/cg"; make_cgroup "$small" $((4 * GiB)) $((1 * GiB))
  large="$(mktemp -d)/cg"; make_cgroup "$large" $((32 * GiB)) $((1 * GiB))
  expect "4 GiB → enforced" "$(resources "$small" lock_enforced)" yes
  expect "32 GiB → not enforced" "$(resources "$large" lock_enforced)" no
}

test_lock_free_runs_and_releases() {
  echo "test_lock_free_runs_and_releases"
  local lock shims out rc
  lock="$(mktemp)"
  shims="$(setup_shims)"
  out="$(CI_CHECK_LOCK="$lock" CI_CHECK_LOCK_WAIT=1 CI_CHECK_CGROUP_DIR=/nonexistent \
    PATH="$shims:$PATH" bash "$CI_CHECK" 2>&1)"
  rc=$?
  expect "free lock → checks run, exit 0" "$rc" 0
  echo "$out" | grep -q "pytest -m unit or integration" \
    || fail "pytest step must be reached (got: $(echo "$out" | grep pytest || true))"
  # The lock must be released on exit: a second run must not wait.
  out="$(CI_CHECK_LOCK="$lock" CI_CHECK_LOCK_WAIT=1 CI_CHECK_CGROUP_DIR=/nonexistent \
    PATH="$shims:$PATH" bash "$CI_CHECK" --unit-only 2>&1)"
  expect "lock released after first run" "$?" 0
}

test_tight_headroom_runs_pytest_with_one_worker() {
  echo "test_tight_headroom_runs_pytest_with_one_worker"
  local cg shims out
  cg="$(mktemp -d)/cg"
  make_cgroup "$cg" $((4 * GiB)) $((3 * GiB))
  shims="$(setup_shims)"
  # CI_CHECK_MEM_WAIT=0: the gate warns and proceeds instead of polling.
  out="$(CI_CHECK_LOCK="" CI_CHECK_CGROUP_DIR="$cg" CI_CHECK_CPUS=2 CI_CHECK_MEM_WAIT=0 \
    PATH="$shims:$PATH" bash "$CI_CHECK" 2>&1)"
  echo "$out" | grep -q "pytest -m unit or integration --tb=short -n 1 " \
    || fail "tight headroom must run pytest with -n 1 (got: $(echo "$out" | grep 'pytest -m' || true))"
  echo "$out" | grep -q "WARNING: only" \
    || fail "expired memory wait must be reported as a WARNING"
}

test_ample_headroom_runs_pytest_with_all_cpus() {
  echo "test_ample_headroom_runs_pytest_with_all_cpus"
  local cg shims out
  cg="$(mktemp -d)/cg"
  make_cgroup "$cg" $((4 * GiB)) $((1 * GiB))
  shims="$(setup_shims)"
  out="$(CI_CHECK_LOCK="" CI_CHECK_CGROUP_DIR="$cg" CI_CHECK_CPUS=2 \
    PATH="$shims:$PATH" bash "$CI_CHECK" 2>&1)"
  echo "$out" | grep -q "pytest -m unit or integration --tb=short -n 2 " \
    || fail "ample headroom must run pytest with -n 2 (got: $(echo "$out" | grep 'pytest -m' || true))"
  if echo "$out" | grep -q "waiting"; then
    fail "ample headroom must not wait"
  fi
}

# --- worker cap (#1061): more than 4 xdist workers is slower on this suite ---

# resources_with <cgroup_dir> <key> <extra env...> — like `resources`, but the
# caller supplies CI_CHECK_CPUS (and anything else) explicitly.
resources_with() {
  local cg="$1" key="$2" out
  shift 2
  out="$(env "$@" CI_CHECK_CGROUP_DIR="$cg" CI_CHECK_LOCK="" \
    bash "$CI_CHECK" --resources-only 2>/dev/null)"
  sed -n "s/^$key=//p" <<<"$out"
}

test_resources_many_cpus_capped_at_max_workers() {
  echo "test_resources_many_cpus_capped_at_max_workers"
  local cg; cg="$(mktemp -d)/cg"
  make_cgroup "$cg" $((32 * GiB)) $((1 * GiB))   # headroom fits far more than 12
  expect "12 cpus → capped" "$(resources_with "$cg" workers CI_CHECK_CPUS=12)" 4
  expect "cap is reported" "$(resources_with "$cg" max_workers CI_CHECK_CPUS=12)" 4
}

test_resources_max_workers_override() {
  echo "test_resources_max_workers_override"
  local cg; cg="$(mktemp -d)/cg"
  make_cgroup "$cg" $((32 * GiB)) $((1 * GiB))
  expect "CI_CHECK_MAX_WORKERS=8 → 8" \
    "$(resources_with "$cg" workers CI_CHECK_CPUS=12 CI_CHECK_MAX_WORKERS=8)" 8
  expect "cap never exceeds cpus" \
    "$(resources_with "$cg" workers CI_CHECK_CPUS=2 CI_CHECK_MAX_WORKERS=8)" 2
}

test_resources_unknown_headroom_still_capped() {
  echo "test_resources_unknown_headroom_still_capped"
  expect "absent cgroup + 12 cpus → capped" \
    "$(resources_with /nonexistent/cgroup workers CI_CHECK_CPUS=12)" 4
}

test_full_path_uses_capped_workers() {
  echo "test_full_path_uses_capped_workers"
  local cg shims out
  cg="$(mktemp -d)/cg"
  make_cgroup "$cg" $((32 * GiB)) $((1 * GiB))
  shims="$(setup_shims)"
  out="$(CI_CHECK_LOCK="" CI_CHECK_CGROUP_DIR="$cg" CI_CHECK_CPUS=12 \
    PATH="$shims:$PATH" bash "$CI_CHECK" 2>&1)"
  echo "$out" | grep -q "pytest -m unit or integration --tb=short -n 4 " \
    || fail "12 cpus must run pytest with -n 4 (got: $(echo "$out" | grep 'pytest -m' || true))"
}

# ---------------------------------------------------------------------------

test_resources_ample_headroom_uses_all_cpus
test_resources_tight_headroom_falls_back_to_one_worker
test_resources_swap_counts_as_used
test_resources_over_limit_reports_zero_headroom
test_resources_unlimited_cgroup_reports_unknown
test_resources_missing_cgroup_reports_unknown
test_lock_held_times_out_with_exit_1
test_lock_enforced_on_small_cgroup
test_lock_skipped_on_large_cgroup
test_lock_enforced_when_cgroup_unknown
test_resources_reports_lock_enforced
test_lock_free_runs_and_releases
test_tight_headroom_runs_pytest_with_one_worker
test_ample_headroom_runs_pytest_with_all_cpus
test_resources_many_cpus_capped_at_max_workers
test_resources_max_workers_override
test_resources_unknown_headroom_still_capped
test_full_path_uses_capped_workers

if [ "$failures" -ne 0 ]; then
  echo "test-ci-check-resources: FAILED ($failures failure(s))" >&2
  exit 1
fi
echo "test-ci-check-resources: all cases passed"
exit 0
