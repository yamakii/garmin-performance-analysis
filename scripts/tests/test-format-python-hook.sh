#!/usr/bin/env bash
# Self-test for .claude/hooks/format-python.sh scoping.
#
# The hook must stay silent (exit 0, no stdout/stderr) for anything that is not
# project code, and must never run `uv` for those inputs — running `uv run`
# from the main checkout re-syncs the shared UV_PROJECT_ENVIRONMENT venv and
# used to clobber a worktree's in-progress ci-check. We stub `uv` on PATH with
# a script that records its invocation, then assert it was never called.
#
# Usage: bash scripts/tests/test-format-python-hook.sh   (run from repo root)
# Exit 0 if all cases pass; prints the failing expectation and exits 1 otherwise.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOOK="$REPO_ROOT/.claude/hooks/format-python.sh"

failures=0
fail() {
  echo "  FAIL: $*" >&2
  failures=$((failures + 1))
}

# --- stub uv: any call is a test failure ---
STUB_DIR="$(mktemp -d)"
UV_LOG="$STUB_DIR/uv-calls.log"
cat >"$STUB_DIR/uv" <<EOF
#!/usr/bin/env bash
echo "\$*" >>"$UV_LOG"
exit 0
EOF
chmod +x "$STUB_DIR/uv"
export PATH="$STUB_DIR:$PATH"

# Scratch files: a .py outside any git checkout, and a non-.py file.
SCRATCH="$(mktemp -d)"
printf 'x = 1\n' >"$SCRATCH/outside.py"
printf 'text\n' >"$SCRATCH/notes.md"
# A .py inside the checkout but outside packages/ (e.g. a scratch script).
IN_REPO_OUTSIDE_PKG="$REPO_ROOT/scripts/tests/.tmp-hook-probe.py"
printf 'x = 1\n' >"$IN_REPO_OUTSIDE_PKG"

run_case() {
  local label="$1" path="$2"
  : >"$UV_LOG"
  local out rc
  out=$(printf '{"tool_input":{"file_path":"%s"}}' "$path" | bash "$HOOK" 2>&1)
  rc=$?
  [[ $rc -eq 0 ]] || fail "$label: expected exit 0, got $rc"
  [[ -z "$out" ]] || fail "$label: expected no output, got: $out"
  [[ ! -s "$UV_LOG" ]] || fail "$label: uv must not be invoked, but was: $(cat "$UV_LOG")"
}

run_case "non-.py file" "$SCRATCH/notes.md"
run_case ".py outside any checkout" "$SCRATCH/outside.py"
run_case ".py in checkout but outside packages/" "$IN_REPO_OUTSIDE_PKG"
run_case "missing file" "$SCRATCH/does-not-exist.py"

# packages/** file: uv MUST be invoked with --no-sync and the package directory.
: >"$UV_LOG"
PKG_FILE="$REPO_ROOT/packages/garmin-mcp-server/src/garmin_mcp/__init__.py"
printf '{"tool_input":{"file_path":"%s"}}' "$PKG_FILE" | bash "$HOOK" >/dev/null 2>&1
if [[ ! -s "$UV_LOG" ]]; then
  fail "packages file: uv should have been invoked"
else
  grep -q -- "--no-sync" "$UV_LOG" || fail "packages file: uv must run with --no-sync"
  grep -q -- "--directory $REPO_ROOT/packages/garmin-mcp-server" "$UV_LOG" \
    || fail "packages file: uv must run with the package's --directory"
fi

rm -rf "$STUB_DIR" "$SCRATCH" "$IN_REPO_OUTSIDE_PKG"

if [[ $failures -ne 0 ]]; then
  echo "test-format-python-hook: $failures failure(s)" >&2
  exit 1
fi
echo "test-format-python-hook: all cases passed"
