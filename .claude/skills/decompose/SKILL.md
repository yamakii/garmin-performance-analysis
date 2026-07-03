---
name: decompose
description: Decompose a large development task into an Epic plus implementable sub-issues on GitHub. Use when a dev task is big enough to need splitting into multiple coordinated GitHub issues (e.g. リファクタリング全体・新機能の段階実装). Argument is the task description.
argument-hint: <task description>
allowed-tools: Bash, Read, Glob, Grep, mcp__serena__activate_project, mcp__serena__find_symbol, mcp__serena__get_symbols_overview, mcp__serena__find_referencing_symbols, mcp__serena__search_for_pattern, mcp__serena__read_file, mcp__serena__list_dir, mcp__github__issue_write, mcp__github__issue_read, mcp__github__sub_issue_write, AskUserQuestion
---

# /decompose — Task Decomposition into GitHub Issues

大きなタスクをコードベース調査 → Epic + Sub-issues に分解し、GitHub Issues として作成します。

## Arguments

$ARGUMENTS — タスクの説明（日本語 or 英語）。例: "ingestパイプラインをリファクタリングしたい"

## Steps

### Step 1: Serena 活性化

```
mcp__serena__activate_project(<リポジトリルートの絶対パス>)  # checkout 位置は環境依存（sandbox では /workspace）
```

### Step 2: コードベース調査

タスクの説明から関連するコードを探索:

1. `mcp__serena__find_symbol` / `mcp__serena__get_symbols_overview` で関連シンボルを特定
2. `mcp__serena__find_referencing_symbols` で依存関係を把握
3. `mcp__serena__search_for_pattern` でパターン検索
4. 影響範囲と変更の複雑さを評価

**Test Plan 作成時のルール:**
- Design Interface に記載した各関数・メソッドに対して最低1ケース
- happy path + error/edge case を各1つ以上
- テスト関数名は `test_{what}` 形式で明示
- scenario は具体値を含む（「不正データ」ではなく「distance=-1.0」）
- `[marker]` は `@pytest.mark.*` に直結（unit/integration/performance）
- `--` の左 = Given/When (setup)、`→` の右 = Then (assertion)

### Step 3: 分解判定

調査結果から規模を判定:

- **小さいタスク** (1-2ファイル変更、明確なスコープ): 単発 Issue を作成（epicラベルなし）
- **大きいタスク** (3+ファイル、複数の独立した作業単位): Epic + Sub-issues に分解

### Step 4: 分解案の提示

ユーザーに以下を提示し、AskUserQuestion で承認を得る:

```
## 分解案: {タスク名}

### Epic: {Epic タイトル}
{ゴールの説明}

### Sub-issues:
1. **{Sub-issue 1 タイトル}** — {説明} [{見積もり: S/M/L}]
   - Files: {変更対象ファイル}
   - Blocks: #{他のsub-issue番号}
2. **{Sub-issue 2 タイトル}** — {説明} [{見積もり: S/M/L}]
   ...

### 依存関係:
{依存グラフを簡潔に}

この分解で進めますか？
```

### Step 5: GitHub Issues 作成

承認後、GitHub MCP ツールで Issues を一括作成:

#### 5a: Epic Issue 作成

> **checkbox を使わない。** sub-issue の open/closed state は GitHub のネイティブ sub-issue
> リンク（Step 5c でリンク）が issue state から自動集計するため、本文 checkbox は state を
> 二重管理して必ず drift する（#516）。本文には **state を持たないプレーン参照リスト**のみ置く。

```
mcp__github__issue_write(
  method="create",
  owner="yamakii",
  repo="garmin-performance-analysis",
  title="{Epic タイトル}",
  labels=["epic"],
  body="""## Goal
{ゴールの説明}

## Sub-issues
> ステータスは GitHub のネイティブ sub-issue 欄（"X of Y completed"）と
> `/project-status` の live fetch が権威。下記は参照用で state を持たない。

- #{sub-issue-1 — 作成後に番号で更新} — {一言目的} — {Level}
- #{sub-issue-2} — {一言目的} — {Level}
...

## 依存関係
{state を持たない構造情報なので drift しない。ASCII グラフ可}

## Context
{コードベース調査で得た背景情報}"""
)
```

#### 5b: Sub-issue Issues 作成

各 Sub-issue を作成:

```
mcp__github__issue_write(
  method="create",
  owner="yamakii",
  repo="garmin-performance-analysis",
  title="{Sub-issue タイトル}",
  labels=["sub-issue", "design-approved"],
  body="""## Summary
{何をするか}

## Parent
Part of #{Epic番号}: {Epic タイトル}

## Design
### Files to Create/Modify
- `path/to/file.py` -- {new/modify/delete}

### Interface
{主要なクラス・関数のシグネチャ}

## Test Plan

### `ClassName.method_name()`
- [ ] `test_scenario_happy_path` [unit] -- {setup/input} → {expected outcome}
- [ ] `test_scenario_edge_case` [unit] -- {setup/input} → {expected outcome}

### Integration
- [ ] `test_e2e_scenario` [integration] -- {setup} → {assertion}

## Dependencies
- Blocks: #{依存先のsub-issue番号}
- Blocked by: #{依存元のsub-issue番号}"""
)
```

#### 5c: ネイティブ sub-issue リンク + Epic 本文の参照更新

Sub-issues の番号が確定したら、**各 sub-issue を GitHub のネイティブ sub-issue として
Epic にリンク**する（checkbox の更新はしない）。これで Epic の "X of Y completed" が
issue state から自動集計され、`/project-status` の `get_sub_issues` が全件返す。

```
# 作成した各 sub-issue を Epic にネイティブリンク（sub_issue_id は issue の内部 id）
mcp__github__sub_issue_write(
  method="add",
  owner="yamakii",
  repo="garmin-performance-analysis",
  issue_number={Epic番号},
  sub_issue_id={sub-issue の内部 id}
)
```

> `sub_issue_id` は issue **番号**ではなく内部 **id**。`issue_write(method="create")` の
> 戻り値に含まれる `id` を使う（取得できない場合は `issue_read(method="get")` の `id`）。

リンク後、Epic 本文の Sub-issues 参照リストを実番号で更新（**checkbox にはしない**。
state を持たないプレーン参照のまま）:

```
mcp__github__issue_write(
  method="update",
  owner="yamakii",
  repo="garmin-performance-analysis",
  issue_number={Epic番号},
  body="""## Goal
...
## Sub-issues
> ステータスは GitHub のネイティブ sub-issue 欄と /project-status の live fetch が権威。

- #51 Extract ApiClient singleton — シングルトン化 — L1
- #52 Extract RawDataFetcher — キャッシュ優先取得 — L2
...

## 依存関係
#51 → #52 → ...
"""
)
```

### Step 6: 結果報告

```
Issues created:
  Epic: #{番号} {タイトル}
  Sub-issues:
    #{番号} {タイトル} [S/M/L]
    #{番号} {タイトル} [S/M/L]
    ...

Next: Plan mode で #{最初のsub-issue番号} から着手できます。
  mcp__github__issue_read (method="get") で設計を確認してください。
```

## Small Task Flow

単発の小さなタスクの場合:

```
mcp__github__issue_write(
  method="create",
  owner="yamakii",
  repo="garmin-performance-analysis",
  title="{タイトル}",
  body="""## Summary
{何をするか}

## Design
{簡潔な設計}

## Test Plan

### `function_or_class()`
- [ ] `test_happy_path` [unit] -- {setup/input} → {expected outcome}
- [ ] `test_edge_case` [unit] -- {setup/input} → {expected outcome}"""
)
```

## Spike Flow

調査タスクの場合:

```
mcp__github__issue_write(
  method="create",
  owner="yamakii",
  repo="garmin-performance-analysis",
  title="Spike: {調査タイトル}",
  labels=["spike"],
  body="""## Question
{調査したいこと}

## Scope
{調査範囲}

## Expected Output
{調査結果の形式 — 例: ADR, 比較表, PoC}"""
)
```
