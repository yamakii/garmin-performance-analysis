# E2E Verification Rules

## Validation Level ガイドライン

計画時（Issue Design 作成時）に以下の表を参照し、変更対象に応じた検証レベルを決定する。

| 変更対象 | Level | 理由 |
|----------|-------|------|
| `.claude/agents/*-analyst.md` | L3 | 分析品質に直結 |
| `src/garmin_mcp/handlers/` | L1 | MCP tool の入出力確認で十分 |
| `src/garmin_mcp/database/readers/` | L1 | 同上 |
| `src/garmin_mcp/reporting/` | L2 | report pipeline は integration test でカバー |
| `src/garmin_mcp/ingest/` | L2 | DB 構造変更は integration test |
| `database/migrations/` | L2 | スキーマ変更 |
| `.claude/rules/`, `docs/`, `CLAUDE.md` | skip | コード変更なし |

**複数カテゴリにまたがる場合**: 最も高いレベルを採用する。
**判断に迷う場合**: L2 を選択する。L3 は agent 定義変更時のみ。

## 検証環境

- **ディレクトリ**: `analysis/`
- **DB**: fixture DB (`analysis/data/database/`)
- **検証コマンド**: `cd analysis/ && claude -p "/analyze-activity 2025-10-09"`
- **Worktree 検証時**: `analysis/.env` の `GARMIN_MCP_SERVER_DIR` を worktree パスに設定

### Fixture DB 生成

```bash
GARMIN_DATA_DIR=analysis/data \
  uv run python -m garmin_mcp.scripts.regenerate_duckdb \
  --activity-ids 12345678901 --force
```

## L3 検証基準

### 構造チェック（FAIL = 致命的）

- 各セクション (split, phase, efficiency, environment, summary) の `analysis_data` が非 null
- 必須フィールドが存在（section_type ごとに定義）
- レポート Markdown が生成される

### 内容チェック（FAIL = 警告、理由を PR コメントに記載）

- ペース値が fixture と整合（5:15-5:45/km 範囲の activity に対して 3:00/km 等の異常値がないか）
- HR 値が fixture と整合（130-165 bpm 範囲）
- セクション間で矛盾がないか（efficiency が「優秀」なのに summary が「要改善」等）

## Verification Activity

- **Activity ID**: `12345678901`
- **Date**: `2025-10-09`
- **Type**: Easy run (7km, 5:15-5:45/km)
- **Fixture Location**: `tests/fixtures/data/raw/activity/12345678901/`
