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
  # test_guard_push_global_options (#1304): the canonical -c credential.helper form
  "guard-push.sh|onfeat|2|git -C $tmp/onfeat -c credential.helper='!f(){ echo x; };f' push -q -u origin main"
  "guard-push.sh|onfeat|2|git -C $tmp/onfeat -c credential.helper='!f(){ echo x; };f' push --force origin feat/x"
  "guard-push.sh|onfeat|2|git push origin +feat/x"
  "guard-push.sh|onfeat|0|git -C $tmp/onfeat -c credential.helper='!f(){ echo x; };f' push -q -u origin feat/x"
  # test_guard_push_ignores_quoted_text (#1304): sed / commit text mentioning git push main
  "guard-push.sh|onfeat|0|sed -i 's#git push origin main#x#' f.md"
  "guard-push.sh|onfeat|0|git commit -m 'never git push --force to main'"
  # test_block_commit_global_options (#1304)
  "block-commit-on-main.sh|onfeat|2|git -C $tmp/onmain -c user.name=x commit -m x"
  "block-commit-on-main.sh|onmain|0|echo 'git commit' > notes.txt"
  # test_guard_no_verify_short_flag (#1304)
  "guard-no-verify.sh|onfeat|2|git commit -n -m x"
  "guard-no-verify.sh|onfeat|2|git commit -nm x"
  "guard-no-verify.sh|onfeat|0|git commit -m 'add -n option'"
  "guard-no-verify.sh|onfeat|0|git commit -am x"
  # test_guard_bare_python (#1302)
  "guard-bare-python.sh|onfeat|2|python3 x.py"
  "guard-bare-python.sh|onfeat|2|python -c 1"
  "guard-bare-python.sh|onfeat|2|python3.12 x.py"
  "guard-bare-python.sh|onfeat|2|cd /x && python3 y.py"
  "guard-bare-python.sh|onfeat|2|FOO=1 python3 y.py"
  "guard-bare-python.sh|onfeat|2|echo a | python3 -c z"
  "guard-bare-python.sh|onfeat|2|.venv/bin/python x.py"
  "guard-bare-python.sh|onfeat|0|uv run python x.py"
  "guard-bare-python.sh|onfeat|0|uv run --directory /w python -m m"
  "guard-bare-python.sh|onfeat|0|grep python3 f"
  "guard-bare-python.sh|onfeat|0|git commit -m python3-fix"
  "guard-bare-python.sh|onfeat|0|ls pythonic"
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
for hook in block-commit-on-main guard-no-verify guard-data-deletion guard-push guard-bare-python; do
  if grep -q "hooks/$hook.sh" "$ROOT/.claude/settings.json"; then
    echo "  ok: test_settings_wires_every_guard_hook: $hook"
  else
    fail "test_settings_wires_every_guard_hook: $hook not in settings.json"
  fi
done

# test_git_quiet_config_sets_merge_stat (#1307) — SessionStart hook silences merge diffstats
CLAUDE_PROJECT_DIR="$tmp/onfeat" bash "$HOOKS/git-quiet-config.sh"
rc=$?
got="$(git -C "$tmp/onfeat" config --get merge.stat || true)"
if [ "$rc" -eq 0 ] && [ "$got" = "false" ]; then
  echo "  ok: test_git_quiet_config_sets_merge_stat"
else
  fail "test_git_quiet_config_sets_merge_stat: exit $rc, merge.stat='$got'"
fi
mkdir -p "$tmp/norepo"
if CLAUDE_PROJECT_DIR="$tmp/norepo" GIT_CEILING_DIRECTORIES="$tmp" bash "$HOOKS/git-quiet-config.sh"; then
  echo "  ok: test_git_quiet_config_noop_outside_repo"
else
  fail "test_git_quiet_config_noop_outside_repo: non-zero exit"
fi
if grep -q '"SessionStart"' "$ROOT/.claude/settings.json" && grep -q 'hooks/git-quiet-config.sh' "$ROOT/.claude/settings.json"; then
  echo "  ok: test_settings_wires_git_quiet_config"
else
  fail "test_settings_wires_git_quiet_config: SessionStart hook not in settings.json"
fi

if [ "$failures" -ne 0 ]; then
  echo "test-guard-hooks: $failures failure(s)" >&2
  exit 1
fi
echo "All guard-hook tests passed"
