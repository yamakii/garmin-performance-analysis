# Project Workflow Rules

## Plan Mode 内での Issue 連携

**全ての開発タスクで Issue を作成する。** Issue なしでの実装は禁止。

### Phase 1: 探索と分解判定

1. **Issue 番号の確認** — `gh issue view {number} --json body,title` で設計を読み込む
2. **分解判定** — 複数の独立した作業単位 → プラン内で `/decompose` を推奨

### Phase 2: プラン作成

プランファイル冒頭に必須:
```
Issue: #{number} | TBD (create before implementation)
Type: Implementation | Roadmap
```

| Type | 内容 |
|------|------|
| **Implementation** | 具体的なコード変更プラン |
| **Roadmap** | 優先度付き改善提案リスト |

Issue Design セクションに以下を必須で含める:
```
Validation Level: L1|L2|L3|skip
```
`e2e-verification.md` のガイドラインを参照してレベルを決定する。

### Plan 承認後の自動遷移ルール

**実行順序（スキップ禁止）:**
1. Issue 作成（TBDの場合）
2. Issue sync（差異あれば Design 更新 — 詳細は `issue-sync.md`）
3. 遷移アクション:

| Type | 条件 | 承認後アクション |
|------|------|-----------------|
| Implementation | 単一作業 | worktree → 実装 |
| Implementation | 分解推奨 | `/decompose` → Epic + Sub-issues |
| Roadmap | — | `/decompose` → Epic + Sub-issues |

**ユーザーに再確認しない。** 優先度マトリクスあり = その順序で実行承認済み。

### Review Gates

| Gate | Timing | Who | Criteria |
|------|--------|-----|----------|
| Design | Issue 作成時 | User (/decompose で確認) | Design セクション完備 + Validation Level 明記 |
| Test Plan | テスト追加後 | CI + レビュー | テストが Design をカバー |
| Code | PR ready 後 | User + CI | CI pass + diff 確認 |
| Validation | PR ready 後 | Validation Agent | `validation_level` に応じた検証 pass |
| Merge | /ship --pr | User | 全チェック green |
