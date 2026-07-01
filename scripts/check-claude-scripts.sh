#!/usr/bin/env bash
# Syntax-smoke for .claude/ orchestration scripts that CI otherwise never checks.
#
# - .claude/workflows/*.js : workflow scripts are an async-function-body dialect
#   (top-level `export const meta`, `await`, `return`), so plain `node --check`
#   rejects them. We strip the `export` and wrap the body in an async function,
#   then `node --check` the result.
# - .claude/hooks/*.sh      : `bash -n` (no-exec parse).
#
# This catches syntax/parse breakage. It does NOT verify behavior — see the
# mandatory pre-merge e2e rule in .claude/rules/dev/implementation-workflow.md.
#
# Usage: scripts/check-claude-scripts.sh   (run from repo root)
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
status=0
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

shopt -s nullglob

for f in .claude/workflows/*.js; do
  wrapped="$tmp/$(basename "$f").mjs"
  {
    echo 'async function __wf__() {'
    sed 's/^export const /const /' "$f"
    echo '}'
  } >"$wrapped"
  if node --check "$wrapped"; then
    echo "ok (workflow): $f"
  else
    echo "FAIL (workflow syntax): $f" >&2
    status=1
  fi
done

for f in .claude/hooks/*.sh; do
  if bash -n "$f"; then
    echo "ok (hook): $f"
  else
    echo "FAIL (hook syntax): $f" >&2
    status=1
  fi
done

# Behavioral tests for workflow pure logic (extracted from source; see
# .claude/workflows/tests/). These catch logic regressions, not just syntax.
# Targets node 22 (the CI version). Pass explicit file paths — node 22's
# `--test` does not accept a directory.
wf_tests=()
for t in .claude/workflows/tests/*.test.mjs; do
  [ -e "$t" ] && wf_tests+=("$t")
done
if [ "${#wf_tests[@]}" -gt 0 ]; then
  if node --test "${wf_tests[@]}"; then
    echo "ok (workflow tests): node --test"
  else
    echo "FAIL (workflow tests)" >&2
    status=1
  fi
fi

# Agent-model gate: every agent() in .claude/workflows/*.js must resolve a
# model (explicit model: or an agentType whose def declares model:). Prevents
# silent inheritance of the (usually Opus) session model.
if node scripts/check-workflow-agent-model.mjs; then
  echo "ok (agent model gate)"
else
  echo "FAIL (agent model gate)" >&2
  status=1
fi

# scripts/tests/*.sh : syntax-smoke (bash -n) for the self-tests themselves.
for f in scripts/tests/*.sh; do
  if bash -n "$f"; then
    echo "ok (script test syntax): $f"
  else
    echo "FAIL (script test syntax): $f" >&2
    status=1
  fi
done

# Behavioral self-test for the merged-worktree cleanup script. Builds its own
# temp git repos, so it is hermetic and safe to run in CI.
if [ -x scripts/tests/test-cleanup-merged-worktrees.sh ] || [ -e scripts/tests/test-cleanup-merged-worktrees.sh ]; then
  if bash scripts/tests/test-cleanup-merged-worktrees.sh; then
    echo "ok (script test): cleanup-merged-worktrees"
  else
    echo "FAIL (script test): cleanup-merged-worktrees" >&2
    status=1
  fi
fi

if [ "$status" -ne 0 ]; then
  echo "check-claude-scripts: FAILED" >&2
else
  echo "check-claude-scripts: all .claude scripts parse + logic tests pass"
fi
exit "$status"
