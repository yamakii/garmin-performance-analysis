---
name: implement
description: Parallel implementation orchestrator for an approved issue (single) or an Epic's design-approved sub-issues. Use when the user wants to auto-implement a plan-approved issue, or the issues under an Epic in dependency order, with worktree-isolated agents. Argument is the Epic number or a list of issue numbers.
argument-hint: <epic-number | issue-numbers>
allowed-tools: Bash, Read, Glob, Grep, Task, Workflow, AskUserQuestion, mcp__github__issue_read
---

# /implement — Parallel Implementation Orchestrator

プラン承認済みの**単発 Issue**、または **Epic 配下**の design-approved Issue を依存順に自動実装する。

## Arguments

$ARGUMENTS — Epic 番号、または個別 Issue 番号のリスト。

Examples:
- `/implement #91` — Epic #91 配下の design-approved Issue を依存順に自動実装
- `/implement #51 #52` — 指定 Issue のみ並列実装（依存チェックあり）

## Steps

### Step 1: Issue 取得と依存グラフ構築

```
# Epic の場合: sub-issues を取得
epic = mcp__github__issue_read(method="get", owner="yamakii", repo="garmin-performance-analysis", issue_number={epic})
# body から "- [ ] #N" パターンで sub-issue 番号を抽出

# 各 sub-issue の情報を取得
mcp__github__issue_read(method="get", owner="yamakii", repo="garmin-performance-analysis", issue_number={N})
```

### Step 2: フィルタリング

1. **State**: OPEN の Issue のみ対象（CLOSED はスキップ）
2. **Label / 承認判定**:
   - **Epic 展開のサブ Issue**: `design-approved` ラベル必須。ラベルなし → スキップし報告: 「#{N} は design-approved がありません」（品質ゲート維持）
   - **明示指定された個別 Issue 番号**（`/implement #N` で直接渡された単発/複数）: `design-approved` が無くても、body に **Design ＋ Test Plan セクションがあれば対象**とし、その場で `mcp__github__issue_write` で `design-approved` を付与してから進む。**Design か Test Plan が欠落**している場合のみスキップし、補完を依頼する
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

### Step 3.5: origin 同期（各ティア起動前・必須）

ティアの Workflow を起動する**前に毎回**、メインセッションがローカル main を origin へ
fast-forward only で同期する。`implement-tier.js` は git fetch もベース ref 指定もせず、worktree
作成はハーネスの `isolation: 'worktree'` に委譲する。ローカルの remote-tracking ref は fetch
しない限り古いままなので、**前ティアの auto-merge 完了後に fetch しないと、次ティアの developer が
「前ティアのマージ済み土台を含まないベース」から分岐 → 土台を再実装 → 巨大 add/add コンフリクト**
という事故が起きる（Epic #526 系で実際に発生）。

```
git fetch origin
# behind なら:
git merge --ff-only origin/main
```

- **初回ティア（Tier 0）起動前**にも実行する（プラン承認から時間が経ち origin が進んでいる場合に備える）。
- **各ティア（Tier 1 以降）起動前**にも毎回実行する。前ティアの auto-merge が origin/main を進めるため、
  次ティアの worktree が最新土台から切られるよう fetch + ff-only が必須。
- `--ff-only` なので、ローカルに未コミット変更や独自コミットがあると**安全に失敗**（force しない・
  データ消失なし）。失敗したら理由を報告し、ユーザーに手動同期を促す（自動 stash / reset はしない）。

> Step 7a（全完了後の post-merge sync）はこの同期の**最終回**にあたる。手順は同一。

### Step 4: ティアを Workflow で実装（implement-tier.js）

各ティアは **`implement-tier` Workflow** に委譲する。1回の呼び出しが
「ティア内 Issue の並列 worktree 実装 → L1/L2 並列検証 → PR 作成 → 条件付き auto-merge」
を担い、結果（merged / escalated / dropped）を構造化して返す。

```
Workflow(
  scriptPath=".claude/workflows/implement-tier.js",
  args={
    "owner": "yamakii",
    "repo": "garmin-performance-analysis",
    "tierName": "Tier 0",
    "issues": [
      {"number": 51, "title": "Extract ApiClient singleton"},
      {"number": 52, "title": "Extract RawDataFetcher"}
    ]
  }
)
```

> Workflow は明示的なオプトイン機能。`/implement` の呼び出し自体がオプトインに該当する
> （ユーザーがティア自動実装を要求している）ため、このコマンド内での Workflow 起動は許可される。

Workflow 内部の流れ（`implement-tier.js`）:
1. **Implement**（並列）: 各 Issue を developer agent（`isolation: 'worktree'`）で実装。manifest を
   schema 付き構造化出力で返す（`/tmp/validation_queue` ファイルは使わない）
2. **Validate**（並列）: validation-agent が L1/L2 を subprocess で検証。`skip` は pass 扱い、
   `L3` は escalate（メインセッション担当のため Workflow では検証しない）
3. **Ship**: push → PR 作成（`Closes #{issue}`）→ `ci-guard` が completed になるまでポーリング
4. **Merge**（auto-merge ゲート）: **L1/L2 PASS かつ `ci-guard` success かつ mergeable** の PR のみ
   `merge_pull_request` で自動マージ。条件を満たさないものは merge せず escalate

### Step 5: Workflow 結果の処理

Workflow の返り値:
```json
{
  "tier": "Tier 0",
  "merged":    [{"issue": 51, "pr": 61, "sha": "..."}],
  "escalated": [{"issue": 52, "pr": 62, "reason": "ci-guard が failure"}],
  "dropped":   []
}
```

- **merged**: 自動マージ済み。ユーザーに PR とマージ SHA を報告
- **escalated**: auto-merge せず人間判断が必要。理由ごとに対応:
  - `検証 FAIL` → developer agent を resume して修正、再度 Workflow（該当 Issue のみ）
  - `内容チェック WARNING` → ユーザーに報告し判断を仰ぐ（マージするなら `/ship --pr N --validated`）
  - `ci-guard が failure` → CI ログを確認して修正
  - `L3` → メインセッションが worktree の `.md` を main に一時適用して L3 検証（`worktree-validation-protocol.md`）→ 手動マージ
  - `コンフリクト` → `git -C <worktree> rebase origin/main` → push → 再度 Step 4
- **dropped**: agent 死亡 or skip。エラーを報告

### Step 6: 次のティアへ進行

ティアの merged Issue がマージされると依存が解け、次ティアが unblock される。

1. マージ済み Issue を完了としてマーク
2. 新たに unblock された Issue を次ティアとして特定
3. **Step 3.5（origin 同期: fetch + ff-only）を再実行**してから、次ティアの Issue で Step 4（Workflow）を再実行。
   前ティアの auto-merge 済み土台を次ティアの worktree ベースへ確実に取り込む

> auto-merge により merge → 次ティア unblock が Workflow 内で完結するため、複数ティアを
> 続けて流せる。escalated が残るティアのみ人間が介入する。

### Step 7: 全完了

#### 7a. ローカル main を同期（必須）

auto-merge は PR を **origin/main にのみ**反映する。ローカル作業ツリーは自動更新されず
origin より遅れて drift するため、**MCP サーバ・各種ツールはローカルから起動する以上、
マージ済みでもローカルでは旧コードが走る**。最終報告の前に、メインセッションが **Step 3.5 と
同一手順**（`git fetch origin` → behind なら `git merge --ff-only origin/main`）でローカル main を
origin へ同期する。これはティアごとの同期の**最終回**にあたる。

- `--ff-only` なので、ローカルに未コミット変更や独自コミットがある場合は**安全に失敗**
  （force しない・データ消失なし）。失敗したら同期できなかった旨と理由を報告し、ユーザーに
  手動同期を促す（自動 stash / reset はしない）。
- 成功したら同期後 SHA を報告する。MCP サーバコードを変更した Epic の場合は
  「ローカル main を `<sha>` に同期。live MCP に反映するには `mcp__garmin-db__reload_server()`
  （シグネチャ不変変更は zero-touch）。スキーマ形変更を含む場合のみ `/mcp` 再接続」と案内する。

#### 7b. Cleanup（マージ済み worktree/ブランチの安全掃除）

7a の同期後、メインセッションが `bash scripts/cleanup-merged-worktrees.sh` を実行する
（dry-run ではなく実行）。auto-merge で残った `.claude/worktrees/*` と `feat/*`・`worktree-*`
ブランチのうち、**origin/main にマージ済み かつ clean なものだけ**を削除する。

- 安全: `git worktree remove`（**`--force` なし**）+ `git branch -d`（**`-D` 禁止**）。dirty な
  worktree や未マージブランチは git が拒否＝残す。消せなかったものは warn 報告のみで止まらない。
- 実行後、スクリプトのサマリ（removed worktrees / deleted branches / skipped(理由付き)）を
  オーケストレータが報告する。

#### 7c. 報告

全 Issue が完了したら報告:

```
All implementations complete for Epic #{epic}:
  #51 → merged (PR #61)   [auto-merged: L1 PASS + ci-guard ✓]
  #52 → merged (PR #62)   [auto-merged: skip + ci-guard ✓]
  #53 → escalated (PR #63) [WARNING: 内容チェック — 要レビュー]

Local main: synced to <sha>   (または: ff-only failed — 手動同期が必要)
Cleanup: removed N worktree(s), deleted M branch(es); skipped K (理由)
```

## DuckDB 並列安全性

- 実装はテスト時 mock DB を使用 → 並列 OK
- DB schema migration が必要な PR → マージは順次（依存関係で自然に制御）

## Notes

- **auto-merge ゲート**: 検証（L1/L2）PASS + `ci-guard` success + mergeable を満たす PR のみ
  Workflow が自動マージする。テスト・検証の充実がこの緩和の前提（#395）
- **人間ゲートが残る例外**: 検証 FAIL / 内容チェック WARNING / CI 失敗 / コンフリクト / L3 含み
- **L3 は Workflow に載せない**: agent 定義変更はメインセッションが reload 非依存で担当
- 各 PR の結果（merged/escalated）は Workflow 返り値からユーザーに提示
- branch protection は維持（auto-merge も `ci-guard` 成功が前提）
