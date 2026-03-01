---
allowed-tools: mcp__github__list_issues, mcp__github__get_issue
description: Show Epic progress with sub-issue status
user-invocable: true
---

# /project-status — Epic Progress Dashboard

Epic の進捗を Sub-issue の状態と共に表示します。

## Arguments

$ARGUMENTS — Optional Epic issue number. If not provided, show all open Epics.

## Steps

### Step 1: Epic 一覧 or 指定 Epic の取得

#### 引数なしの場合: 全 open Epic を表示

```
mcp__github__list_issues(owner="yamakii", repo="garmin-performance-analysis", state="open", labels=["epic"])
```

#### 引数ありの場合: 指定 Epic を取得

```
mcp__github__get_issue(owner="yamakii", repo="garmin-performance-analysis", issue_number=$ARGUMENTS)
```

### Step 2: Sub-issue の状態取得

Epic body の task list から Sub-issue 番号を抽出し、各 Issue の状態を取得:

```
# Epic body から #番号 を抽出
# 各 Issue の state を取得
mcp__github__get_issue(owner="yamakii", repo="garmin-performance-analysis", issue_number={番号})
```

### Step 3: 進捗表示

以下の形式で表示:

```
## #{Epic番号} {Epic タイトル} [{完了数}/{総数} complete]

  [x] #{番号} {タイトル} (closed {日付})
  [x] #{番号} {タイトル} (closed {日付})
  [ ] #{番号} {タイトル} (open — in progress)
  [ ] #{番号} {タイトル} (open)

Progress: ████████░░░░ 50%
```

複数 Epic がある場合は、各 Epic を上記形式で順に表示。

### Step 4: 次のアクション提案

未完了の Sub-issue のうち、依存関係がないもの（blocked by がない、または依存先が全て完了済み）を提案:

```
Next actionable:
  #{番号} {タイトル} — no blockers, ready to start
```
