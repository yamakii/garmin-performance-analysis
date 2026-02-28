# Development Reference

参照用辞書。手続き的ワークフローは `implementation-workflow.md` を参照。

## 1. Project Workflow

- **Issue必須**: 全開発タスクで Issue 作成。Issue なし実装は禁止
- **Plan冒頭**: `Issue: #{number} | TBD` + `Type: Implementation | Roadmap` + `Validation Level: L1|L2|L3|skip`
- **Plan承認後**: Issue作成(TBD時) → Issue sync → worktree実装 or `/decompose`。再確認不要
- **Review Gates**: Design → Test Plan → Code(CI) → Validation → Merge(`/ship --pr`)

### Issue Sync

Issue body の Design/Test Plan は常に最新を反映。Change Log に `(Plan):`, `(Build):`, `(Done):`, `(Ship):` で追記。
Skip: Design セクションなし、Issue番号不明、dry-run時。

## 2. Git & Branching

- **Serena activate**: コード調査前に必ず `mcp__serena__activate_project()` 実行
- **Stale recovery**: Serena → activate、garmin-db → `reload_server()`、それでもダメなら `/mcp`
- **Code changes** (`packages/`, `tests/`): worktree MANDATORY
- **Rules/docs** (`.claude/rules/`, `docs/`): PR required (branch protection)
- **Planning**: main branch (read-only)
- **PR**: merge commit --no-ff、1 PR = 1 Sub-issue、title は Conventional Commits、body に `Closes #{issue}`
- **Commit**: Conventional Commits + Co-Authored-By。単一の関心事のみ（"and" が必要なら分割）
- **Parallel**: 各 worktree = 1 branch = 1 PR。依存関係 → 先の PR マージ後に rebase

## 3. Validation

### Validation Level 判定

変更対象の**全ファイル**を以下と照合し、最も高いレベルを採用:

| 変更対象 | Level |
|----------|-------|
| `.claude/agents/*-analyst.md` | L3 |
| `handlers/`, `database/readers/` | L1 |
| `reporting/`, `ingest/`, `database/migrations/` | L2 |
| `.claude/rules/`, `docs/`, `CLAUDE.md` | skip |

迷ったら L2。L3 は agent 定義変更時のみ。

### 検証フロー (FIFO キュー + Validation Agent)

1. L1: `reload_server(server_dir=worktree_path)` → MCP tool 呼び出し → 非null、型一致、値範囲チェック (pace 3:00-9:00, HR 80-200) → `reload_server()` で復帰
2. L2: L1 + worktree 内で `uv run pytest -m integration --tb=short -q`
3. L3: L2 + Validation Agent で `/analyze-activity` 実行 + 構造/内容チェック（詳細は `worktree-validation-protocol.md`）

### L3 検証基準

- **構造 (FAIL=致命的)**: 全5セクションの `analysis_data` 非null、必須フィールド存在、Markdown生成
- **内容 (WARNING)**: ペース/HR が fixture 範囲と整合、セクション間の矛盾なし
- **Fixture**: Activity `12345678901` (2025-10-09, Easy run 7km, 5:15-5:45/km)

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

## 8. LLM Round-Trip Optimization

- 同じツール 3回以上のループ → Python スクリプト1コマンドに集約
- Read→Parse→Call の連鎖 → バッチスクリプト化
- スクリプト出力は JSON 1行で完結させる

## 9. Real Data Validation

- コード変更後は `reload_server()` 必須（stale state で false negative になる）
- MCP tool 変更 → 実 activity_id で `statistics_only=True/False` 両方テスト
- Agent 定義変更 → fixture データで E2E 検証
