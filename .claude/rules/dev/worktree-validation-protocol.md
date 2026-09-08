---
paths:
  - "packages/**"
  - ".claude/**"
  - "scripts/**"
  - "docs/**"
  - "CLAUDE.md"
---

# Worktree Validation Protocol

**本書が検証と auto-merge ゲートの唯一の正本**。Validation Level の判定表、L1/L2/L3 の実行手順、
Ship 手順、auto-merge の条件はすべてここに置く。他のルール・skill・agent 定義は本書へリンクするだけで、
内容を再掲しない（再掲は必ず陳腐化して矛盾を生む。#1045）。

## 1. Validation Level 判定

Validation Level は **PR マージ前の検証方法**を決める。skip は「Validation Agent を省く」であって、
Issue / Plan / Worktree / PR を省く許可ではない。

変更対象の**全ファイル**を以下と照合し、最も高いレベルを採用する:

| 変更対象 | Level |
|----------|-------|
| `.claude/agents/*-analyst.md` | L3 |
| `tools/` (ToolDef), `handlers/`, `database/readers/` | L1 |
| `reporting/`, `ingest/`, `database/migrations/` | L2 |
| `packages/garmin-web/` | L2 |
| `.claude/rules/`, `.claude/skills/`, `docs/`, `CLAUDE.md` | skip |

迷ったら L2。L3 は analyst agent 定義変更時のみ。`implement-tier.js` の `levelForFile` はこの表の写しなので、表を変えたら同じ PR で更新する。

| Level | 内容 | 完了条件 |
|-------|------|---------|
| L1 | worktree コードを subprocess で import し、下層関数を `verification_activity_id` で呼ぶ | 非 null・型一致・値範囲・`json.dumps` 可・exit 0 |
| L2 | L1 + `uv run --directory <worktree> bash scripts/ci-check.sh` | exit 0 |
| L3 | pre-merge は diff レビュー、post-merge に新規セッションで E2E（§4） | 構造チェック通過 |
| skip | コードレビューのみ。CI（`docs-guard` / `meta-checks`）が品質ゲート | レビュー通過 |

## 2. 実行原則

- **`reload_server` に依存しない**。サブエージェントは reload を跨ぐと `mcp__garmin-db__*` を失い復帰できない（spike #243）。worktree コードは `uv run --directory <worktree> ...` の subprocess で検証する。
- **L1/L2 は並列起動してよい**（subprocess 分離）。直列が必要なのは L3 だけ。
- **リソースは別問題**（#1009）。`scripts/ci-check.sh` 1 本が約 2 GB、live セッション 1 つが約 0.6 GB。ci-check.sh は重い工程の前に cgroup の余裕を待ち、コンテナが 16 GiB 未満なら flock で直列化する。この待ちを外さない。判断は `bash scripts/ci-check.sh --resources-only` で確認できる。
- **サブエージェントの報告を信じない**。テスト結果とマージ状態はオーケストレーターが自分のターンで確認する（GitHub の `pull_request_read` が ground truth）。

## 3. L1 / L2 の手順

### Manifest

developer agent は commit 後に manifest を**構造化出力**で返す（`/tmp` へのファイル書き出しはしない）。
Workflow はこれを validation-agent にインラインで渡す。

```json
{
  "branch": "feat/123-xxx",
  "worktree_path": "/absolute/path/to/worktree",
  "server_dir": "/absolute/path/to/worktree/packages/garmin-mcp-server",
  "issue_number": 123,
  "validation_level": "L1|L2|L3|skip",
  "change_category": "tool|handler|reader|agent|reporting|ingest|schema|other",
  "changed_files": ["src/garmin_mcp/tools/performance.py"],
  "test_results": {"unit": "pass", "integration": "pass"},
  "verification_activity_id": 20636804823
}
```

### L1: In-process check

1. `changed_files` から呼ぶ下層関数を決める: tool (ToolDef) / handler → 委譲先の `GarminDBReader` メソッド、reader → 該当メソッド、script → 公開関数。不明なら変更ファイルを Read してシグネチャを確認。
2. subprocess で import して呼び、`json.dumps`（MCP 境界相当）まで通す:
   ```bash
   uv run --directory <worktree>/packages/garmin-mcp-server python -c \
     "import json; from garmin_mcp.database.db_reader import GarminDBReader; print(json.dumps(GarminDBReader().get_performance_trends(<activity_id>), default=str))"
   ```
3. 判定: 非 null、期待する型・構造、値範囲（ペース 3:00-9:00/km、HR 80-200 bpm）、`json.dumps` 成功、exit 0。いずれか欠ければ FAIL。

### L2: L1 + CI 同一ゲート

```bash
uv run --directory <worktree> bash scripts/ci-check.sh
```

= whole-package の `ruff` + `black --check` + `mypy` + `pytest -m "unit or integration" --cov-fail-under=60` + doc-guard、`packages/garmin-web/` 変更時は web-backend / web-frontend も。fresh worktree の dev 依存は ci-check.sh が自分で sync する。反復時は `--unit-only`。exit 非 0 は FAIL（失敗ステップ・テスト名を記録）。

## 4. L3: analyst agent 定義の変更

agent 定義は本文ごとセッション開始時に登録され、セッション途中の変更は spawn に反映されない（#742 で実証）。したがって **pre-merge に同一セッションで挙動検証することは不可能**で、手順は次の 3 段だけ:

1. **Pre-merge: メインセッションが diff を Read でレビュー**（構造・意図・出力キー整合・捏造ガード）。人間への往復は不要（#888）。問題があれば escalate。
2. **Merge**: レビュー通過 + `ci-guard` success で auto-merge。`implement-tier` Workflow は diff レビューができないため L3 を escalate する。escalate を受けたメインセッションがレビューしてマージする。
3. **Post-merge: 新規セッションで `/analyze-activity 2025-10-09`** を実行し、下記基準を確認する。**必須の追跡義務**。マージした報告には「E2E 未了」と明記し、未了の間は同じ agent 定義へ変更を重ねない。不合格なら revert。

L3 検証基準:
- **構造（FAIL）**: 全 5 セクションの `analysis_data` 非 null、必須フィールド存在、`merge_section_analyses` → DuckDB `section_analyses` 登録成功
- **内容（WARNING）**: ペース 6:00-6:45/km（360-405 sec/km）、HR 120-160 bpm、セクション間の矛盾なし
- **Fixture**: Activity `20636804823`（2025-10-09, aerobic_base 5.66 km, 約 6:26/km, HR 平均 144 bpm）

## 5. 変更カテゴリ別の pre-merge 検証

`ci-guard` green は「CI が見た範囲が通った」だけで検証完了の証明ではない。原則は**変更した挙動を自動テストで exercise し CI でゲートする**。手動確認は自動化が困難な領域（分析の品質、web の見た目）に限り、PR 本文の `## Verification` に記録する。

| 変更カテゴリ | 必須検証 | CI |
|----------|---------|----|
| `packages/` コード | unit + L1/L2 | `lint-and-test` |
| `packages/garmin-web/` | pytest + vitest + build。見た目はマージ後の確認で可 | `web-backend` / `web-frontend` |
| `.claude/agents/*-analyst.md` | §4 | なし |
| `.claude/workflows/*.js` | 純粋ロジックを `// >>> testable` ブロックに置き `node --test` で検証。プロンプト変更はレビュー | `meta-checks` |
| `.claude/hooks/*.sh` | 代表入力で exit code を検証する `scripts/tests/*.sh` | `meta-checks` |
| `.claude/skills/`, `.claude/rules/` | 手順を実行して挙動確認 | `meta-checks`（stale-phrase guard） |
| `docs/**`, `*.md`, `.claude/**` | doc-guard テスト（`tests/docs`）+ リンク・コマンド目視 | `docs-guard`（code も変わる PR は `lint-and-test` が兼ねる） |

## 6. Ship と auto-merge ゲート

1. `git fetch origin` し、必要なら `origin/main` へ rebase または merge（force push は禁止）。
2. push（worktree では `GITHUB_TOKEN` の inline credential helper を使う。`implement-tier.js` の `pushCmd` が正典）。
3. `mcp__github__create_pull_request`（body に `Closes #{issue}` と `## Verification`）。
4. `bash scripts/wait-for-ci.sh <PR> --timeout 900` を**フォアグラウンドで 1 回**（Bash timeout 960000 ms 以上）。`run_in_background` / Monitor / `pgrep` / `kill` / `sleep` ループは使わない（ask ルールで止まる, #993）。exit 3 のときだけ `pull_request_read(method="get_check_runs")` で数回ポーリング。
5. **auto-merge ゲート**: 検証 PASS（L1/L2、または skip のレビュー、または L3 の diff レビュー）+ `ci-guard` success + mergeable。満たせば `mcp__github__merge_pull_request(merge_method="merge")`。
   **恒久承認（2026-08-09, #886）**: このゲートを満たす PR は PR ごとの確認なしにマージしてよい。背景ジョブ・非対話セッションにも適用。承認は PR のマージのみで、main への直接 push・force push・下記例外は対象外。
6. **例外は人間ゲート**: 検証 FAIL / 内容チェック WARNING / CI 失敗 / コンフリクト。auto-merge せず PR URL と理由を報告する。`.claude/workflows` `.claude/hooks` は `meta-checks` がゲートするので green なら auto-merge。
7. マージ後: `git fetch origin && git merge --ff-only origin/main` でローカル main を同期し、`bash scripts/cleanup-merged-worktrees.sh` で残留を掃除する。MCP サーバコードを変えたときは `mcp__garmin-db__reload_server()`（スキーマ形変更のみ `/mcp` 再接続）。

## 7. live MCP サーバの確認（メインセッション限定・稀）

MCP サーバは安定 shim + 差し替え可能 worker（Epic #478）。`reload_server` は worker のみ再起動し接続は切れない。シグネチャ不変の変更は zero-touch で反映、tool 追加/削除・引数変更のみ `/mcp` 再接続が 1 回要る。live tool 経由で確認したい稀なケースだけ、メインセッションが `reload_server()` → `get_server_info()` が ready になるまでポーリング → 対象 tool を `verification_activity_id` で呼ぶ。サブエージェント内での `reload_server` は禁止。
