#!/usr/bin/env bash
# Skip-level docs/rules changes may ship without an Issue (#1051). The rule must
# state the exception, and no rule may still say the unqualified 「Issue なし実装は禁止」.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
failures=0
fail() { echo "  FAIL: $*" >&2; failures=$((failures + 1)); }

# test_prohibited_list_has_skip_exception
if grep -q 'skip レベルの例外' "$ROOT/.claude/rules/dev/dev-reference.md" \
   && grep -q 'skip レベルで省略できるのは Issue だけ' "$ROOT/.claude/rules/dev/dev-reference.md"; then
  echo "  ok: test_prohibited_list_has_skip_exception: dev-reference states the exception"
else
  fail "test_prohibited_list_has_skip_exception: dev-reference.md lacks the skip-level exception"
fi

hits="$(grep -rn 'Issue なし実装は禁止' "$ROOT/.claude/rules" "$ROOT/CLAUDE.md" 2>/dev/null || true)"
if [ -z "$hits" ]; then
  echo "  ok: test_prohibited_list_has_skip_exception: no unqualified ban remains"
else
  fail "test_prohibited_list_has_skip_exception: unqualified ban still present: $hits"
fi

if [ "$failures" -ne 0 ]; then
  echo "test-skip-level-issue-exception: $failures failure(s)" >&2
  exit 1
fi
echo "All skip-level-issue-exception tests passed"
