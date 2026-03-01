# Worktree Validation Protocol

## Overview

並行 worktree 実装エージェントの検証を FIFO キューで逐次処理する。
MCP server は単一プロセスのため、検証は直列実行が必須。

## Architecture

```
Main Session (queue manager — 検証作業はしない)
│
├─ Implementation Agent A (background, worktree) ──完了──┐
├─ Implementation Agent B (background, worktree) ──完了──┤
└─ Implementation Agent C (background, worktree) ──完了──┘
                                                         │
                                          FIFO 順 ◄──────┘
                  Validation Agent #1 (foreground) → A 検証
                  Validation Agent #2 (foreground) → B 検証
                  Validation Agent #3 (foreground) → C 検証
```

## Validation Levels

| Level | 名称 | 内容 | コスト |
|-------|------|------|--------|
| L1 | MCP check | reload_server → MCP tool 呼び出し → 値の妥当性 | ~20K tokens |
| L2 | Integration | L1 + worktree 内で `uv run pytest -m integration` | ~30K tokens |
| L3 | Full E2E | `/analyze-activity` を worktree 上で実行 + 検証基準チェック | ~150K tokens |

レベル判定は `dev-reference.md` §3 の Validation Level 判定表を参照。

## Implementation Agent の責務

1. Worktree で実装 + unit/integration テスト pass
2. Validation manifest を書き出し:
   ```
   /tmp/validation_queue/<branch-name>.json
   ```
   ```json
   {
     "branch": "feature/xxx",
     "worktree_path": "/absolute/path/to/worktree",
     "server_dir": "/absolute/path/to/worktree/packages/garmin-mcp-server",
     "pr_number": 123,
     "issue_number": 72,
     "validation_level": "L1|L2|L3",
     "change_category": "handler|reader|agent|reporting|ingest|schema|other",
     "changed_files": ["src/garmin_mcp/handlers/foo.py"],
     "test_results": {"unit": "pass", "integration": "pass"},
     "verification_activity_id": 20636804823
   }
   ```
3. PR 作成 (draft)

## Main Session の責務 (Queue Manager)

- 完了通知を受信したら Validation Agent を **foreground** で起動（毎回新規）
- Validation Agent の結果に応じて:
  - **pass**: PR を ready にする / `/ship` 候補としてユーザーに報告
  - **fail**: PR にコメント追記、修正指示
- 検証作業は一切しない（委譲のみ）

## Validation Agent の責務

毎回独立起動。前回の検証コンテキストは持たない。
manifest の `validation_level` に応じた手順を実行する。

### L1: MCP Check

1. Manifest 読み込み (`/tmp/validation_queue/<branch>.json`)
2. `mcp__garmin-db__reload_server(server_dir=worktree_server_dir)` で worktree に切替
3. Health check: `mcp__garmin-db__get_server_info()` で server_dir が worktree を指すことを確認
4. `changed_files` から影響を受ける MCP tool を特定し、`verification_activity_id` で呼び出す
5. 結果の妥当性チェック:
   - 返却値が非 null
   - 期待される型・構造と一致
   - 値が妥当な範囲内（ペース 3:00-9:00/km、HR 80-200 bpm 等）
6. `mcp__garmin-db__reload_server()` で main 復帰
7. pass/fail + 詳細を返却
8. Manifest ファイルを削除

### L2: Integration

1-3. L1 と同じ（reload_server + health check）
4. L1 の MCP check を実行（上記 4-5）
5. Worktree ディレクトリで integration テスト実行:
   ```bash
   cd {worktree_path} && uv run pytest -m integration --tb=short -q
   ```
6. テスト結果の判定:
   - 全 pass → L2 pass
   - 失敗あり → 失敗テスト名とエラー内容を記録、L2 fail
7. `mcp__garmin-db__reload_server()` で main 復帰
8. pass/fail + 詳細を返却
9. Manifest ファイルを削除

### L3: Full E2E

1-3. L1 と同じ（reload_server + health check）
4. `/analyze-activity {fixture_date}` を実行（analyze-activity.md が Single Source of Truth）
   - temp ディレクトリパスは analyze-activity.md の ANALYSIS_TEMP_DIR 定義に従う（timestamp 付きユニークパス）
   - Fixture: `dev-reference.md` §3 の L3 検証基準を参照
5. 検証基準チェック（`dev-reference.md` §3 の L3 検証基準）:
   - **構造チェック**: 5 セクションの `analysis_data` が非 null、必須フィールド存在
   - **内容チェック**: ペース・HR 値が fixture 範囲と整合、セクション間矛盾なし
6. (任意) DuckDB 挿入検証: `insert_section_analysis_dict` で各セクション挿入成功を確認
7. (任意) レポート生成検証: Markdown レポート生成 + 5セクション見出し存在を確認
8. `mcp__garmin-db__reload_server()` で main 復帰
9. pass/fail + 詳細を返却
10. Manifest ファイルを削除

### 判定基準

- **構造チェック失敗**: FAIL（致命的）— PR にブロッキングコメント
- **内容チェック失敗**: WARNING — PR にコメント記載、マージ判断はユーザーに委ねる
- **テスト失敗 (L2)**: FAIL — 失敗テストの詳細を PR コメントに記載

## Skip 条件

`validation_level: skip` は Validation Agent の実行をスキップする。
Issue → Plan → Worktree → PR のワークフローは変わらない。

判定: `validation_level` 未指定かつ変更が `.claude/rules/`, `docs/`, `CLAUDE.md` のみの場合に該当。

## Manifest ディレクトリ

```bash
mkdir -p /tmp/validation_queue
```

検証完了後、manifest ファイルは Validation Agent が削除する。
