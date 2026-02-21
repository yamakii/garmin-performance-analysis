---
allowed-tools: Bash, Read, Write, Edit, TaskCreate, TaskList, Glob
description: Resume a saved session checkpoint after /clear
user-invocable: true
---

# /resume — Restore Session from Checkpoint

保存されたチェックポイントからセッション状態を復元します。

## Arguments

$ARGUMENTS — Optional slug name. If not provided, show available checkpoints and ask user to choose.

## Steps

### Step 1: Slug解決

1. `$ARGUMENTS` があればそのslugを使用
2. なければ MEMORY.md の Active Checkpoints テーブルを読み込み、一覧表示：
   ```
   Available checkpoints:
     1. {slug} — {type} — #{issue} — {goal} (Updated: {date})
     2. {slug} — {type} — #{issue} — {goal} (Updated: {date})
   Which checkpoint to resume? (number or slug)
   ```
   AskUserQuestion で選択を求める

3. 指定されたslugのチェックポイントファイルが存在しない場合：
   ```
   Checkpoint '{slug}' not found.

   Available checkpoints:
     - {slug1} ({type}, {date})
     - {slug2} ({type}, {date})

   Usage: /resume <slug>
   ```

### Step 2: チェックポイント読み込み

`~/.claude/projects/-home-yamakii-workspace-garmin-performance-analysis/memory/checkpoint-{slug}.md` を読み込む。

### Step 3: Issue 情報復元

チェックポイントに Issue 番号がある場合:

```bash
# Issue の最新状態を取得（クローズ済みの場合もある）
gh issue view {number} --json number,title,state,body,labels

# Epic がある場合、Epic の進捗も確認
gh issue view {epic-number} --json number,title,body
```

Issue の設計情報を読み込み、文脈を復元する。

### Step 4: 環境検証・復元

タイプ別に環境を検証：

#### dev タイプ
1. **Worktree確認**: `git worktree list` でworktreeパスが存在するか確認
   - 存在しない場合: 警告を出し、再作成するか確認
2. **Serena activate**: worktreeパスで `mcp__serena__activate_project` を実行
3. **Issue 設計確認**: Issue body の Design セクションをサマリ表示
4. **Git状態**: `git status --short` と `git log --oneline -3` で現在の状態を確認
5. **Failing tests**: 記録されていれば、該当テストファイルの存在を確認

#### analysis タイプ
1. **Pending list確認**: 未処理アクティビティ一覧を表示

#### training-plan タイプ
1. **Plan読み込み**: plan_idがあれば `mcp__garmin-db__get_training_plan(plan_id, summary_only=True)` で確認
2. **Fitness状態**: 必要に応じて `mcp__garmin-db__get_current_fitness_summary()` を呼び出し

### Step 5: タスクリスト再作成

チェックポイントの Task List セクションから、各タスクを TaskCreate で再作成。
- pending のタスクは pending のまま作成
- in_progress のタスクも pending で作成（再開時に改めて in_progress にする）

### Step 6: 復元サマリ表示

```
Session restored: {slug}

## Summary
- **Type**: {type}
- **Goal**: {session goal}
- **Issue**: #{number} ({title}) — {state}
- **Epic**: #{epic-number} ({epic-title}) — {progress}

## Current State
{タイプ別の主要状態を3-5行で}

## Task List
{再作成したタスク一覧}

## Next Action
{チェックポイントに記録された次のアクション}

---
Ready to continue. 上記の Next Action から始めますか？
```

### Step 7: チェックポイント更新

1. チェックポイントファイルの Status を `active` → `resumed` に更新
2. MEMORY.md の該当行も Updated 日付を更新

## Error Handling

- チェックポイントファイルが壊れている場合: パース可能な部分だけ復元し、警告表示
- Worktreeが消失している場合: 再作成の提案（ブランチが残っていれば）
- Issue がクローズ済みの場合: 警告表示し、再オープンするか確認
- DuckDBに接続できない場合: 警告表示し、手動復旧を提案
