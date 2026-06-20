#!/bin/bash
# mainブランチでのgit commitをブロック

set -euo pipefail
input=$(cat)
command=$(echo "$input" | python3 -c "
import sys, json
print(json.load(sys.stdin).get('tool_input',{}).get('command',''))
" 2>/dev/null) || exit 0

[ -z "$command" ] && exit 0

# git commit以外は通す（git -C <path> commit 形式も検知）
echo "$command" | grep -Eq 'git( +-C +[^ ]+)? +commit' || exit 0

# command から -C <path> を抽出（あればターゲットの worktree を見る）
cpath=$(echo "$command" | grep -oE 'git +-C +[^ ]+' | head -1 | sed -E 's/.*-C +//')

# ターゲットブランチを解決（-C があればそのパス、なければ CWD）
if [ -n "$cpath" ]; then
  branch=$(git -C "$cpath" rev-parse --abbrev-ref HEAD 2>/dev/null) || exit 0
else
  branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null) || exit 0
fi
[ "$branch" != "main" ] && [ "$branch" != "master" ] && exit 0

# mainブランチでのcommit → ブロック（branch protection により全変更がPR必須）
echo "BLOCKED: mainブランチへの直接コミットは禁止です" >&2
echo "worktreeを作成してください: git worktree add -b feature/name ../garmin-name main" >&2
exit 2
