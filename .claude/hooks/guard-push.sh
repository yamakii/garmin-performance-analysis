#!/bin/bash
# 危険な push をブロックする。
# force push と main/master への直接 push を明示 ack なしで止める（git.md §1: push 済み履歴は書き換えない）。
# CWD のブランチ判定はしない（git -C <worktree> push を誤爆させないため、
# command 文字列の ref トークンのみで判定する）。
# クォート内（commit メッセージ・sed 式・credential.helper の中身）は判定前に潰す。
# git のグローバルオプション -C <path> / -c <k=v> を挟んだ正典 push 形も検知する（#1304）。

set -euo pipefail
input=$(cat)
command=$(echo "$input" | python3 -c "
import sys, json
print(json.load(sys.stdin).get('tool_input',{}).get('command',''))
" 2>/dev/null) || exit 0

[ -z "$command" ] && exit 0

# ALLOW_PUSH=1 による明示 ack があれば通す（避難経路）
echo "$command" | grep -q "ALLOW_PUSH=1" && exit 0

# クォート文字列を潰し、git push セグメントだけを取り出す
stripped=$(echo "$command" | sed -E "s/'[^']*'/Q/g; s/\"[^\"]*\"/Q/g")
segments=$(echo "$stripped" | grep -oE 'git( +-[Cc] +[^ ]+)* +push[^&|;]*' || true)
[ -z "$segments" ] && exit 0

# force push 判定（--force-with-lease は除外）
has_force=0
if echo "$segments" | grep -Eq '(--force([[:space:]]|$)|[[:space:]]-f([[:space:]]|$)|[[:space:]]\+[^ ]+)'; then
  has_force=1
fi
echo "$segments" | grep -q -- "--force-with-lease" && has_force=0

if [ "$has_force" -eq 1 ]; then
  echo "BLOCKED: force push は禁止です（git.md §1: push 済みの履歴は書き換えない）。" >&2
  echo "コンフリクトは git.md §2 の merge 取り込み → 通常 push で解消してください。意図的なら: ALLOW_PUSH=1 <元コマンド>" >&2
  exit 2
fi

# main/master への明示 push（ref トークン）
if echo "$segments" | grep -Eq '(\bmain\b|\bmaster\b)'; then
  echo "BLOCKED: main/master への直接 push は禁止です。worktree + PR 経由にしてください。" >&2
  echo "意図的なら: ALLOW_PUSH=1 <元コマンド>" >&2
  exit 2
fi

exit 0
