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
- **`can't start new thread` は環境フレーク**。サンドボックスは cgroup `pids.max` でプロセス＋スレッド総数を上限管理しており（`cat /sys/fs/cgroup/pids.current` で現在値）、xdist のワーカー数が多いと上限に当たって**差分と無関係なファイル**のテストが落ちる。コード欠陥として扱わず、`ci-guard`（GitHub runner に同じ上限は無い）の結果を正とする。ローカルで再現を切り分けるなら該当テストだけ `-n 0` で再実行する。`-n auto` より上限付きの固定ワーカー数のほうが安定する。

## 3. L1 / L2 の手順

### Manifest

developer agent は commit 後に manifest を**構造化出力**で返す（`/tmp` へのファイル書き出しはしない）。
`validation_level` は developer が申告せず、Workflow が `changed_files` から §1 の表で決めて書き込んでから
validation-agent にインラインで渡す。

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

**workflow スクリプトも同じキャッシュに乗る（#1093）。** `.claude/workflows/*.js` をマージして main を
同期しても、`Workflow(name="...")` は**セッション開始時のスクリプト**を実行する（変更前のプロンプトのまま
走り、E2E 検証が丸ごと無駄になる）。セッション途中で新版を走らせるには**名前でなくファイルを渡す**:
`Workflow({scriptPath: "/workspace/.claude/workflows/<name>.js", args: {...}})`（呼び出し時にファイルを読む）。
E2E の結果を信用する前に、返り値の `promptPreview` でどちらの版が走ったかを必ず確認する。

L3 検証基準:
- **構造（FAIL）**: `run_note.analysis_data` 非 null、必須フィールド存在、merge の grounding ゲート通過、`merge_section_analyses` → DuckDB `section_analyses` 登録成功
- **内容（WARNING）**: `story` / `timeline` の数値が REPORT と一致、課題（growth point）が outside かつ adverse なシグナル、off-plan の軸、`policy.verdict == "concern"` のシーンのいずれかに乗っている（条件の正本は `run-note-analyst.md` §4 と merge ゲート）
- **Fixture**: Activity `20636804823`（2025-10-09, aerobic_base 5.66 km, 約 6:26/km, HR 平均 144 bpm）

## 5. 変更カテゴリ別の pre-merge 検証

`ci-guard` green は「CI が見た範囲が通った」だけで検証完了の証明ではない。原則は**変更した挙動を自動テストで exercise し CI でゲートする**。手動確認は自動化が困難な領域（分析の品質、web の見た目）に限り、PR 本文の `## Verification` に記録する。

| 変更カテゴリ | 必須検証 | CI |
|----------|---------|----|
| `packages/` コード | unit + L1/L2 | `lint-and-test` |
| `packages/garmin-web/` | pytest + vitest + build。見た目はマージ後の確認で可 | `web-backend` / `web-frontend` |
| `.claude/agents/*-analyst.md` | §4 | なし |
| `.claude/workflows/*.js` | 純粋ロジックを `// >>> testable` ブロックに置き `node --test` で検証。プロンプト変更はレビュー。**マージ後に同一セッションで挙動確認しない**（下記） | `meta-checks` |
| `.claude/hooks/*.sh` | 代表入力で exit code を検証する `scripts/tests/*.sh` | `meta-checks` |
| `.claude/skills/`, `.claude/rules/` | 手順を実行して挙動確認 | `meta-checks`（stale-phrase guard） |
| `docs/**`, `*.md`, `.claude/**` | doc-guard テスト（`tests/docs`）+ リンク・コマンド目視 | `docs-guard`（code も変わる PR は `lint-and-test` が兼ねる） |

## 6. Ship と auto-merge ゲート

1. push は `git.md` §2 の正典形（`GITHUB_TOKEN` の inline credential helper）。**origin/main の事前取り込みはしない**（遅れているだけの PR はそのままマージできる）。
2. PR が `mergeable=false`（コンフリクト）のときだけ `git.md` §2 の手順で merge 取り込み → push し直す。
3. `mcp__github__create_pull_request`（body に `Closes #{issue}` と `## Verification`）。
4. `bash scripts/wait-for-ci.sh <PR> --timeout 900` を**フォアグラウンドで 1 回**（Bash timeout 960000 ms 以上）。`run_in_background` / Monitor / `pgrep` / `kill` / `sleep` ループは使わない（ask ルールで止まる, #993）。exit 3 のときだけ `pull_request_read(method="get_check_runs")` で数回ポーリング。
5. **auto-merge ゲート**: 検証 PASS（L1/L2、または skip のレビュー、または L3 の diff レビュー）+ `ci-guard` success + mergeable。満たせば `mcp__github__merge_pull_request(merge_method="merge")`。
   **恒久承認（2026-08-09, #886）**: このゲートを満たす PR は PR ごとの確認なしにマージしてよい。背景ジョブ・非対話セッションにも適用。承認は PR のマージのみで、main への直接 push・force push・下記例外は対象外。
6. **例外は人間ゲート**: 検証 FAIL / 内容チェック WARNING / CI 失敗 / コンフリクト。auto-merge せず PR URL と理由を報告する。`.claude/workflows` `.claude/hooks` は `meta-checks` がゲートするので green なら auto-merge。
7. マージ後: ローカル main を同期し（`git.md` §2）、`bash scripts/cleanup-merged-worktrees.sh` で残留を掃除する。MCP サーバコードを変えたときは `mcp__garmin-db__reload_server()`（スキーマ形変更のみ `/mcp` 再接続）。

## 7. live MCP サーバの確認（メインセッション限定・稀）

MCP サーバは安定 shim + 差し替え可能 worker（Epic #478）。`reload_server` は worker のみ再起動し接続は切れない。シグネチャ不変の変更は zero-touch で反映、tool 追加/削除・引数変更のみ `/mcp` 再接続が 1 回要る。

**反映経路は 3 種類ある。worker だけを見て「直ったはず」と判断しない:**

| 変えた場所 | 反映方法 |
|-----------|---------|
| worker 側コード（tools/ handlers/ database/ 等）・シグネチャ不変 | `reload_server()` |
| tool の追加/削除・引数変更（スキーマ形状） | `reload_server()` + `/mcp` 再接続 1 回 |
| **shim 側コード（`server.py` / `worker_client.py`）** | **`reload_server` では反映されない**（worker しか再起動しないため shim の起動時 import が残る）。`/mcp` 再接続か次セッションが要る |

shim 側の修正をマージした直後に live tool で確かめると、古いコードのまま動いて**誤って失敗と判定する**。
検証は live tool ではなく subprocess で行う:
`uv run --directory packages/garmin-mcp-server python -c "...WorkerClient...rpc('call', <tool>, {})"`。
ユーザーには「`/mcp` 再接続（または次セッション）で反映」と伝える。

**`reload_server` は「呼んだ時点の cwd」に worker を固定する。** worktree の中で reload し、その worktree を
後で削除すると、worker は消えたパスを指したまま残る。症状が紛らわしく、**top-level import のツールは動き続け、
遅延 import のツールだけが落ちる**（例: `ModuleNotFoundError: No module named 'garmin_mcp.fitness.garmin_calendar'`
──モジュールは main に存在するのに）。worktree を出た後は **`/workspace` から reload し直す**。確認は
`get_server_info`（`worker_started_at` が更新される）＋遅延 import のツール 1 本。

**ingest 時の導出を変えたときは「reload → backfill → 再分析」の順を守る。** `uv run` のスクリプトは常に
ディスク上の新コードを import するが、MCP tool は長命 worker を通るため、reload 前は両者が食い違う。
backfill 後に `/analyze-activity` を流すと、その fetch 段が **live worker の `ingest_activity`（古いコード）**で
再取り込み＝再導出し、**そのアクティビティだけ backfill 結果が古い値に戻る**（Epic #827 で実際に発生）。
順序を誤ったら、stale worker の分析で再取り込みされたアクティビティを backfill し直す。live tool 経由で確認したい稀なケースだけ、メインセッションが `reload_server()` → `get_server_info()` が ready になるまでポーリング → 対象 tool を `verification_activity_id` で呼ぶ。サブエージェント内での `reload_server` は禁止。
