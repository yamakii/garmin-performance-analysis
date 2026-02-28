# E2E Verification Rules

## 検証基準

### 構造チェック（FAIL = 致命的）

- 各セクション (split, phase, efficiency, environment, summary) の `analysis_data` が非 null
- 必須フィールドが存在（section_type ごとに定義）
- レポート Markdown が生成される

### 内容チェック（FAIL = 警告、理由を PR コメントに記載）

- ペース値が fixture と整合（5:15-5:45/km 範囲の activity に対して 3:00/km 等の異常値がないか）
- HR 値が fixture と整合（130-165 bpm 範囲）
- セクション間で矛盾がないか（efficiency が「優秀」なのに summary が「要改善」等）

### スキップ条件

分析エージェント (`.claude/agents/*-analyst.md`)、Handler (`src/garmin_mcp/handlers/`)、Reader (`src/garmin_mcp/database/readers/`)、Report (`src/garmin_mcp/reporting/`) のいずれにも変更がない場合はスキップ。

## Verification Activity

- **Activity ID**: `12345678901`
- **Date**: `2025-10-09`
- **Type**: Easy run (7km, 5:15-5:45/km)
- **Fixture Location**: `tests/fixtures/data/raw/activity/12345678901/`
