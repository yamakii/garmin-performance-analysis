# Issue Body Sync Protocol

Issue body の Design / Test Plan は常に最新の実態を反映する。変更履歴は Change Log に追記。

## 更新コマンド

```bash
CURRENT_BODY=$(gh issue view {number} --json body --jq '.body')
printf '%s' "$NEW_BODY" | gh issue edit {number} --body-file -
```

## フェーズ別の更新内容

| Phase | Condition | Updates | Change Log |
|-------|-----------|---------|------------|
| Plan承認後 | Design差異あり | Design更新 | `(Plan): {差異}` |
| 実装完了 | 常時 | Design + Test Plan | `(Build): {変更}` |
| Close時 | 常時 | — | `(Done): {結果}` |
| Ship時 | Change Logなし | — | `(Ship): Closed via /ship` |

## Skip条件

Design セクションなし、Issue 番号不明、dry-run モード → スキップ。

Best-effort: sync 失敗時はエラー表示して続行。
