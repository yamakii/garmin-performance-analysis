# Implementation Workflow

プラン承認後のフロー。各ステップの完了条件を満たさないと次に進めない。

## Phase 1: Delegate (実装委任)

サブエージェント(general-purpose, worktree isolation)に以下を含めて委任:
- プランの実装手順（そのまま渡す）
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
