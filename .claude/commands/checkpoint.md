---
allowed-tools: Bash, Read, Write, Edit, TaskList, Glob
description: Save session state to auto-memory for resumption after /clear
user-invocable: true
---

# /checkpoint — Save Session State

セッションの進捗状態をauto-memoryに保存します。`/clear` 後に `/resume` で復元できます。

## Arguments

$ARGUMENTS — Optional slug name. If not provided, auto-generate from branch name or `task-YYYYMMDD-HHMM`.

## Steps

### Step 1: Slug解決

1. `$ARGUMENTS` があればそれをslugとして使用
2. なければ `git branch --show-current` でブランチ名を取得し、`feature/foo-bar` → `foo-bar` に変換
3. ブランチ名がmainなら `task-YYYYMMDD-HHMM` を自動生成

### Step 2: Git状態収集

以下を収集してください：
```bash
git branch --show-current
git status --short
git log --oneline -5
git worktree list
```

### Step 3: タスクリスト取得

TaskList ツールを呼び出し、pending/in_progress のタスクを取得してください。

### Step 4: タイプ判定

以下のルールでチェックポイントタイプを判定：
- **dev**: worktreeが存在する、またはfeature/ブランチにいる場合
- **analysis**: 直前の会話でanalyze-activity/batch-analyze系の作業をしていた場合
- **training-plan**: 直前の会話でplan-training系の作業をしていた場合
- 判断できない場合はユーザーに確認

### Step 5: チェックポイントファイル書き出し

`~/.claude/projects/-home-yamakii-workspace-claude-workspace-garmin-performance-analysis/memory/checkpoint-{slug}.md` に書き出し：

```markdown
# Checkpoint: {slug}

## Meta
- **Created**: YYYY-MM-DD HH:MM
- **Type**: dev | analysis | training-plan
- **Status**: active
- **Session goal**: {会話の目的を一文で}

## State

### dev の場合
- **Branch**: {branch name}
- **Worktree**: {worktree path or "none"}
- **Phase**: planning | red | green | refactor | review
- **Planning doc**: {planning.md path if exists}
- **Failing tests**: {failing test names or "none"}
- **Key files modified**: {git status から主要変更ファイル}

### analysis の場合
- **Processed activities**: {完了したactivity ID list}
- **Pending activities**: {未処理のactivity ID list}
- **Current activity**: {処理中のactivity ID or "none"}

### training-plan の場合
- **Plan ID**: {plan_id or "not yet created"}
- **Step**: fitness-assessment | plan-generation | review | upload
- **VDOT**: {value or "not assessed"}
- **Goal**: {goal description}
- **Constraints**: {key constraints}

## Task List
{pending/in_progress タスクのみ、箇条書き}
- [ ] {task subject} — {brief description}

## Context Notes
{セッション中の重要な決定事項、気づき、注意点を最大10行で}

## Next Action
{次にやるべきことを具体的に1-2文で}
```

### Step 6: MEMORY.md更新

`~/.claude/projects/-home-yamakii-workspace-claude-workspace-garmin-performance-analysis/memory/MEMORY.md` を読み込み、Active Checkpointsテーブルを更新。

ファイルが存在しない、またはActive Checkpointsセクションがない場合は初期構造を作成：

```markdown
# Project Memory: garmin-performance-analysis

## Active Checkpoints
| Slug | Type | Goal | Next Action | Updated |
|------|------|------|-------------|---------|
| {slug} | {type} | {goal} | {next action} | {YYYY-MM-DD} |

## Persistent Notes
```

既存の場合はテーブルに行を追加（同一slugは上書き）。

**ルール:**
- テーブル最大5行。超える場合は最も古いresumedエントリを削除
- 7日超 + status=resumed のエントリは自動削除（チェックポイントファイルも削除）

### Step 7: 完了報告

以下を表示：
```
Checkpoint saved: {slug}
  Type: {type}
  Next: {next action}
  File: memory/checkpoint-{slug}.md

/clear 後に /resume {slug} で復元できます。
```
