#!/bin/bash
# mainブランチでのgit commitをブロック

set -euo pipefail
input=$(cat)
command=$(echo "$input" | python3 -c "
import sys, json
print(json.load(sys.stdin).get('tool_input',{}).get('command',''))
" 2>/dev/null) || exit 0

[ -z "$command" ] && exit 0

# git commit以外は通す
echo "$command" | grep -q "^git commit" || exit 0

# mainブランチかチェック
branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null) || exit 0
[ "$branch" != "main" ] && [ "$branch" != "master" ] && exit 0

# .claude/ 配下のみの変更は例外として許可
staged=$(git diff --cached --name-only 2>/dev/null)
[ -z "$staged" ] && { echo "BLOCKED: mainブランチへの直接コミットは禁止です" >&2; exit 2; }
non_claude=$(echo "$staged" | grep -v "^\.claude/" || true)
[ -z "$non_claude" ] && exit 0

# mainブランチでのcommit → ブロック
echo "BLOCKED: mainブランチへの直接コミットは禁止です" >&2
echo "worktreeを作成してください: git worktree add -b feature/name ../garmin-name main" >&2
exit 2
