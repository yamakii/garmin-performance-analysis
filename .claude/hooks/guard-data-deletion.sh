#!/bin/bash
# 不可逆データ削除をブロックする。
# data/ ・ result/ ・ *.duckdb は git 未管理で復元不可（dev-reference §7 / analysis-standards §5）。
# DB 削除フラグ (--delete-db) と sensitive path への rm を明示 ack なしで止める。

set -euo pipefail
input=$(cat)
command=$(echo "$input" | python3 -c "
import sys, json
print(json.load(sys.stdin).get('tool_input',{}).get('command',''))
" 2>/dev/null) || exit 0

[ -z "$command" ] && exit 0

# CONFIRM_DELETE=1 による明示 ack があれば通す（避難経路）
echo "$command" | grep -q "CONFIRM_DELETE=1" && exit 0

danger=0

# --delete-db フラグを含む → 危険
echo "$command" | grep -q -- "--delete-db" && danger=1

# rm を含み、かつ対象に sensitive path を含む → 危険
if echo "$command" | grep -Eq '\brm\b'; then
  if echo "$command" | grep -Eq '\.duckdb' \
    || echo "$command" | grep -Eq 'garmin_data' \
    || echo "$command" | grep -Eq '(^|[[:space:]]|/|=|\./)(data|result)/'; then
    danger=1
  fi
fi

[ "$danger" -eq 0 ] && exit 0

echo "BLOCKED: data/・result/・*.duckdb は git 未管理で復元不可です（dev-reference §7 / analysis-standards §5）。" >&2
echo "ls -la で中身を確認しユーザー確認の上、CONFIRM_DELETE=1 を付けて再実行してください: CONFIRM_DELETE=1 <元コマンド>" >&2
exit 2
