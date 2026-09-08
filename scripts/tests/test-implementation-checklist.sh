#!/usr/bin/env bash
# The default implementation path (implementation-workflow.md Phase 1) names
# one command per step. Every `scripts/*.sh` it names must exist and parse, so
# the checklist cannot silently point at a renamed or deleted script (#1046).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
DOC="$ROOT/.claude/rules/dev/implementation-workflow.md"
fail=0

# test_checklist_commands_exist
scripts="$(grep -oE 'scripts/[A-Za-z0-9_./-]+\.sh' "$DOC" | sort -u)"
if [ -z "$scripts" ]; then
  echo "  FAIL test_checklist_commands_exist (no scripts named in $DOC)" >&2
  fail=1
fi
for s in $scripts; do
  if [ -f "$ROOT/$s" ] && bash -n "$ROOT/$s"; then
    echo "  ok   test_checklist_commands_exist: $s"
  else
    echo "  FAIL test_checklist_commands_exist: $s missing or does not parse" >&2
    fail=1
  fi
done

# test_checklist_has_default_path_heading
if grep -q '1 セッション = 1 worktree = 1 PR' "$DOC"; then
  echo "  ok   test_checklist_has_default_path_heading"
else
  echo "  FAIL test_checklist_has_default_path_heading" >&2
  fail=1
fi

if [ "$fail" -ne 0 ]; then
  echo "test-implementation-checklist: FAILED" >&2
  exit 1
fi
echo "test-implementation-checklist: all passed"
