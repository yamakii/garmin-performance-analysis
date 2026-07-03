#!/usr/bin/env bash
# Self-test for scripts/ci-check.sh flag parsing.
#
# We do NOT run the real checks (uv/pytest/mypy are slow and need a synced
# venv). Instead we assert the flag-parsing contract by intercepting the
# resolved pytest marker: the script is sourced-equivalent via a stubbed
# environment where `run` echoes its argv, so we can observe which marker the
# pytest step uses without executing anything heavy.
#
# Strategy: run ci-check.sh with a PATH shim that stubs every external command
# (uv, git, node, npm, npx) as no-ops that just echo their argv. This lets the
# script reach the pytest `run` line and print the marker, while never doing
# real work. We grep the output for the marker and assert per-flag behavior.
#
# Usage: bash scripts/tests/test-ci-check-flags.sh   (run from repo root)
# Exit 0 if all cases pass; prints the failing expectation and exits 1 otherwise.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CI_CHECK="$SCRIPT_DIR/ci-check.sh"

failures=0

fail() {
  echo "  FAIL: $*" >&2
  failures=$((failures + 1))
}

# Build a temp dir of shim executables (uv, git, npm, npx, node, black, mypy,
# ruff, pytest) that just echo their argv and exit 0. Echoes the shim dir path.
setup_shims() {
  local dir
  dir="$(mktemp -d)"
  for cmd in uv git npm npx node; do
    cat >"$dir/$cmd" <<'EOF'
#!/usr/bin/env bash
echo "SHIM $(basename "$0") $*"
exit 0
EOF
    chmod +x "$dir/$cmd"
  done
  echo "$dir"
}

# Run ci-check.sh with the shims taking precedence on PATH. Echoes combined
# stdout+stderr. Passes through any args ($@ after the first).
run_ci_check() {
  local shims="$1"
  shift
  PATH="$shims:$PATH" bash "$CI_CHECK" "$@" 2>&1
}

# ---------------------------------------------------------------------------

test_default_runs_integration() {
  echo "test_default_runs_integration"
  local shims out; shims="$(setup_shims)"
  out="$(run_ci_check "$shims")"
  echo "$out" | grep -q "pytest -m unit or integration" \
    || fail "default run must use marker 'unit or integration' (got: $(echo "$out" | grep pytest || true))"
}

test_unit_only_skips_integration() {
  echo "test_unit_only_skips_integration"
  local shims out; shims="$(setup_shims)"
  out="$(run_ci_check "$shims" --unit-only)"
  echo "$out" | grep -q "pytest -m unit --tb" \
    || fail "--unit-only must use marker 'unit' only (got: $(echo "$out" | grep pytest || true))"
  if echo "$out" | grep -q "pytest -m unit or integration"; then
    fail "--unit-only must NOT run the combined unit-or-integration marker"
  fi
}

test_unknown_flag_rejected() {
  echo "test_unknown_flag_rejected"
  local shims; shims="$(setup_shims)"
  PATH="$shims:$PATH" bash "$CI_CHECK" --bogus >/dev/null 2>&1
  [ "$?" -eq 2 ] || fail "unknown flag must exit 2"
}

# ---------------------------------------------------------------------------

test_default_runs_integration
test_unit_only_skips_integration
test_unknown_flag_rejected

if [ "$failures" -ne 0 ]; then
  echo "test-ci-check-flags: FAILED ($failures failure(s))" >&2
  exit 1
fi
echo "test-ci-check-flags: all cases passed"
exit 0
