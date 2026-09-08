#!/usr/bin/env bash
# Rules under .claude/rules/dev/ are development-only and must be path-scoped
# (a `paths:` frontmatter block) so analysis / coaching sessions do not load them
# (#1049). The unconditional set (CLAUDE.md + rules without `paths:`) is kept
# under a byte budget so a rule cannot be quietly un-scoped.
#
# Usage: bash scripts/tests/test-rules-frontmatter.sh [root]
set -uo pipefail

ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
BUDGET="${RULES_BUDGET_BYTES:-20480}"
failures=0
fail() { echo "  FAIL: $*" >&2; failures=$((failures + 1)); }

# has_paths FILE → 0 when the file opens with a frontmatter block containing `paths:`
has_paths() {
  awk 'NR==1 && $0!="---" {exit 1}
       NR>1 && $0=="---" {exit (found?0:1)}
       /^paths:/ {found=1}
       END {if (NR==0) exit 1}' "$1"
}

# --- test_all_dev_rules_path_scoped ------------------------------------------
for f in "$ROOT"/.claude/rules/dev/*.md; do
  [ -e "$f" ] || continue
  if has_paths "$f"; then
    echo "  ok: test_all_dev_rules_path_scoped: ${f#"$ROOT"/}"
  else
    fail "test_all_dev_rules_path_scoped: ${f#"$ROOT"/} has no paths: frontmatter"
  fi
done

# negative control: a rule without frontmatter must be detected
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
printf '# Rule\nbody\n' >"$tmp/unscoped.md"
if has_paths "$tmp/unscoped.md"; then
  fail "test_all_dev_rules_path_scoped: negative control passed (detector broken)"
else
  echo "  ok: test_all_dev_rules_path_scoped: negative control detected"
fi

# --- test_always_loaded_size_budget ------------------------------------------
total=0
while IFS= read -r f; do
  [ -n "$f" ] || continue
  if ! has_paths "$f"; then
    total=$((total + $(wc -c <"$f")))
  fi
done < <(find "$ROOT/.claude/rules" -name '*.md' 2>/dev/null; echo "$ROOT/CLAUDE.md")
if [ "$total" -lt "$BUDGET" ]; then
  echo "  ok: test_always_loaded_size_budget: ${total} bytes < ${BUDGET}"
else
  fail "test_always_loaded_size_budget: unconditional rules + CLAUDE.md = ${total} bytes >= ${BUDGET}"
fi

if [ "$failures" -ne 0 ]; then
  echo "test-rules-frontmatter: $failures failure(s)" >&2
  exit 1
fi
echo "All rules-frontmatter tests passed"
