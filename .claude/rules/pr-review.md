# PR Review Rules

## PR Lifecycle
- Draft PR: tdd-implementer Phase 1.5 (Red 完了後)
- Ready: Phase 4.5 (全コミット完了後)
- Review: completion-reporter の自動レビュー + ユーザー確認
- Merge: /ship --pr (merge commit)

## Convention
- 1 PR = 1 Sub-issue (1:1 マッピング)
- PR title: Conventional Commits 形式
- PR body: "Closes #{issue}" を含む
- Merge strategy: merge commit --no-ff (TDD の Red→Green→Refactor 履歴を保持)

## Automated Review Checklist
- 設計カバレッジ: Issue Design の対象ファイル vs 実際の変更ファイル
- テスト計画カバレッジ: Issue Test Plan vs 実際のテスト関数
- CI ステータス: 全チェック通過

## Parallel Development
- 独立した Sub-issue は同時に別 worktree + 別 PR で作業可能
- 依存関係のある Sub-issue: 依存先の PR マージ後に着手
- コンフリクト発生時: git rebase origin/main + git push --force-with-lease
