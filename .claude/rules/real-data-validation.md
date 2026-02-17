# Real Data Validation Rules

## CRITICAL: Unit tests alone are NOT sufficient. Validate with real data before presenting results.

## When to Validate

実データ検証が必要なケース:
- Training plan生成/修正 → 実際のfitness summaryで出力値の妥当性確認
- DuckDB schema変更/migration → 実テーブルでPRAGMA table_info確認
- MCP tool変更 → 実activity_idで呼び出して戻り値の型・構造確認
- Ingest pipeline変更 → 実activity 1件でend-to-end実行

## Validation Checklist

### Training Plan
1. `get_current_fitness_summary()` で現在の走行量を確認
2. 生成されたプランの初週volume ≤ 現在volume × 1.1 を検証
3. 日付が正しい曜日に割り当てられているか確認
4. HR zone targetがGarmin native zones内に収まっているか確認

### DuckDB Operations
1. 変更後に `PRAGMA table_info(table_name)` でカラム型を確認
2. `SELECT typeof(column) FROM table LIMIT 1` で実際の型を確認
3. datetime.date vs string 等の型ミスマッチを実データで検出
4. NULL値の有無を `SELECT COUNT(*) WHERE column IS NULL` で確認

### MCP Tool Changes
1. 変更したtoolを実activity_idで呼び出す
2. 戻り値のJSON構造とフィールド型を確認
3. statistics_only=True/False 両方のモードでテスト
4. エッジケース: 短いアクティビティ(3km未満), インターバル, リカバリーラン

### After Code Changes
1. Restart MCP servers before verifying changes through MCP tools
2. Stale MCP server state causes false negatives — fixes may appear broken when server just hasn't reloaded
3. Verify with real data AFTER restart

## How to Validate

MCP toolsを直接呼び出して検証する（スクリプト不要）:
- `mcp__garmin-db__get_activity_by_date()` で実IDを取得
- 変更対象のtoolを実IDで呼び出し
- 結果をユーザーに提示して確認を求める
