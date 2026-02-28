#!/bin/bash
# analysis/ ワークスペース用 MCP server 起動
# .env の環境変数でサーバーコード・データパスを制御
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ANALYSIS_DIR="$(cd "$SCRIPT_DIR/../analysis" && pwd)"

# .env 読み込み
if [[ -f "$ANALYSIS_DIR/.env" ]]; then
  set -a; source "$ANALYSIS_DIR/.env"; set +a
fi

SERVER_DIR="${GARMIN_MCP_SERVER_DIR:-../packages/garmin-mcp-server}"
# 相対パスを analysis/ 基準で解決
if [[ ! "$SERVER_DIR" = /* ]]; then
  SERVER_DIR="$(cd "$ANALYSIS_DIR/$SERVER_DIR" && pwd)"
fi

exec uv run --directory "$SERVER_DIR" garmin-mcp-server
