# Development Reference

参照用辞書。手続き的ワークフローは `implementation-workflow.md` を参照。

## 1. Project Workflow

- **Issue必須**: 全開発タスクで Issue 作成。Issue なし実装は禁止
- **Plan構造**（thin plan は Phase 0 でブロック）:
  ```
  Issue: #{number} | TBD
  Type: Implementation | Roadmap
  Validation Level: L1 | L2 | L3 | skip

  ### Files to Create/Modify
  - `packages/.../foo.py` -- new | modify

  ### Interface
  class FooBar:
      def method(self, x: int) -> str: ...

  ### Risks
  - [検証済] DuckDB の JSON 型は nested object をサポート (v0.9+)
  - [未検証] Garmin API の rate limit が bulk fetch に影響する可能性
  - [未検証] time_series_metrics の 2000 行を1クエリで返すとタイムアウトする可能性 → spike 推奨

  ### Test Plan
  - [ ] test_method_happy_path [unit] -- x=5 → "5"
  - [ ] test_method_edge_case [unit] -- x=-1 → raises ValueError
  ```
- **Plan承認後**: Issue作成(TBD時) → Issue sync（`design-approved` 付与）→ 既定で `/implement <issue>` 実装 or `/decompose`。再確認不要
- **Review Gates**: Design → Test Plan → Code(CI) → Validation → Merge
  - **既定経路 = `/implement <issue番号>`**（**単発 Issue / Epic を問わず**）: 検証(L1/L2) PASS + `ci-guard` success + mergeable なら **auto-merge**（`implement-tier` Workflow）。例外（FAIL / 内容チェック WARNING / CI 失敗 / コンフリクト / L3）のみ人間が `/ship --pr N --validated`
  - **手動 developer 委任 + `/ship --pr N` は例外（フォールバック）**: L3（agent 定義変更）/ Workflow 不可環境 / skip-level の docs・rules 微修正のみ。**「単発だから手動」ではない**（単発でも既定は /implement）

### Issue Sync

Issue body の Design/Test Plan は常に最新を反映。Change Log に `(Plan):`, `(Build):`, `(Done):`, `(Ship):` で追記。
**プラン承認時**: Design/Test Plan が後述の `design-approved 品質基準` を満たす Issue に **`design-approved` ラベルを付与**してから `/implement <issue>` を起動する（**単発 Issue でも付与する**。これで /implement Step 2 のゲートを通り、既定経路に乗る）。
Skip: Design セクションなし、Issue番号不明、dry-run時。

### design-approved 品質基準

`/implement` が `design-approved` ラベルでフィルタする際の品質基準:
- Test Plan に test_xxx 形式の関数名がある
- 各テストに [unit|integration] マーカーがある
- 入力値・期待値が具体的（数値 or 文字列）
- 新規クラス/関数 → Interface にシグネチャがある

満たさない → ラベルを外し、Issue コメントで補完を依頼。

## 2. Git & Branching

- **Serena activate**: コード調査前に必ず `mcp__serena__activate_project()` 実行
- **Stale recovery**: Serena → activate、garmin-db → `reload_server()`、それでもダメなら `/mcp`
- **全変更**: Issue → Plan → Worktree → PR（branch protection により必須）
- **Planning**: main branch (read-only)
- **PR**: merge commit --no-ff、1 PR = 1 Sub-issue、title は Conventional Commits、body に `Closes #{issue}`
- **Commit**: Conventional Commits + Co-Authored-By。単一の関心事のみ（"and" が必要なら分割）
- **Parallel**: 各 worktree = 1 branch = 1 PR。依存関係 → 先の PR マージ後に rebase

## 3. Validation

> **正本マップ（検証の単一ソース）**: **Validation Level 判定表** = 本節(§3) / **検証メカニクス（L1/L2/L3 の実行手順）** = `worktree-validation-protocol.md` / **auto-merge ゲート・Ship 手順** = `implementation-workflow.md` Phase 3。他ファイルの再掲は参照用で、矛盾時は各正本を優先する。

### Validation Level 判定

> **Validation Level は PR マージ前の検証方法を決めるもの。
> skip は「Validation Agent をスキップ」であり「ワークフロー(Issue/Plan/Worktree/PR)をスキップ」ではない。**

変更対象の**全ファイル**を以下と照合し、最も高いレベルを採用:

| 変更対象 | Level |
|----------|-------|
| `.claude/agents/*-analyst.md` | L3 |
| `tools/` (ToolDef), `handlers/`, `database/readers/` | L1 |
| `reporting/`, `ingest/`, `database/migrations/` | L2 |
| `packages/garmin-web/` | L2 |
| `.claude/rules/`, `docs/`, `CLAUDE.md` | skip |

迷ったら L2。L3 は agent 定義変更時のみ。

### 検証フロー (Validation Agent)

> **正本: `worktree-validation-protocol.md`**（L1/L2/L3 の実行手順・根拠の詳細）。本節は辞書用の要約で、矛盾時は正本を優先する。

- **L1**: worktree コードを subprocess で import → 下層関数を `verification_activity_id` で呼び出し、非null・型一致・値範囲 (pace 3:00-9:00, HR 80-200)・`json.dumps` 可能を検証（`reload_server` は使わない）
- **L2**: L1 + worktree 内で `uv run --directory <worktree> bash scripts/ci-check.sh`（CI 同一: unit+型+lint+doc-guard、web 変更時は web チェック）exit 0 + `uv run --directory <worktree> pytest -m integration --tb=short -q`（ci-check.sh は integration 非実行のため別途）。tool/table 追加時の doc-sync/unit 漏れを ci-guard 前に検出
- **L3**: agent 定義変更時、メインセッションが worktree の `.md` を main に一時適用 → `/analyze-activity` 実行 + 構造/内容チェック → `git checkout` で復元（reload 非依存）
- L1/L2 は subprocess 分離のため**並列起動が安全**（複数 worktree の L1/L2 を同時検証可）。直列必須は L3 のみ。経緯（旧 FIFO 直列前提）は正本を参照

### L3 検証基準

- **構造 (FAIL=致命的)**: 全5セクションの `analysis_data` 非null、必須フィールド存在、merge → DuckDB `section_analyses` 登録成功
- **内容 (WARNING)**: ペース/HR が fixture 範囲と整合、セクション間の矛盾なし
- **Fixture**: Activity `20636804823` (2025-10-09, aerobic_base 5.66km, ~6:26/km, HR avg 144bpm)
- **Content check ranges**:
  - Pace: 6:00-6:45/km (360-405 sec/km)
  - HR: 120-160 bpm

## 4. Testing

- **本番データ依存禁止**。全テストに pytest marker 必須 (`unit`/`integration`/`performance`/`garmin_api`)
- **Markers**: unit = mock+no I/O+<100ms、integration = mock DuckDB、performance = real data OK (skip if unavailable)
- **Budget**: unit <200ms。Read-only fixture は `scope="class"`/`scope="module"`
- **DB fixture**: `initialized_db_path` (~0.6ms) を使う。`GarminDBWriter()` per test (~50ms) 禁止
- **並列安全**: 実行順序非依存、テストごとに unique `activity_id`
- **Test名**: Issue Test Plan の `test_xxx` をそのまま使用

## 5. Code Quality

- **Pre-commit自動実行**: Black (line-length=88), Ruff (E,F,W,I,UP,B,SIM,RUF), Mypy (python 3.12)
- **Settings**: `pyproject.toml` が source of truth
- **Bash style**: 独立コマンドは並列 Bash tool calls。チェーンは order-dependent 時のみ

## 6. Architecture

- **Filter at ingest**: データ変換は ingest 時に実行。query 側の WHERE フィルタで汚いデータをマスクしない
- **Garmin native HR zones**: `heart_rate_zones` テーブルから読む。計算式(220-age等)やハードコード禁止
- **DuckDB connections**: `get_connection()` / `get_write_connection()` のみ使用。raw `duckdb.connect()` 禁止
- **DuckDB concurrency**: single writer。locked エラー → リトライ(3回, 2s backoff)
- **DuckDB dates**: `datetime.date` で返る → MCP/JSON前に `str()` で変換
- **DB safety**: 100+ activities。削除前にユーザー確認必須。`--delete-db` を第一候補にしない
- **Safe regen**: `--tables X --activity-ids N --force` で surgical update
- **No backward-compat shims**: リファクタ時は全 call site を同時更新。aliases/re-exports 禁止

## 7. Prohibited

- main ブランチでの実装 / main への直接 push / force push
- Serena なしのコード編集
- `git worktree remove --force` (status 未確認)
- DB 削除をユーザー確認なしで実行
- ルールを CLAUDE.md に直接記述 (`.claude/rules/` を使う)
- 本番データ依存テスト
- 複数の無関係な変更を1コミットに混在
- Validation Level: skip を理由に Issue/Plan/Worktree/PR をスキップ

## 8. LLM Round-Trip Optimization

- 同じツール 3回以上のループ → Python スクリプト1コマンドに集約
- Read→Parse→Call の連鎖 → バッチスクリプト化
- スクリプト出力は JSON 1行で完結させる

## 9. Real Data Validation

- worktree コード変更の検証は in-process / subprocess（`uv run --directory <worktree> ...`）で行う。`reload_server` は使わない（サブエージェントは reload を跨ぐと tool 一覧を再取得できず `mcp__garmin-db__*` を見失う。spike #243）。live MCP 確認が要る稀なケースのみメインセッションが reload + `get_server_info` の ready ポーリング
- **reload モデル（Epic #478）**: MCP サーバは安定 shim（MCP セッション保持）+ 差し替え可能 worker（fresh プロセスで最新コードを import し `dispatch` 実行）。`reload_server` は **worker のみ再起動 + `tools/list_changed` 送出**で、shim は死なない＝接続は切れない（旧 `os._exit` 自殺 + クライアント respawn 依存・`server_dir` 引数は撤去済み）。**シグネチャ不変変更は zero-touch 反映、スキーマ形変更（tool 追加/削除・引数変更）のみ `/mcp` 再接続が1回必要**
- MCP tool 変更 → 実 activity_id で `statistics_only=True/False` 両方テスト
- Agent 定義変更 → fixture データで E2E 検証
