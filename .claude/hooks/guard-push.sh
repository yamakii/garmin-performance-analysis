#!/bin/bash
# 危険な push をブロックする。
# force push と main/master への直接 push を明示 ack なしで止める（dev-reference §7）。
# CWD のブランチ判定はしない（git -C <worktree> push を誤爆させないため、
# command 文字列の ref トークンのみで判定する）。

set -euo pipefail
input=$(cat)
command=$(echo "$input" | python3 -c "
import sys, json
print(json.load(sys.stdin).get('tool_input',{}).get('command',''))
" 2>/dev/null) || exit 0

[ -z "$command" ] && exit 0

# ALLOW_PUSH=1 による明示 ack があれば通す（避難経路）
echo "$command" | grep -q "ALLOW_PUSH=1" && exit 0

# git push を含まないなら通す（git -C <path> push 形式も検知）
echo "$command" | grep -Eq 'git( +-C +[^ ]+)? +push' || exit 0

# force push 判定（--force-with-lease は除外）
has_force=0
if echo "$command" | grep -Eq '(--force|[[:space:]]-f([[:space:]]|$))'; then
  has_force=1
fi
echo "$command" | grep -q -- "--force-with-lease" && has_force=0

if [ "$has_force" -eq 1 ]; then
  echo "BLOCKED: force push は禁止です（dev-reference §7）。--force-with-lease を使うか rebase 後の通常 push を検討してください。" >&2
  echo "意図的なら: ALLOW_PUSH=1 <元コマンド>" >&2
  exit 2
fi

# main/master への明示 push（ref トークン）
if echo "$command" | grep -Eq 'git( +-C +[^ ]+)? +push[^&|;]*(\bmain\b|\bmaster\b)'; then
  echo "BLOCKED: main/master への直接 push は禁止です。worktree + PR 経由にしてください。" >&2
  echo "意図的なら: ALLOW_PUSH=1 <元コマンド>" >&2
  exit 2
fi

exit 0
