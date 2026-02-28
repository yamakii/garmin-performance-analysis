# Worktree Validation Protocol

## Overview

worktree 実装後の検証を `analysis/` ワークスペースで実行する。
analysis/ は独自の MCP server プロセスを持つため、reload_server による切り替え不要。

## Validation Levels

| Level | 名称 | 内容 | コスト |
|-------|------|------|--------|
| L1 | MCP check | analysis/ で MCP tool 呼び出し → 値の妥当性 | ~20K tokens |
| L2 | Integration | L1 + worktree 内で `uv run pytest -m integration` | ~30K tokens |
| L3 | Full E2E | analysis/ で `/analyze-activity` 実行 + 検証基準チェック | ~150K tokens |

計画時に `e2e-verification.md` のガイドラインを参照してレベルを決定する。

## 検証フロー

```
1. worktree で実装 + unit/integration テスト pass
2. analysis/.env を編集:
     GARMIN_MCP_SERVER_DIR=/path/to/worktree/packages/garmin-mcp-server
3. fixture DB 生成（必要な場合）:
     GARMIN_DATA_DIR=analysis/data uv run python -m garmin_mcp.scripts.regenerate_duckdb \
       --activity-ids 12345678901 --force
4. E2E 検証:
     cd analysis/ && claude -p "/analyze-activity 2025-10-09"
5. 結果の pass/fail 判定
6. PR 作成
```

## L1: MCP Check

1. `analysis/.env` に worktree の `GARMIN_MCP_SERVER_DIR` を設定
2. `cd analysis/ && claude` で起動
3. `mcp__garmin-db__get_server_info()` で server_dir が worktree を指すことを確認
4. 変更の影響を受ける MCP tool を `verification_activity_id` で呼び出す
5. 結果の妥当性チェック:
   - 返却値が非 null
   - 期待される型・構造と一致
   - 値が妥当な範囲内（ペース 3:00-9:00/km、HR 80-200 bpm 等）

## L2: Integration

1-5. L1 と同じ
6. Worktree ディレクトリで integration テスト実行:
   ```bash
   cd {worktree_path} && uv run pytest -m integration --tb=short -q
   ```
7. テスト結果の判定:
   - 全 pass → L2 pass
   - 失敗あり → 失敗テスト名とエラー内容を記録、L2 fail

## L3: Full E2E

1. `analysis/.env` に worktree パスを設定
2. `cd analysis/ && claude -p "/analyze-activity 2025-10-09"` を実行
3. `e2e-verification.md` の検証基準でチェック

## 判定基準

- **構造チェック失敗**: FAIL（致命的）— PR にブロッキングコメント
- **内容チェック失敗**: WARNING — PR にコメント記載、マージ判断はユーザーに委ねる
- **テスト失敗 (L2)**: FAIL — 失敗テストの詳細を PR コメントに記載

## Skip 条件

`validation_level` 未指定かつ変更が `.claude/rules/`, `docs/`, `CLAUDE.md` のみの場合、検証スキップ。
