#!/usr/bin/env bash
# The sandbox freeze policy (#1050) must be stated in the rule Claude sessions
# load, the human runbook, and the docker/ README, so a future sandbox change
# meets it wherever the author starts reading.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
failures=0

# test_docs_mention_sandbox_freeze
for f in .claude/rules/dev/maintenance-policy.md docs/maintenance.md docker/README.md; do
  if grep -q 'Sandbox freeze\|Frozen (#1050)' "$ROOT/$f"; then
    echo "  ok: test_docs_mention_sandbox_freeze: $f"
  else
    echo "  FAIL: test_docs_mention_sandbox_freeze: $f lacks the freeze section" >&2
    failures=$((failures + 1))
  fi
done

if [ "$failures" -ne 0 ]; then
  echo "test-sandbox-freeze-docs: $failures failure(s)" >&2
  exit 1
fi
echo "All sandbox-freeze-docs tests passed"
