#!/bin/bash
# `git commit --no-verify` をブロックする。
# pre-commit を迂回すると CI (whole-package black --check . / mypy . / pytest -m unit)
# で落ちる実績があるため、明示 ack (CI_CHECKED=1) なしの --no-verify を止める。

set -euo pipefail
input=$(cat)
command=$(echo "$input" | python3 -c "
import sys, json
print(json.load(sys.stdin).get('tool_input',{}).get('command',''))
" 2>/dev/null) || exit 0

[ -z "$command" ] && exit 0

# git commit 以外は通す
echo "$command" | grep -q "git commit" || exit 0

# --no-verify を含まないなら通す
echo "$command" | grep -q -- "--no-verify" || exit 0

# CI_CHECKED=1 による明示 ack があれば通す（避難経路）
echo "$command" | grep -q "CI_CHECKED=1" && exit 0

# --no-verify だが ack なし → ブロック
echo "BLOCKED: --no-verify は pre-commit を迂回します。CI は whole-package で black --check . / mypy . / pytest -m unit を回します。" >&2
echo "まず scripts/ci-check.sh を実行し、pass を確認してから: CI_CHECKED=1 git commit --no-verify ..." >&2
exit 2
