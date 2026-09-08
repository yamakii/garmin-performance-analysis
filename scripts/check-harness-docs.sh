#!/usr/bin/env bash
# Stale-phrase guard for the harness docs (#1045).
#
# Rule text is duplicated across rules / skills / agent defs and drifts; each
# phrase below names a procedure that was retired and must not be re-described
# anywhere. Add a line to BANNED when you retire a procedure; delete a line only
# together with the procedure coming back.
#
# Usage: scripts/check-harness-docs.sh [root]   (default: repo root)
# exit 0 = clean, 1 = a banned phrase is present (offending lines on stdout).
set -uo pipefail

ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

# Fixed strings (grep -F). Keep each on its own line; comments are not allowed
# inside the block because the block is fed to grep verbatim.
BANNED='/tmp/validation_queue
一時適用
Co-Authored-By: Claude <noreply
merge --no-ff feature/
dev-reference.md §3
dev-reference.md` §3
implementation-workflow.md` Phase 3
implementation-workflow.md` Phase 2
単発だから手動
単発 Issue でも既定で
単発 Issue / Epic を問わず
Issue なし実装は禁止'

targets=()
for p in .claude/rules .claude/skills .claude/agents CLAUDE.md; do
  [ -e "$ROOT/$p" ] && targets+=("$ROOT/$p")
done
[ "${#targets[@]}" -gt 0 ] || exit 0

hits="$(grep -rnF --include='*.md' -f <(printf '%s\n' "$BANNED") "${targets[@]}" 2>/dev/null || true)"
if [ -n "$hits" ]; then
  echo "check-harness-docs: retired procedure text found (see scripts/check-harness-docs.sh BANNED):" >&2
  echo "$hits"
  exit 1
fi
exit 0
