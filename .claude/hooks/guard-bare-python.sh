#!/bin/bash
# 生の `python` / `python3` 実行をブロックし `uv run python` へ誘導する（#1302）。
# 権限レイヤーは理由なしで拒否するため、モデルが python3 の言い換えを繰り返していた。
# ここで理由と正しい形を返し、1 回で `uv run` に切り替えさせる。
# コマンドの各セグメント先頭（行頭 / ; && || | ( の直後、VAR=val や env の後）の
# python・python3・python3.N・<path>/python だけを対象にし、引数中の文字列は通す。

set -euo pipefail
input=$(cat)
command=$(echo "$input" | python3 -c "
import sys, json
print(json.load(sys.stdin).get('tool_input',{}).get('command',''))
" 2>/dev/null) || exit 0

[ -z "$command" ] && exit 0

pattern='(^|[;&|(])[[:space:]]*(env[[:space:]]+)?([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+)*([^[:space:];&|()]*/)?python(3(\.[0-9]+)?)?([[:space:]]|$)'
echo "$command" | grep -Eq "$pattern" || exit 0

echo "BLOCKED: python / python3 を直接実行しない。このリポジトリでは uv 経由で実行する:" >&2
echo "  uv run --directory /workspace python <script.py>   (worktree 内なら --directory <worktree>)" >&2
echo "  uv run --directory <path>/packages/garmin-mcp-server python -m <module>" >&2
exit 2
