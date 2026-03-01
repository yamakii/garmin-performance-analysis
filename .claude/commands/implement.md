---
allowed-tools: Bash, Read, Glob, Grep, Task, AskUserQuestion, mcp__github__get_issue
description: Parallel implementation orchestrator for Epic sub-issues
user-invocable: true
---

# /implement — Parallel Implementation Orchestrator

Epic 配下の design-approved Issue を依存順に自動実装する。

## Arguments

$ARGUMENTS — Epic 番号、または個別 Issue 番号のリスト。

Examples:
- `/implement #91` — Epic #91 配下の design-approved Issue を依存順に自動実装
- `/implement #51 #52` — 指定 Issue のみ並列実装（依存チェックあり）

## Steps

### Step 1: Issue 取得と依存グラフ構築

```
# Epic の場合: sub-issues を取得
epic = mcp__github__get_issue(owner="yamakii", repo="garmin-performance-analysis", issue_number={epic})
# body から "- [ ] #N" パターンで sub-issue 番号を抽出

# 各 sub-issue の情報を取得
mcp__github__get_issue(owner="yamakii", repo="garmin-performance-analysis", issue_number={N})
```

### Step 2: フィルタリング

1. **State**: OPEN の Issue のみ対象（CLOSED はスキップ）
2. **Label**: `design-approved` ラベルがある Issue のみ対象
   - ラベルなしの Issue → スキップし報告: 「#{N} は design-approved がありません」
3. **Dependencies**: Issue body の `Blocked by: #N` から依存関係を抽出

### Step 3: 依存グラフからティア分類

```
Tier 0: 依存なし → 即座に起動可能
Tier 1: Tier 0 の Issue に依存 → Tier 0 マージ後に起動
Tier 2: Tier 1 の Issue に依存 → Tier 1 マージ後に起動
...
```

ユーザーに依存グラフを表示:

```
Implementation Plan:
  Tier 0 (parallel):
    #51 Extract ApiClient singleton
    #52 Extract RawDataFetcher
  Tier 1 (after Tier 0):
    #53 Refactor IngestWorker (blocked by #51)
  Tier 2 (after Tier 1):
    #54 Add error handling (blocked by #51, #52)

  Skipped:
    #55 — design-approved label missing
    #56 — already closed
```

### Step 4: Tier 0 の並列実装

各 Issue に対して汎用サブエージェントを worktree で起動:

```
Agent(subagent_type="developer", isolation="worktree", prompt="""
  Issue: #{number}
  Title: {title}
  Implement according to the Issue design.
  mcp__github__get_issue で設計を読み込んでください。
""")
```

**並列起動:** Tier 0 の全 Issue を同時に Agent tool で起動（独立しているため並列安全）。

### Step 5: Validation (FIFO)

各 developer agent 完了後、Validation Level に応じて検証を実行:

1. **Manifest 確認**: `/tmp/validation_queue/<branch>.json` を読み込む
   - developer agent が manifest を書いていない場合:
     worktree_path と changed_files から Validation Level を自動判定（`dev-reference.md` §3 の判定表を使用）
   - skip レベルの場合 → 検証をスキップし Step 6 へ

2. **Validation Agent 起動**: foreground で1つずつ起動（FIFO 順）
   ```
   Agent(subagent_type="validation-agent", prompt="""
     Manifest: /tmp/validation_queue/<branch>.json
     （または worktree_path, changed_files, validation_level を直接指定）
   """)
   ```

3. **結果に応じて分岐**:
   - **PASS** → Step 6 へ
   - **FAIL** → developer agent を resume して修正指示、再度 Step 5
   - **WARNING** → ユーザーに報告、判断を委ねる

### Step 6: Ship & 次のティアへ

Validation PASS（または skip）の PR をユーザーに報告:

```
Tier 0 results:
  #51 → PR #61 validated (L1 PASS): {URL}
  #52 → PR #62 validated (skip): {URL}

To proceed to Tier 1, merge these PRs:
  /ship --pr 61 --validated
  /ship --pr 62 --validated
```

### Step 7: 次のティアへ進行

マージ完了後、依存グラフを更新:

1. マージ済み Issue を完了としてマーク
2. 新たに unblock された Issue を特定
3. 次のティアの Issue に対して Step 4-5 を繰り返す

### Step 8: 全完了

全 Issue が完了したら報告:

```
All implementations complete for Epic #{epic}:
  #51 → merged (PR #61)
  #52 → merged (PR #62)
  #53 → merged (PR #63)
  #54 → merged (PR #64)
```

## DuckDB 並列安全性

- 実装はテスト時 mock DB を使用 → 並列 OK
- DB schema migration が必要な PR → マージは順次（依存関係で自然に制御）

## Notes

- マージ判断は常にユーザー（自動マージしない）
- 各 PR 完了時に PR URL を提示
- コンフリクト発生時: `git rebase origin/main && git push --force-with-lease`
