# Issue Body Sync Protocol

## Principle: Issue body is a Living Document

Issue body の Design / Test Plan は **常に最新の実態** を反映する。
変更履歴は末尾の Change Log セクションに追記する。

```
## Design          ← 直接更新（常に最新の実態）
## Test Plan       ← チェックボックス更新 + 項目追加/削除
## Change Log      ← 追記のみ（変更履歴）
```

## 更新パターン（`gh issue edit --body-file -`）

全エージェント共通の安全なパターン（特殊文字対応）:

```bash
CURRENT_BODY=$(gh issue view {number} --json body --jq '.body')
# CURRENT_BODY を編集（sed / Python 等でセクション差し替え + Change Log 追記）
printf '%s' "$NEW_BODY" | gh issue edit {number} --body-file -
```

**重要**: `--body` フラグではなく `--body-file -` を使う（シェル特殊文字を安全に処理）

## フェーズ別の更新内容

### Plan 承認後（project-workflow.md が担当）

- **条件**: Plan で Design との差異がある場合のみ
- **更新**: Design セクションを Plan の内容で更新
- **Change Log**: `- YYYY-MM-DD (Plan): {差異の概要}`

### 実装完了時（tdd-implementer.md が担当）

- **条件**: 常に実行（実装は必ず何かしら変わる）
- **更新**:
  - Design: 実装で変わった部分を反映（インターフェース変更等）
  - Test Plan: チェックボックスを実績に合わせて更新、追加テストがあれば項目追加
- **Change Log**: `- YYYY-MM-DD (Build): {変更サマリー}`

### Issue クローズ時（completion-reporter.md が担当）

- **条件**: 常に実行
- **更新**: Change Log に完了サマリー追記
- **Change Log**: `- YYYY-MM-DD (Done): {テスト結果・品質チェック結果}`

### フォールバック（ship.md が担当）

- **条件**: `--close` 指定時に Change Log セクションが存在しない場合
- **更新**: 最小限の Change Log エントリを自動追記
- **Change Log**: `- YYYY-MM-DD (Ship): Closed via /ship`

## Sync しない条件

- Issue body に `## Design` セクションがない（古い Issue、手動作成 Issue）
- Issue 番号が不明
- dry-run モード

## エラーハンドリング

- **best-effort**: sync 失敗時はエラーメッセージを表示して続行
- ワークフローをブロックしない
- `gh issue edit` が失敗した場合、ユーザーに手動更新を促すメッセージを表示
