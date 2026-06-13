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

## reload_server 非依存の原則

検証フローは **`reload_server`（live MCP サーバ再起動）に依存しない**。

- サブエージェント（Validation Agent）は `reload_server` を跨ぐと `mcp__garmin-db__*` を丸ごと失い、内部から復帰できない（spike #243 で実証済み）。
- worktree コードの検証は **インプロセス import（subprocess 経由）** と **subprocess pytest** で行う方が堅牢（実証済み）。
- L1/L2 はサブエージェント（Validation Agent）が subprocess で完結させる。
- L3（agent 定義変更）はメインセッション（オーケストレーター）が worktree の `.md` を main に一時適用して実行する（agent コード ≠ MCP サーバコード）。
- **live MCP サーバコード自体を検証したい稀なケースのみ**、メインセッションが `reload_server` を扱う（後述「例外」節）。サブエージェント内で `reload_server` を呼ぶことは禁止。

## Validation Levels

| Level | 名称 | 内容 | コスト |
|-------|------|------|--------|
| L1 | In-process check | worktree コードを subprocess で import → 下層関数呼び出し → 値の妥当性 | ~20K tokens |
| L2 | Integration | L1 + worktree 内で `uv run pytest -m integration` | ~30K tokens |
| L3 | Full E2E | worktree の agent `.md` を main に一時適用 → `/analyze-activity` 実行 + 検証基準チェック → 復元 | ~150K tokens |

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

- 完了通知を受信したら、validation_level に応じて起動先を選ぶ:
  - **L1 / L2**: Validation Agent を **foreground** で起動（毎回新規）
  - **L3**: メインセッション（オーケストレーター）が**自分で**実行する（後述「L3: Full E2E（メインセッション担当）」）。L3 はサブエージェントに委譲しない
- 検証結果に応じて:
  - **pass**: PR を ready にする / `/ship` 候補としてユーザーに報告
  - **fail**: PR にコメント追記、修正指示
- L1/L2 の検証作業自体はサブエージェントに委譲する（Queue Manager は委譲のみ）。L3 のみメインセッションが直接実行する

## Validation Agent の責務（L1 / L2）

毎回独立起動。前回の検証コンテキストは持たない。
manifest の `validation_level` が L1/L2 のときのみ起動される。**サブエージェントは `reload_server` を呼ばない。**

### L1: In-process Check（reload なし）

1. Manifest 読み込み (`/tmp/validation_queue/<branch>.json`)
2. `changed_files` から「どの下層関数を呼ぶか」を特定:
   - handler 変更 → 委譲先の `GarminDBReader` メソッド（または handler 内関数）
   - reader 変更 → 該当 `GarminDBReader` メソッド
   - script/関数モジュール変更 → 公開関数
   - 不明な場合は変更ファイルを Read してシグネチャを確認
3. worktree コードを subprocess で import し、`verification_activity_id` で呼び出す。`json.dumps`（MCP 境界相当）まで通す:
   ```bash
   uv run --directory <worktree>/packages/garmin-mcp-server python -c \
     "import json; from garmin_mcp.<module> import <func>; print(json.dumps(<func>(<activity_id>), default=str))"
   ```
   reader メソッド例:
   ```bash
   uv run --directory <worktree>/packages/garmin-mcp-server python -c \
     "import json; from garmin_mcp.database.db_reader import GarminDBReader; print(json.dumps(GarminDBReader().get_performance_trends(<activity_id>), default=str))"
   ```
4. 結果の妥当性チェック:
   - 返却値が非 null
   - 期待される型・構造と一致
   - 値が妥当な範囲内（ペース 3:00-9:00/km、HR 80-200 bpm 等）
   - `json.dumps` が例外なく完了（= MCP 境界でシリアライズ可能）
   - subprocess の exit code が 0
5. pass/fail + 詳細を返却

> `reload_server` / health check は使わない。live MCP サーバの状態に一切依存しないため disconnect は発生しない。

### L2: Integration（reload なし）

1. L1（In-process Check）を実行（上記 1-4）
2. Worktree ディレクトリで integration テスト実行:
   ```bash
   uv run --directory <worktree> pytest -m integration --tb=short -q
   ```
3. テスト結果の判定:
   - 全 pass → L2 pass
   - 失敗あり → 失敗テスト名とエラー内容を記録、L2 fail
4. pass/fail + 詳細を返却

> reload_server / health check ステップは存在しない。subprocess 値検証 + subprocess pytest のみ。

## L3: Full E2E（メインセッション担当）

L3（agent 定義 = `*-analyst.md` の変更）は**サブエージェントに委譲せず、メインセッション（オーケストレーター）が直接実行する**。
agent コードは MCP サーバコードではないため `reload_server` は不要。worktree の `.md` を main の `.claude/agents/` に一時適用し、main 側にすでにバンドルされている prefetch 等の MCP tool で `/analyze-activity` を実行すれば足りる。

メインセッションが以下を実行する:

1. **適用**: worktree の対象 `.md`（`changed_files` の `.claude/agents/*-analyst.md`）を main repo の `.claude/agents/` にコピー（上書き）
   ```bash
   cp <worktree>/.claude/agents/<name>-analyst.md <main>/.claude/agents/<name>-analyst.md
   ```
2. **実行**: メインセッションで `/analyze-activity {fixture_date}` を実行（analyze-activity.md が Single Source of Truth）
   - temp ディレクトリパスは analyze-activity.md の ANALYSIS_TEMP_DIR 定義に従う（timestamp 付きユニークパス）
   - Fixture: `dev-reference.md` §3 の L3 検証基準を参照
3. **検証基準チェック**（`dev-reference.md` §3 の L3 検証基準）:
   - **構造チェック**: 5 セクションの `analysis_data` が非 null、必須フィールド存在
   - **内容チェック**: ペース・HR 値が fixture 範囲と整合、セクション間矛盾なし
4. (任意) DuckDB 挿入検証: `insert_section_analysis_dict` で各セクション挿入成功を確認
5. (任意) レポート生成検証: Markdown レポート生成 + 5セクション見出し存在を確認
6. **復元**: 一時適用した `.md` を main の git 管理状態に戻す
   ```bash
   git -C <main> checkout -- .claude/agents/<name>-analyst.md
   ```
7. pass/fail + 詳細を返却

> live MCP サーバ再起動（`reload_server`）は使わない。agent 定義の差し替えはファイルの一時適用→復元で完結する。

## 例外: live MCP サーバコードの検証（メインセッション限定）

MCP サーバコード自体（handler/reader の挙動を live MCP tool 経由で確認したい等）を検証する**稀なケースのみ**、以下をメインセッションが行う。**サブエージェント内で `reload_server` を呼ぶことは禁止**（reload を跨ぐと `mcp__garmin-db__*` を失い復帰不能）。

1. メインセッション（サブエージェント不可）が `mcp__garmin-db__reload_server(server_dir=<worktree>/packages/garmin-mcp-server)` で worktree に切替
2. `mcp__garmin-db__get_server_info()` を **ready になるまでポーリング**し、`server_dir` が worktree を指すことを確認
3. 対象 MCP tool を `verification_activity_id` で呼び出して値を検証
4. `mcp__garmin-db__reload_server()`（引数なし）で main 復帰
5. 通常は L1 の in-process 検証で十分なため、この手順は L1/L2 の代替ではなく追加の確認手段として位置づける

### 判定基準

- **構造チェック失敗**: FAIL（致命的）— PR にブロッキングコメント
- **内容チェック失敗**: WARNING — PR にコメント記載、マージ判断はユーザーに委ねる
- **テスト失敗 (L2)**: FAIL — 失敗テストの詳細を PR コメントに記載
- **subprocess exit code 非0 / import エラー (L1)**: FAIL — エラー内容を PR コメントに記載

## Skip 条件

`validation_level: skip` は Validation Agent の実行をスキップする。
Issue → Plan → Worktree → PR のワークフローは変わらない。

判定: `validation_level` 未指定かつ変更が `.claude/rules/`, `docs/`, `CLAUDE.md` のみの場合に該当。

## Manifest ディレクトリ

パス: `/tmp/validation_queue/`

- Write tool が親ディレクトリを自動作成するため、明示的な `mkdir` は不要
- manifest ファイルは /tmp 内のため OS 再起動で自動消去される（明示的な削除は不要）
