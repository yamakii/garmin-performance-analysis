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
# Targets node 24 (the CI version). Pass explicit file paths — node 24's
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

# Behavioral self-test for ci-check.sh flag parsing (--unit-only). Uses PATH
# shims so it never runs the real (slow) checks; hermetic and CI-safe.
if [ -e scripts/tests/test-ci-check-flags.sh ]; then
  if bash scripts/tests/test-ci-check-flags.sh; then
    echo "ok (script test): ci-check-flags"
  else
    echo "FAIL (script test): ci-check-flags" >&2
    status=1
  fi
fi

# Behavioral self-test for the format-python hook scoping: it must never call
# `uv` for files outside <checkout>/packages/** (a stubbed `uv` on PATH records
# any call), and must run with --no-sync + the package --directory otherwise.
if [ -e scripts/tests/test-format-python-hook.sh ]; then
  if bash scripts/tests/test-format-python-hook.sh; then
    echo "ok (script test): format-python-hook"
  else
    echo "FAIL (script test): format-python-hook" >&2
    status=1
  fi
fi

# Behavioral self-test for wait-for-ci.sh: a PATH-shimmed `curl` serves canned
# pulls / check-runs responses, so exit codes (0 success / 1 failure / 2 timeout
# / 3 env error) are asserted without network or a real token.
if [ -e scripts/tests/test-wait-for-ci.sh ]; then
  if bash scripts/tests/test-wait-for-ci.sh; then
    echo "ok (script test): wait-for-ci"
  else
    echo "FAIL (script test): wait-for-ci" >&2
    status=1
  fi
fi

# Behavioral self-test for ci-check.sh change detection: throwaway git repos
# assert that an uncommitted or untracked web change is seen (it was not — the
# run reported success with the web tree untested) and that a stale local `main`
# does not resurrect an upstream web commit. `--detect-only` exits before any
# check runs, so no venv or toolchain is needed.
if [ -e scripts/tests/test-ci-check-detection.sh ]; then
  if bash scripts/tests/test-ci-check-detection.sh; then
    echo "ok (script test): ci-check-detection"
  else
    echo "FAIL (script test): ci-check-detection" >&2
    status=1
  fi
fi

# Behavioral self-test for the ci-check.sh container-resource guards (#1009):
# a fake cgroup dir drives the pytest worker count (`--resources-only`), and a
# private lock file asserts that a second ci-check waits / gives up instead of
# running alongside the first. Shims stand in for uv/git, so nothing heavy runs.
if [ -e scripts/tests/test-ci-check-resources.sh ]; then
  if bash scripts/tests/test-ci-check-resources.sh; then
    echo "ok (script test): ci-check-resources"
  else
    echo "FAIL (script test): ci-check-resources" >&2
    status=1
  fi
fi

# docker/ shell scripts: the entrypoint / firewall / smoke run only inside the
# sandbox container (root + NET_ADMIN), so at least parse them here. Their
# behaviour is exercised by the CI docker-build job (docker/sandbox-smoke.sh).
for f in docker/*.sh docker/lib/*.sh; do
  if bash -n "$f"; then
    echo "ok (docker script syntax): $f"
  else
    echo "FAIL (docker script syntax): $f" >&2
    status=1
  fi
done

# Behavioral self-test for the sandbox egress allowlist logic (#1027): the
# allowed-domains.txt parser and the dnsmasq config generator are pure functions
# in docker/lib/allowlist.sh, so a bad entry or a bare `server=` line (which would
# forward every name upstream) is caught here, not at container boot.
if [ -e scripts/tests/test-sandbox-allowlist.sh ]; then
  if bash scripts/tests/test-sandbox-allowlist.sh; then
    echo "ok (script test): sandbox-allowlist"
  else
    echo "FAIL (script test): sandbox-allowlist" >&2
    status=1
  fi
fi

# Behavioral self-test for the managed-settings generator (#1028): the policy for
# Claude Code's built-in sandbox is built with jq from allowed-domains.txt + env,
# so a wrong key, a missing allowWrite path or a mask leaking into the default
# output is caught here, not after a rebuild.
if [ -e scripts/tests/test-sandbox-managed-settings.sh ]; then
  if bash scripts/tests/test-sandbox-managed-settings.sh; then
    echo "ok (script test): sandbox-managed-settings"
  else
    echo "FAIL (script test): sandbox-managed-settings" >&2
    status=1
  fi
fi

if [ "$status" -ne 0 ]; then
  echo "check-claude-scripts: FAILED" >&2
else
  echo "check-claude-scripts: all .claude scripts parse + logic tests pass"
fi
exit "$status"
