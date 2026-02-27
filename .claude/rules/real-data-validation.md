# Real Data Validation Rules

## CRITICAL: Unit tests alone are NOT sufficient. Validate with real data.

## When to Validate

- Training plan → `get_current_fitness_summary()` で妥当性確認
- DuckDB schema変更 → `PRAGMA table_info` + 実データ型確認
- MCP tool変更 → 実activity_idで呼び出し、`statistics_only=True/False` 両方テスト
- Ingest pipeline変更 → 実activity 1件でend-to-end
- Agent definition変更 → mainマージ → 新セッション → `/analyze-activity YYYY-MM-DD` で検証

## MCP Server Restart (コード変更後)

```
mcp__garmin-db__reload_server()                          # main
mcp__garmin-db__reload_server(server_dir="/path/to/wt")  # worktree
mcp__serena__activate_project()                          # Serena再activate
```

再起動前の検証結果は信用しない。Stale server state causes false negatives.

## How to Validate

MCP toolsを直接呼び出して検証（スクリプト不要）:
1. `get_activity_by_date()` で実IDを取得
2. 変更対象のtoolを実IDで呼び出し
3. 結果をユーザーに提示
