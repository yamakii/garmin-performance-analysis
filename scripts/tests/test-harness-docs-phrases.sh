#!/usr/bin/env bash
# Self-test for scripts/check-harness-docs.sh (#1045). Hermetic: builds temp
# trees, never touches the real .claude/.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GUARD="$HERE/../check-harness-docs.sh"
ROOT="$(cd "$HERE/../.." && pwd)"
fail=0

check() { # name expected_exit actual_exit
  if [ "$2" -eq "$3" ]; then
    echo "  ok   $1"
  else
    echo "  FAIL $1 (expected exit $2, got $3)" >&2
    fail=1
  fi
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# test_phrase_guard_fails_on_stale_phrase
mkdir -p "$tmp/stale/.claude/rules"
printf 'L3 は worktree の .md を main に一時適用して検証する\n' >"$tmp/stale/.claude/rules/x.md"
bash "$GUARD" "$tmp/stale" >/dev/null 2>&1
check test_phrase_guard_fails_on_stale_phrase 1 $?

# test_phrase_guard_passes_clean_tree
mkdir -p "$tmp/clean/.claude/rules" "$tmp/clean/.claude/skills/s"
printf 'manifest は構造化出力で返す\n' >"$tmp/clean/.claude/rules/x.md"
printf 'Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>\n' >"$tmp/clean/.claude/skills/s/SKILL.md"
bash "$GUARD" "$tmp/clean" >/dev/null 2>&1
check test_phrase_guard_passes_clean_tree 0 $?

# test_phrase_guard_ignores_non_md
mkdir -p "$tmp/nonmd/.claude/hooks"
printf '/tmp/validation_queue\n' >"$tmp/nonmd/.claude/hooks/x.sh"
bash "$GUARD" "$tmp/nonmd" >/dev/null 2>&1
check test_phrase_guard_ignores_non_md 0 $?

# test_real_tree_is_clean
bash "$GUARD" "$ROOT" >/dev/null 2>&1
check test_real_tree_is_clean 0 $?

if [ "$fail" -ne 0 ]; then
  echo "test-harness-docs-phrases: FAILED" >&2
  exit 1
fi
echo "test-harness-docs-phrases: all passed"
