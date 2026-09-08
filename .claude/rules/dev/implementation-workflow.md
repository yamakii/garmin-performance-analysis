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
※ これは Interface 省略の条件であり、Validation Level とは無関係（判定表は `worktree-validation-protocol.md` §1）。

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
> **各ティア起動前は origin 同期（`git fetch origin` → behind なら `git merge --ff-only origin/main`）が必須**
> — 初回ティアだけでなく **tier 間（前ティアの auto-merge 完了後、次ティア起動前）にも毎回**実行する。
> fetch を怠ると次ティアの worktree が前ティアのマージ済み土台を含まないベースから切られ、add/add
> コンフリクトの原因になる（手順は `.claude/skills/implement/SKILL.md` Step 3.5 が正本）。
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
- **Manifest 返却指示**: commit 後に manifest を構造化出力で返すこと（developer.md Step 5.5）

## Phase 2: Verify (独立検証)

サブエージェント完了後、オーケストレーターが**自分で**以下を実行:

### 2a. コードレビュー
- worktree の全変更ファイルを Read で読む（diff ではなく全文）
- プランの各ステップと照合:
  - [ ] 新規ファイル: クラス名、メソッドシグネチャ、出力形式がプランと一致
  - [ ] 変更ファイル: 変更箇所がプランの指定位置と一致
  - [ ] テスト: プランのテスト名が全て存在

### 2b. 検証実行

Validation Level の判定と L1/L2/L3/skip の手順・完了条件は `worktree-validation-protocol.md` §1〜§5。
`packages/` を変更した PR は `scripts/ci-check.sh` exit 0 が完了条件。

**CRITICAL**: テスト結果は自分のターンで確認する。サブエージェントの報告を信じない。

### 2c. 判定
- 全チェック通過 → Phase 3 へ
- 失敗あり → サブエージェントを resume して修正指示、再度 Phase 2

## Phase 3: Ship (PR作成 + 条件付き auto-merge)

手順・auto-merge ゲート・例外・恒久承認（#886）の範囲は `worktree-validation-protocol.md` §6 が正本。
`/implement` 経由では `implement-tier` Workflow が同じゲートを内包するので手動 push/PR/merge は不要。
