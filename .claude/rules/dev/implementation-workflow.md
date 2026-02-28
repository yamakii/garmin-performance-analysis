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

Risks セクション（任意）:
- 計画時点で不確実な技術的判断・未検証の前提があれば記載する
- [検証済] / [未検証] タグで区別し、spike 推奨があればユーザーに判断を仰ぐ
- リスクなしなら省略可

## Phase 1: Delegate (実装委任)

サブエージェント(general-purpose, worktree isolation)に以下を含めて委任:
- Issue 番号と `gh issue view` 実行指示
- プランの実装手順（そのまま渡す）
- 実装前確認（コードを書く前に出力させる）:
  1. 変更対象ファイル一覧
  2. Test Plan のテスト関数名一覧
  3. Validation Level 確認
- テスト実行指示: `uv run pytest {test_path} -m unit -v`
- lint 実行指示: `uv run ruff check {changed_files}`
- commit 指示: ブランチ名、コミットメッセージ形式
- **push しない**指示

## Phase 2: Verify (独立検証)

サブエージェント完了後、オーケストレーターが**自分で**以下を実行:

### 2a. コードレビュー
- worktree の全変更ファイルを Read で読む（diff ではなく全文）
- プランの各ステップと照合:
  - [ ] 新規ファイル: クラス名、メソッドシグネチャ、出力形式がプランと一致
  - [ ] 変更ファイル: 変更箇所がプランの指定位置と一致
  - [ ] テスト: プランのテスト名が全て存在

### 2b. テスト実行
プランの Validation Level に応じて（`dev-reference.md` §3 参照）:

| Level | 実行内容 | 完了条件 |
|-------|---------|---------|
| L1 | `uv run pytest {test_path} -m unit -v` | 0 failures |
| L2 | L1 + `uv run pytest -m integration --tb=short -q` | 0 failures |
| L3 | L2 + `cd analysis/ && claude -p "/analyze-activity 2025-10-09"` | 該当セクション出力あり |

**CRITICAL**: テスト結果は自分のターンで確認する。サブエージェントの報告を信じない。

### 2c. 判定
- 全チェック通過 → Phase 3 へ
- 失敗あり → サブエージェントを resume して修正指示、再度 Phase 2

## Phase 3: Ship (PR作成)

Phase 2 完了後のみ実行可能:
1. worktree ブランチを main repo に fetch
2. remote に push
3. `gh pr create` (Closes #{issue})
4. ユーザーに PR URL を報告
