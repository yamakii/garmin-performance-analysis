#!/bin/bash
# `git commit --no-verify`（短縮形 -n を含む）をブロックする。
# pre-commit を迂回すると CI (whole-package black --check . / mypy . /
# pytest -m "unit or integration") で落ちる実績があるため、明示 ack
# (CI_CHECKED=1) なしの --no-verify を止める。
# クォート内（commit メッセージ）は判定前に潰し、git -C <path> / -c <k=v> の形も検知する（#1304）。

set -euo pipefail
input=$(cat)
command=$(echo "$input" | python3 -c "
import sys, json
print(json.load(sys.stdin).get('tool_input',{}).get('command',''))
" 2>/dev/null) || exit 0

[ -z "$command" ] && exit 0

# CI_CHECKED=1 による明示 ack があれば通す（避難経路）
echo "$command" | grep -q "CI_CHECKED=1" && exit 0

stripped=$(echo "$command" | sed -E "s/'[^']*'/Q/g; s/\"[^\"]*\"/Q/g")

# git commit セグメントだけを見る
segments=$(echo "$stripped" | grep -oE 'git( +-[Cc] +[^ ]+)* +commit[^&|;]*' || true)
[ -z "$segments" ] && exit 0

# --no-verify、または -n を含む短縮オプション束（-n / -nm 等）
echo "$segments" | grep -Eq -- '(--no-verify|[[:space:]]-[a-zA-Z]*n[a-zA-Z]*([[:space:]]|$))' || exit 0

echo "BLOCKED: --no-verify / -n は pre-commit を迂回します。CI は whole-package で black --check . / mypy . / pytest -m \"unit or integration\" を回します。" >&2
echo "まず scripts/ci-check.sh を実行し、pass を確認してから: CI_CHECKED=1 git commit --no-verify ..." >&2
exit 2
