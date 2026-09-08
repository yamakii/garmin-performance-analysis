#!/usr/bin/env bash
# Table-driven self-test for the PreToolUse guard hooks (#1048):
#   block-commit-on-main.sh, guard-no-verify.sh, guard-data-deletion.sh, guard-push.sh
# Each hook reads {"tool_input":{"command":...}} on stdin and exits 0 (pass
# through to the normal permission flow) or 2 (block). Hermetic: temp git repos
# stand in for main / feature checkouts; nothing is executed but the hooks.
#
# Usage: bash scripts/tests/test-guard-hooks.sh   (run from repo root)
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOOKS="$ROOT/.claude/hooks"
failures=0
fail() { echo "  FAIL: $*" >&2; failures=$((failures + 1)); }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# Temp repos: one checked out on main, one on a feature branch.
for name in onmain onfeat; do
  git -C "$tmp" init -q -b main "$name"
  git -C "$tmp/$name" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
done
git -C "$tmp/onfeat" checkout -q -b feat/x

# run_hook HOOK CWD COMMAND → prints the hook's exit code
run_hook() {
  local hook="$1" cwd="$2" cmd="$3" json
  json="$(printf '%s' "$cmd" | python3 -c 'import json,sys; print(json.dumps({"tool_input":{"command":sys.stdin.read()}}))')"
  (cd "$cwd" && printf '%s' "$json" | bash "$HOOKS/$hook" >/dev/null 2>&1)
  echo $?
}

# Case table: hook | cwd | expected exit | command
# (no double quotes inside commands; keep each case on one line)
cases=(
  # test_block_commit_on_main_blocks_main
  "block-commit-on-main.sh|onmain|2|git commit -m x"
  "block-commit-on-main.sh|onfeat|0|git commit -m x"
  "block-commit-on-main.sh|onmain|0|git status"
  "block-commit-on-main.sh|onfeat|2|git -C $tmp/onmain commit -m x"
  "block-commit-on-main.sh|onmain|0|git -C $tmp/onfeat commit -m x"
  # test_guard_no_verify
  "guard-no-verify.sh|onfeat|2|git commit --no-verify -m x"
  "guard-no-verify.sh|onfeat|0|CI_CHECKED=1 git commit --no-verify -m x"
  "guard-no-verify.sh|onfeat|0|git commit -m x"
  "guard-no-verify.sh|onfeat|2|git -C $tmp/onfeat commit --no-verify -m x"
  # test_guard_data_deletion
  "guard-data-deletion.sh|onfeat|2|rm -rf data/x"
  "guard-data-deletion.sh|onfeat|2|rm x.duckdb"
  "guard-data-deletion.sh|onfeat|2|rm -r result/old"
  "guard-data-deletion.sh|onfeat|2|uv run python -m garmin_mcp.scripts.regenerate_duckdb --delete-db"
  "guard-data-deletion.sh|onfeat|0|CONFIRM_DELETE=1 rm -rf data/x"
  "guard-data-deletion.sh|onfeat|0|rm /tmp/x"
  "guard-data-deletion.sh|onfeat|0|ls data/"
  # test_guard_push
  "guard-push.sh|onfeat|2|git push --force"
  "guard-push.sh|onfeat|2|git push -f origin feat/x"
  "guard-push.sh|onfeat|0|git push --force-with-lease"
  "guard-push.sh|onfeat|2|git push origin main"
  "guard-push.sh|onfeat|2|git push origin HEAD:master"
  "guard-push.sh|onfeat|0|git -C $tmp/onfeat push -u origin feat/x"
  "guard-push.sh|onfeat|0|ALLOW_PUSH=1 git push --force"
  "guard-push.sh|onfeat|0|git fetch origin main"
)

for c in "${cases[@]}"; do
  IFS='|' read -r hook cwd expected cmd <<<"$c"
  got="$(run_hook "$hook" "$tmp/$cwd" "$cmd")"
  if [ "$got" = "$expected" ]; then
    echo "  ok: $hook [$cwd] exit $expected: $cmd"
  else
    fail "$hook [$cwd] '$cmd': expected exit $expected, got $got"
  fi
done

# test_settings_has_no_readonly_hook — the auto-approve hook is gone (#1048)
if grep -q 'readonly-auto-approve' "$ROOT/.claude/settings.json"; then
  fail "test_settings_has_no_readonly_hook: settings.json still wires readonly-auto-approve"
elif [ -e "$HOOKS/readonly-auto-approve.sh" ]; then
  fail "test_settings_has_no_readonly_hook: hook file still exists"
else
  echo "  ok: test_settings_has_no_readonly_hook"
fi

# test_settings_wires_every_guard_hook — each guard tested above is actually installed
for hook in block-commit-on-main guard-no-verify guard-data-deletion guard-push; do
  if grep -q "hooks/$hook.sh" "$ROOT/.claude/settings.json"; then
    echo "  ok: test_settings_wires_every_guard_hook: $hook"
  else
    fail "test_settings_wires_every_guard_hook: $hook not in settings.json"
  fi
done

if [ "$failures" -ne 0 ]; then
  echo "test-guard-hooks: $failures failure(s)" >&2
  exit 1
fi
echo "All guard-hook tests passed"
