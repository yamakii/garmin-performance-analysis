# Worktree Validation Protocol

## Overview

並行 worktree 実装エージェントの検証を実行する。
L1/L2 検証は worktree コードを **subprocess（`uv run --directory <worktree>`）** で評価する。
subprocess はプロセス分離されており**並列実行が安全**なため、L1/L2 の Validation Agent は**並列起動してよい**。
直列が必須なのは **L3 のみ**（メインセッションが担当し、live MCP サーバの reload を扱う稀ケース）。

> **正本マップ**: 本書は**検証メカニクス（L1/L2/L3 の実行手順）の正本**。**Validation Level 判定表**は `dev-reference.md §3`、**auto-merge ゲート / Ship 手順**は `implementation-workflow.md` Phase 3 を正本とする。各書の再掲は参照用で、矛盾時は各正本を優先する。

> かつては「MCP server は単一プロセスゆえ検証は直列必須」という FIFO 前提があったが、
> これは L1/L2 が `reload_server`（live MCP サーバ再起動）に依存していた時代の制約。
> 現行の L1/L2 は reload を使わず subprocess で完結するため、この前提はもはや当てはまらない。

## Architecture

```
Main Session (validation manager — L1/L2 の検証作業はサブエージェントに委譲)
│
├─ Implementation Agent A (background, worktree) ──完了──┐
├─ Implementation Agent B (background, worktree) ──完了──┤
└─ Implementation Agent C (background, worktree) ──完了──┘
                                                         │
                            L1/L2 は並列起動可 ◄─────────┘
                  Validation Agent (foreground) → A 検証 ┐
                  Validation Agent (foreground) → B 検証 ├ 並列可（subprocess 分離）
                  Validation Agent (foreground) → C 検証 ┘

                  L3 のみ直列（メインセッションが reload を扱う場合）
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
| L2 | Integration + CI ゲート | L1 + worktree 内で `scripts/ci-check.sh`（unit+integration+型+lint+doc-guard を一発で実行） | ~35K tokens |
| L3 | Full E2E | worktree の agent `.md` を main に一時適用 → `/analyze-activity` 実行 + 検証基準チェック → 復元 | ~150K tokens |

レベル判定は `dev-reference.md` §3 の Validation Level 判定表を参照。

## Manifest 受け渡しプロトコル（正本）

manifest の受け渡しには2経路があり、**既定は構造化出力方式**。`/tmp` ファイル方式は
手動フォールバック経路専用（下記）。

- **既定経路（`/implement` の `implement-tier` Workflow）= 構造化出力**:
  developer agent が manifest を**この呼び出しの構造化出力（schema 準拠）として返す**。
  Workflow が受け取り、validation-agent へ**プロンプトにインラインで渡す**。
  **`/tmp/validation_queue/<branch>.json` への書き出しは行わない**（デッドファイル・トークン浪費のため）。
- **手動フォールバック経路（構造化出力が使えない環境）= `/tmp` ファイル**:
  Implementation Agent が下記スキーマの JSON を `/tmp/validation_queue/<branch-name>.json` へ Write し、
  Validation Agent が同パスを Read する。手動 developer 委任時のみ使用。

manifest スキーマ（両経路共通）:
```json
{
  "branch": "feature/xxx",
  "worktree_path": "/absolute/path/to/worktree",
  "server_dir": "/absolute/path/to/worktree/packages/garmin-mcp-server",
  "pr_number": 123,
  "issue_number": 72,
  "validation_level": "L1|L2|L3",
  "change_category": "tool|handler|reader|agent|reporting|ingest|schema|other",
  "changed_files": ["src/garmin_mcp/tools/performance.py"],
  "test_results": {"unit": "pass", "integration": "pass"},
  "verification_activity_id": 20636804823
}
```

## Implementation Agent の責務

1. Worktree で実装 + unit/integration テスト pass
2. Validation manifest を返す:
   - **既定経路**: 構造化出力（schema 準拠）として返却（上記「Manifest 受け渡しプロトコル」参照）
   - **手動フォールバック経路のみ**: `/tmp/validation_queue/<branch-name>.json` へ Write
3. PR 作成 (draft)

## Main Session の責務 (Validation Manager)

- 完了通知を受信したら、validation_level に応じて起動先を選ぶ:
  - **L1 / L2**: Validation Agent を **foreground** で起動（毎回新規）。subprocess 分離されているため**複数の Validation Agent を並列起動してよい**（FIFO で1つずつ待つ必要はない）
  - **L3**: メインセッション（オーケストレーター）が**自分で**実行する（後述「L3: Full E2E（メインセッション担当）」）。L3 はサブエージェントに委譲せず、reload を扱うため直列に実行する
- 検証結果に応じて:
  - **pass**: PR を ready にする / `/ship` 候補としてユーザーに報告
  - **fail**: PR にコメント追記、修正指示
- L1/L2 の検証作業自体はサブエージェントに委譲する（Queue Manager は委譲のみ）。L3 のみメインセッションが直接実行する

## Validation Agent の責務（L1 / L2）

毎回独立起動。前回の検証コンテキストは持たない。subprocess 分離により**並列起動が安全**（複数 worktree の L1/L2 を同時に検証してよい）。
manifest の `validation_level` が L1/L2 のときのみ起動される。**サブエージェントは `reload_server` を呼ばない。**

### L1: In-process Check（reload なし）

1. Manifest 受領（既定経路: プロンプトにインラインで渡される JSON。手動フォールバック経路のみ `/tmp/validation_queue/<branch>.json` を Read）
2. `changed_files` から「どの下層関数を呼ぶか」を特定:
   - tool (ToolDef) 変更 → 委譲先の `GarminDBReader` メソッド（ToolDef は schema+dispatch を reader に配線するため、reader と同じリスク profile）
   - handler 変更 → 委譲先の `GarminDBReader` メソッド（または handler 内関数。現状 `handlers/` は `base.py` のみ）
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

### L2: Integration + CI ゲート（reload なし）

L2 は L1 に加え、**CI と対称な品質ゲート**を worktree subprocess で回す。L2=integration のみだと
unit / doc-guard が抜け、tool/table 追加時の doc-sync 漏れ（README/CLAUDE のカウント、golden snapshot、
count テスト）が ci-guard で初めて落ちて escalate になる（Epic #497 の #498・#500 で2回連続発生）。
これを **ci-guard 試行前**に止める。

1. L1（In-process Check）を実行（上記 1-4）
2. **CI 同一コマンドの正典**を worktree で実行（exit 0 を確認）:
   ```bash
   uv run --directory <worktree> bash scripts/ci-check.sh
   ```
   = whole-package の `pytest -m "unit or integration" ... --cov-fail-under=60` + `black --check .`
   + `mypy .` + doc-guard テスト（web 変更時は web-backend/web-frontend）。
   integration も既定で回るため、別途 integration テストを実行する必要はない（ci-check.sh 一発で CI 同等。Issue #743）。
3. テスト結果の判定:
   - ci-check.sh exit 0 → L2 pass
   - ci-check.sh 非 0（unit / integration / 型 / lint / doc-guard 失敗）→ 失敗ステップ名・テスト名・エラー内容を記録、L2 fail
4. pass/fail + 詳細を返却

> reload_server / health check ステップは存在しない。subprocess 値検証 + subprocess ci-check.sh のみ。

## L3: agent 定義変更の検証（同一セッション temp-apply は無効 — #742）

L3（agent 定義 = `.claude/agents/*-analyst.md` の変更）は agent コードであり MCP サーバコードではないため `reload_server` は不要。しかし **agent 定義は本文（system prompt）ごとセッション開始時に一度だけ登録され、セッション途中の変更は spawn 時に反映されない**（tool list について #586/#593、**本文について #742 spike で実証**：main の analyst 定義本文にマーカー指示を mid-session 追記して同 agentType を spawn したところ、agent は「そんな指示は存在しない」と回答＝セッション開始時キャッシュを使用）。

> **旧手順「worktree の `.md` を main に一時適用（`cp`）→ 同一セッションで `/analyze-activity` 実行 → 検証 → `git checkout` で復元」は無効**（#742 で棄却）。同一セッションの spawn はセッション開始時キャッシュ（＝**変更前**の定義）を使うため、**変更後の挙動を一切 exercise しない**。通ったように見えて old def を検証しているだけの偽ゲートだった。`cp` による mid-session 差し替えも `/resume` も反映されない。

### 正しい L3 検証（pre-merge diff レビュー + post-merge fresh-session E2E）

agent 定義変更は **pre-merge に同一セッションで挙動検証できない**（原理的制約）。したがって:

1. **Pre-merge（人間ゲート）**: メインセッションが worktree の `.md` 差分を Read で精査する。プロンプトは人間可読なので、構造・意図・出力キー整合・アンチ捏造ガード・[[]] 参照等をレビューで担保する。`implement-tier` は L3 を auto-merge せず escalate 済み。
2. **Merge**: レビュー通過後、人間判断でマージ（`/ship --pr N --validated` 相当）。
3. **Post-merge fresh-session E2E**: **変更が main の on-disk にある状態で開始した新規セッション**で `/analyze-activity {fixture_date}` を実行し、下記検証基準をチェックする（fresh session でないとキャッシュに載らないため必須）。
   - 構造/内容/Fixture 基準は `dev-reference.md` §3 の L3 検証基準を参照。
4. **不合格なら revert**: 構造チェック失敗なら該当 agent 定義変更を revert（**merge-first-verify-later; revert-if-bad**）。

> なぜ fresh session が必須か: agentType レジストリは（本文含め）セッション開始時に一度だけ登録され、以後 spawn ごとに再読込されない（#586/#593/#742）。ゆえに「新規/変更 agent 定義を **pre-merge に** E2E 検証する」ことは原理的に不可能で、挙動検証は必ずマージ後の新規セッションに回る。pre-merge ゲートは diff レビュー、behavioral 検証は post-merge fresh session、が唯一成立する分担。

## 例外: live MCP サーバコードの検証（メインセッション限定）

MCP サーバは **安定 shim + 差し替え可能 worker** で構成される（Epic #478）。`server.py` は MCP セッションを保持する極小 shim で、重いドメインコード（tool registry / DB reader）は `garmin_mcp.worker`（fresh プロセスで最新の on-disk コードを import し `dispatch` を実行）が持つ。`reload_server` は **worker のみ再起動 + `tools/list_changed` 送出**であり、**shim プロセスは死なない＝クライアント接続（subagent の tool access 含む）は切れない**。旧モデルの `os._exit` 自殺 + `scripts/start-mcp-server.sh` の override-dir 分岐によるクライアント respawn 依存は撤去済みで、`reload_server` の `server_dir` 引数も撤去された。

worktree コードの検証は引き続き subprocess（`uv run --directory <worktree>`）で行うのが主であり、これが最も堅牢（live サーバの状態に一切依存しない）。MCP サーバコード自体（handler/reader の挙動を live MCP tool 経由で確認したい等）を検証する**稀なケースのみ**、以下をメインセッションが行う。**サブエージェント内で `reload_server` を呼ぶことは禁止**（reload を跨ぐとサブエージェントは tool 一覧を再取得できず `mcp__garmin-db__*` を見失う。spike #243）。worker 再起動自体は shim 接続を切らないが、tool 一覧キャッシュの再取得をサブエージェントが扱えないため、依然としてメインセッション限定とする。

> 反映の範囲（実機検証済みの確定事実）:
> - **シグネチャ不変のコード変更**（reader ロジック / バグ修正＝更新の大多数） → `reload_server`（または次の tool 呼び出し）で worker が最新コードを import し、同一セッションに **完全 zero-touch** 反映される。
> - **スキーマ形変更**（tool 追加/削除・引数 = inputSchema 変更） → クライアントの tool 一覧はキャッシュされ、`tools/list_changed` 送出だけでは即更新されない。**この種だけ `/mcp` 再接続が1回必要**（reload 後に新ツールが再接続なしでは発見・呼び出し不可だった、と実 Claude Code セッションで実証済み）。
> - 設計指針: 形が変わりやすい tool を `options: dict`（汎用パラメータ）で受ければ inputSchema が不変＝ロジック変更扱いになり、zero-touch を維持できる。

1. メインセッション（サブエージェント不可）が main の `mcp__garmin-db__reload_server()` を呼ぶ。worker のみ再起動され、worktree ではなく on-disk の最新コードを import する。worktree コード自体を live で確認したい場合は、検証前にその内容を main repo へ反映してから reload する（subprocess 検証で済むなら不要）
2. `mcp__garmin-db__get_server_info()` を **ready になるまでポーリング**し、worker が応答することを確認
3. 対象 MCP tool を `verification_activity_id` で呼び出して値を検証
4. シグネチャ不変変更なら追加操作は不要。スキーマ形変更を確認した場合のみ `/mcp` 再接続を1回挟む
5. 通常は L1 の in-process 検証で十分なため、この手順は L1/L2 の代替ではなく追加の確認手段として位置づける

### 判定基準

- **構造チェック失敗**: FAIL（致命的）— PR にブロッキングコメント
- **内容チェック失敗**: WARNING — PR にコメント記載、マージ判断はユーザーに委ねる
- **ci-check.sh 非0 / テスト失敗 (L2)**: FAIL — 失敗ステップ・テストの詳細を PR コメントに記載（unit/型/lint/doc-guard/integration）
- **subprocess exit code 非0 / import エラー (L1)**: FAIL — エラー内容を PR コメントに記載

## Skip 条件

`validation_level: skip` は Validation Agent の実行をスキップする。
Issue → Plan → Worktree → PR のワークフローは変わらない。

判定: `validation_level` 未指定かつ変更が `.claude/rules/`, `docs/`, `CLAUDE.md` のみの場合に該当。

## Manifest ディレクトリ（手動フォールバック経路専用）

パス: `/tmp/validation_queue/`

**既定経路（`/implement`）では使わない**（manifest は構造化出力でインライン受け渡し）。
手動 developer 委任のフォールバック経路でのみ、このディレクトリに manifest を Write/Read する。

- Write tool が親ディレクトリを自動作成するため、明示的な `mkdir` は不要
- manifest ファイルは /tmp 内のため OS 再起動で自動消去される（明示的な削除は不要）
