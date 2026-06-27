# Implementation Workflow

プラン承認後のフロー。各ステップの完了条件を満たさないと次に進めない。

## Phase 0: Plan Completeness Check

Phase 1 に進む前に、プランが以下を満たすことを確認。不足 → 補完してユーザーに再提示。

必須チェックリスト:
- [ ] Issue: #{number} | TBD + Validation Level: L1|L2|L3|skip
- [ ] Files to Create/Modify — パスと new/modify
- [ ] Interface — 新規クラス・関数の Python シグネチャ（既存変更のみの場合は変更メソッドのシグネチャ）
- [ ] Test Plan — test_{name} 形式、[unit|integration] マーカー、具体的入力値と期待値

thin plan の例（不足とみなす）:
- "Unit: パワーデータありのテスト" → test_xxx 形式でない、入力値なし
- Interface なしで新規クラス導入

例外: プロンプト変更のみ（.claude/agents/, .claude/rules/）→ Interface 省略可。Test Plan は必須。
※ これは Interface 省略の条件であり、Validation Level とは無関係。
agents は L3、rules は skip（dev-reference.md §3 参照）。

Risks セクション（任意）:
- 計画時点で不確実な技術的判断・未検証の前提があれば記載する
- [検証済] / [未検証] タグで区別し、spike 推奨があればユーザーに判断を仰ぐ
- リスクなしなら省略可

## Phase 1: Delegate (実装委任)

> **既定経路は `/implement <issue番号>`**（**単発 Issue / Epic を問わず**）。プラン承認後、Issue に
> `design-approved` を付与し（Phase 0 完全性で Design/Test Plan は担保済み）、`/implement <issue>` を
> 起動すれば `implement-tier` Workflow が **developer 実装 → L1/L2 検証 → push/PR → 条件付き
> auto-merge** を一括で回す（Phase 2〜3 を内包）。**この場合、以下の Phase 1〜3 を手で行う必要はない。**
>
> 以下の **手動 developer 委任は例外（フォールバック）**: L3（agent 定義変更）/ Workflow 不可環境 /
> skip-level の docs・rules 微修正。**「単発だから手動」ではない**。手動経路を取るときのみ次の手順に従う。

サブエージェント(developer, worktree isolation)に以下を含めて委任:
- Issue 番号と `mcp__github__issue_read` (method="get") 実行指示
- プランの実装手順（そのまま渡す）
- 実装前確認（コードを書く前に出力させる）:
  1. 変更対象ファイル一覧
  2. Test Plan のテスト関数名一覧
  3. Validation Level 確認
- テスト実行指示: `uv run pytest {test_path} -m unit -v`
- lint 実行指示: `uv run ruff check {changed_files}`
- commit 指示: ブランチ名、コミットメッセージ形式
- **push しない**指示
- **Manifest 書き出し指示**: commit 後に `/tmp/validation_queue/{branch}.json` へ manifest を書き出すこと（developer.md Step 5.5 参照）

## Phase 2: Verify (独立検証)

サブエージェント完了後、オーケストレーターが**自分で**以下を実行:

### 2a. コードレビュー
- worktree の全変更ファイルを Read で読む（diff ではなく全文）
- プランの各ステップと照合:
  - [ ] 新規ファイル: クラス名、メソッドシグネチャ、出力形式がプランと一致
  - [ ] 変更ファイル: 変更箇所がプランの指定位置と一致
  - [ ] テスト: プランのテスト名が全て存在

### 2b. テスト実行

> L1/L2 は subprocess 検証でプロセス分離されているため**並列起動が安全**（FIFO で1つずつ待つ必要はない）。直列が必須なのは L3（メインセッション担当・reload を扱う）のみ。詳細・経緯は `worktree-validation-protocol.md` / `dev-reference.md §3` を参照。

プランの Validation Level に応じて（`dev-reference.md` §3 参照）:

| Level | 実行内容 | 完了条件 |
|-------|---------|---------|
| L1 | `uv run pytest {test_path} -m unit -v` | 0 failures |
| L2 | L1 + `uv run pytest -m integration --tb=short -q` | 0 failures |
| L3 | L2 + メインセッションが worktree の `.md` を main に一時適用 → `/analyze-activity` 実行 → `git checkout` で復元（reload 非依存） | analysis_data 非null + 必須フィールド存在 |
| skip | Validation Agent スキップ。コードレビュー(Phase 2a)のみ | 2a チェック通過 |

CI 同一コマンド（whole-package の `black --check .` / `mypy .` / `pytest -m unit ... --cov-fail-under=60`、web 変更時は web-backend/web-frontend）を再現する正典コマンドは `scripts/ci-check.sh`。
Phase 2b の完了条件は **`scripts/ci-check.sh` が exit 0（0 failures）** とする。per-file の pre-commit では捕まらない型エラー・他モジュール破壊を CI 前に検出するため、commit 前に必ず実行する。

**CRITICAL**: テスト結果は自分のターンで確認する。サブエージェントの報告を信じない。

### 2c. 判定
- 全チェック通過 → Phase 3 へ
- 失敗あり → サブエージェントを resume して修正指示、再度 Phase 2

## Phase 2 と /implement の対応

- `/implement` の Step 5 が Phase 2 に相当する
- developer agent 完了 → Validation Agent 起動（Step 5）→ Phase 3 (Ship)
- Validation Agent は `/implement` が自動起動する（手動で別途起動する必要はない）
- skip レベルの場合は Phase 2a（コードレビュー）のみ実施し Phase 3 へ（Validation Agent はスキップ）

## Phase 2.9: Pre-merge verification (全 PR 必須)

> **`ci-guard` green は「CI が検証できた範囲が通った」だけ。検証完了の証明ではない。**
> 原則: **変更した挙動を自動テストで exercise し、CI でゲートする**。手動確認は
> 自動化が原理的に困難な領域（分析の品質、web の見た目）に限定し、その場合のみ
> PR 本文の `## Verification` に記録する。「人がマージ前に workflow を手動起動して
> 目視」は検証手段として不可（再現性なし・ロジックバグを見落とす）。

カテゴリ別の必須検証（マージ前）:

| 変更カテゴリ | 必須検証（自動が原則） | CI が実行 |
|----------|----------------------|----------|
| `packages/` コード | unit + L1/L2（subprocess import + 実 activity_id + integration）| `lint-and-test`（unit/型/lint）+ Validation Agent |
| `packages/garmin-web/` | pytest + vitest + build（CI）。**UI の見た目はマージ後の確認で可**（pre-merge ブロッカーにしない） | `web-backend` / `web-frontend` |
| `.claude/agents/*-analyst.md` | L3（fixture で `/analyze-activity`、構造/内容チェック） | なし（メインセッションが実行） |
| `.claude/workflows/*.js` | **純粋ロジックを `// >>> testable` ブロックに置き、`node --test .claude/workflows/tests/` で自動検証**。プロンプト/構造変更はレビュー | `meta-checks`（構文 smoke + `node --test`） |
| `.claude/hooks/*.sh` | hook を代表入力で発火させ exit code を検証する自動テスト（理想）。当面は `bash -n` + レビュー | `meta-checks`（`bash -n`） |
| `.claude/skills/*.md` / `rules/` | 該当 skill / ルール手順を実行して挙動確認（記録） | なし |
| `docs/**` / `*.md` / `.env.example` | docs-integrity / magic-number テスト + リンク・コマンド目視 | `lint-and-test`（doc-guard テスト） |

`scripts/check-claude-scripts.sh`（`meta-checks` が CI 実行）= `.claude/workflows`・`.claude/hooks` の構文 smoke + workflow 純粋ロジックの `node --test`。**ロジックは必ず testable ブロックに切り出してテストを足す**（#441 のような args 取り違えを CI で捕捉するため）。

## Phase 3: Ship (PR作成 + 条件付き auto-merge)

> **既定経路（`/implement`）では Ship＋auto-merge を `implement-tier` Workflow が内包する**ため、
> この手動 Phase 3 は**フォールバック経路（手動 developer 委任）専用**。`/implement` を使ったら
> 手動 push/PR/merge は不要（Workflow の返り値で merged/escalated を確認するだけ）。

> **正本マップ**: 本 Phase 3 が **auto-merge ゲート / Ship 手順の正本**。**検証メカニクス**は `worktree-validation-protocol.md`、**Validation Level 判定表**は `dev-reference.md §3` を正本とする。

Phase 2 + Phase 2.9 完了後のみ実行可能（手動経路）:
1. worktree ブランチを main repo に fetch
2. remote に push
3. `mcp__github__create_pull_request` (Closes #{issue}, 本文に `## Verification` を記録)
4. `ci-guard` が completed になるまでポーリング（`pull_request_read(method="get_check_runs")`）
5. **auto-merge ゲート**: 検証(L1/L2) PASS + `ci-guard` success + mergeable + **Phase 2.9 の検証完了**を満たせば
   `merge_pull_request` で自動マージ（テスト・検証の充実が前提, #395）。
   `/implement` ではこの判定を `implement-tier` Workflow が担う
6. **例外は人間ゲート**: 検証 FAIL / 内容チェック WARNING / CI 失敗 / コンフリクト / L3 は
   auto-merge せず（`implement-tier` も escalate）、PR URL と理由を報告して判断を仰ぐ。
   `.claude/workflows`・`.claude/hooks` 変更は `meta-checks`（`node --test` / `bash -n`）が CI でロジックをゲートするため、
   green であれば他カテゴリと同じく auto-merge する。agent 定義（`.claude/agents/*-analyst.md`）は L3 のため
   引き続き escalate し、メインセッションが L3 検証後に手動マージ（`/ship --pr N --validated`）。
