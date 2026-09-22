#!/bin/bash
# mainブランチでのgit commitをブロック
# クォート内（commit メッセージ等）は判定前に潰し、git のグローバルオプション
# -C <path> / -c <k=v> を挟んだ形も検知する（#1304）。

set -euo pipefail
input=$(cat)
command=$(echo "$input" | python3 -c "
import sys, json
print(json.load(sys.stdin).get('tool_input',{}).get('command',''))
" 2>/dev/null) || exit 0

[ -z "$command" ] && exit 0

stripped=$(echo "$command" | sed -E "s/'[^']*'/Q/g; s/\"[^\"]*\"/Q/g")

# git commit以外は通す（git -C <path> / -c k=v commit 形式も検知）
segment=$(echo "$stripped" | grep -oE 'git( +-[Cc] +[^ ]+)* +commit' | head -1 || true)
[ -z "$segment" ] && exit 0

# セグメントから -C <path> を抽出（あればターゲットの worktree を見る）
cpath=$(echo "$segment" | grep -oE -- '-C +[^ ]+' | head -1 | sed -E 's/-C +//' || true)

# ターゲットブランチを解決（-C があればそのパス、なければ CWD）
if [ -n "$cpath" ]; then
  branch=$(git -C "$cpath" rev-parse --abbrev-ref HEAD 2>/dev/null) || exit 0
else
  branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null) || exit 0
fi
[ "$branch" != "main" ] && [ "$branch" != "master" ] && exit 0

# mainブランチでのcommit → ブロック（branch protection により全変更がPR必須）
echo "BLOCKED: mainブランチへの直接コミットは禁止です" >&2
echo "worktree を作成してください（.claude/rules/dev/git.md §2）: 背景ジョブは EnterWorktree、対話は git worktree add -q -b <type>/<issue>-<slug> .claude/worktrees/<slug> origin/main" >&2
exit 2
