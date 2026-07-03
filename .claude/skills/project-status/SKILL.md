---
name: project-status
description: Show Epic progress as a dashboard with each sub-issue's status. Use when the user asks for project / Epic / issue progress. Optional argument is an Epic issue number; with none, shows all open Epics.
argument-hint: [epic-number]
allowed-tools: mcp__github__list_issues, mcp__github__issue_read
---

# /project-status — Epic Progress Dashboard

Epic の進捗を Sub-issue の状態と共に表示します。

## Arguments

$ARGUMENTS — Optional Epic issue number. If not provided, show all open Epics.

## Steps

### Step 1: Epic 一覧 or 指定 Epic の取得

#### 引数なしの場合: 全 open Epic を表示

```
mcp__github__list_issues(owner="yamakii", repo="garmin-performance-analysis", state="OPEN", labels=["epic"])
```

#### 引数ありの場合: 指定 Epic を取得

```
mcp__github__issue_read(method="get", owner="yamakii", repo="garmin-performance-analysis", issue_number=$ARGUMENTS)
```

### Step 2: Sub-issue 番号の収集 + live state 取得

> **本文の checkbox (`- [ ] #N` / `- [x] #N`) は state ソースとして読まない**（#516）。
> 本文 checkbox は drift する。完了判定は常に各 issue の **live state** を権威とする。

#### 2a: Sub-issue 番号の和集合を作る

ネイティブ sub-issue リンク（権威）と本文の `#N` 参照（移行期の旧 epic フォールバック）の
**和集合**を取る:

```
# ネイティブ sub-issue（権威）— 新しい epic はこれで全件返る
mcp__github__issue_read(method="get_sub_issues", owner="yamakii", repo="garmin-performance-analysis", issue_number={Epic番号})

# 本文の #N 参照（移行期: ネイティブ未リンクの旧 epic フォールバック）
# Epic body から #番号 を抽出（checkbox の有無は問わない。プレーン参照 `#N` も拾う）
```

両者を **issue 番号で和集合**にする（重複は1件に統合）。これで:
- 新 epic: `get_sub_issues` が全件返す
- 旧 epic（本文参照のみ・未リンク）: 本文 `#N` フォールバックで拾う

#### 2b: 各 issue を live fetch して state 判定

和集合の各番号を **毎回 `issue_read(method="get")` で live fetch** し、`state` / `state_reason`
で完了判定する（`state="closed"` → 完了）。**本文 checkbox は読まない。**

```
mcp__github__issue_read(method="get", owner="yamakii", repo="garmin-performance-analysis", issue_number={番号})
```

#### 2c: 移行期の drift 検出

旧 epic で**本文 checkbox** と **live state** が食い違う場合は `⚠️ drift` を付す
（本文は参考、live state が正）:
- 本文 `- [ ] #N`（未チェック）だが live `state="closed"` → `⚠️ drift (body stale)`
- 本文 `- [x] #N`（チェック済）だが live `state="open"` → `⚠️ drift (body stale)`

### Step 3: 進捗表示

完了数/総数は **live state** で算出する（本文 checkbox からは数えない）。
以下の形式で表示:

```
## #{Epic番号} {Epic タイトル} [{完了数}/{総数} complete] (live state)

  [x] #{番号} {タイトル} (closed {日付})
  [x] #{番号} {タイトル} (closed {日付})
  [ ] #{番号} {タイトル} (open — in progress)
  [ ] #{番号} {タイトル} (open)
  [x] #{番号} {タイトル} (closed {日付}) ⚠️ drift (body stale)

Progress: ████████░░░░ 50%
```

> 表示の `[x]`/`[ ]` は **live state を反映した派生表示**であり、Epic 本文の checkbox では
> ない。本文に checkbox が無い（新 epic）でも live state から `[x]`/`[ ]` を導出する。

複数 Epic がある場合は、各 Epic を上記形式で順に表示。

### Step 4: 次のアクション提案

未完了の Sub-issue のうち、依存関係がないもの（blocked by がない、または依存先が全て完了済み）を提案:

```
Next actionable:
  #{番号} {タイトル} — no blockers, ready to start
```

### Step 5: lessons.md 棚卸し（自己改善バッファの triage）

進捗表示のついでに、`.claude/tasks/lessons.md`（ルール昇格前の一時バッファ）を triage する。
lessons.md は git 管理外のため Read で内容を確認し、各エントリを分類:

- **ルール化できる再発防止** → 該当する `.claude/rules/**` に昇格（新規追記 or 既存強化）し、lessons.md から削除
- **一度きり / 既にルール化済み / 陳腐化** → lessons.md から削除
- **保留（まだ判断がつかない）** → 残す

> lessons.md は git 管理外。背景ジョブでは bg-isolation guard が Edit/Write を拒否するため、追記・削除は
> **Bash 経由の `uv run python`** で行う（`.claude/rules/dev/workflow-orchestration.md` の Self-Improvement Loop 参照）。

triage 結果を1行で報告する（例:「lessons 3件を triage: 1件を dev-reference §5 へ昇格、2件を陳腐化で削除」）。
エントリが0件、または全て保留なら「lessons.md: triage 対象なし」と報告してスキップ。
