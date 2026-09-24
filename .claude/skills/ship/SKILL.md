---
name: ship
description: Run the full ship workflow — commit, push, create or merge the PR, and close issues. Use when the user asks to ship / commit / push the current changes or to merge a specific PR. Optional argument is a commit message, or flags like --pr N / --close M.
argument-hint: [commit message | --pr N --close M]
allowed-tools: Bash, Read, Glob, Grep, mcp__github__list_pull_requests, mcp__github__pull_request_read, mcp__github__merge_pull_request, mcp__github__create_pull_request, mcp__github__issue_read, mcp__github__issue_write
---

# /ship — Commit & Push Workflow

Run the full ship workflow for the current changes.

## Steps

0. **State diagnosis** (only when `$ARGUMENTS` is empty — no commit message, no `--close`, no `--pr`):

   Check the following in order. Execute from the first incomplete step found:

   a. **Open PR on current branch**: Use `mcp__github__list_pull_requests(owner="yamakii", repo="garmin-performance-analysis", head="yamakii:{branch}", state="open")`. If a PR exists and is open → go to Step 1-PR (PR flow).

   b. **Uncommitted changes**: Run `git status --short`. If there are staged or unstaged changes → go to Step 1 (normal flow).

   c. **Unpushed commits**: Run `git log --oneline @{u}..HEAD` (an error means no upstream, i.e. unpushed). If there are commits → go to Step 3 (Push).

   d. **Pushed feature branch without a PR**: If the current branch is not `main` and has no open PR → create the PR (Step 3 note) and go to Step 1-PR.

   e. **Unclosed Issue**: Extract issue numbers from recent commits:
      ```bash
      git log -n 5 --format='%s %b' | grep -oE '#[0-9]+'
      ```
      For each extracted number, check if the issue is still open using `mcp__github__issue_read(method="get", owner="yamakii", repo="garmin-performance-analysis", issue_number=N)`. If any issue state is "open" → execute Step 4 (Close Issue) with that number.

   f. **All complete**: If none of the above apply → report 「全ステップ完了済みです。未完了の作業はありません。」 and stop.

   If `$ARGUMENTS` is not empty (commit message, `--close`, or `--pr` provided), skip Step 0 and follow the flow for the given flags.

---

## PR Flow (when `--pr` is specified or PR detected)

### Step 1-PR: CI 確認

まず **1 コマンドで ci-guard の完了を待つ**（`sleep` → `get_check_runs` の手動ループは使わない）:

```bash
bash scripts/wait-for-ci.sh {PR_NUMBER} --timeout 900   # run_in_background=true 推奨（CI は 5〜10 分）
```

exit 0 = `ci-guard` success、1 = failure 系、2 = timeout、3 = 環境エラー（`GITHUB_TOKEN` 無し等）。
exit 3 のときだけ MCP でポーリングする:

```
mcp__github__pull_request_read(method="get_check_runs", owner="yamakii", repo="garmin-performance-analysis", pullNumber={PR_NUMBER})
mcp__github__pull_request_read(method="get", owner="yamakii", repo="garmin-performance-analysis", pullNumber={PR_NUMBER})
```

`get_check_runs` は head commit の CI チェック（check-runs）を返す。required check `ci-guard` が `conclusion: "success"` ならマージ可。`web-backend` / `web-frontend` は `packages/garmin-web/**` 変更時のみ走り、それ以外は `conclusion: "skipped"`（正常）。

**`--validated` フラグあり**（Validation Agent PASS 済み）:
- 検証はやり直さない。マージ条件は `worktree-validation-protocol.md` §6 のゲート（`ci-guard` success + mergeable）のままで、pending なら完了を待ち、failure ならマージせずに報告する

**`--validated` フラグなし**:
- `ci-guard` の conclusion が success でなければマージしない（`web-*` の `skipped` は正常）
- checks が failing → report to user and stop (do not merge)

### Step 2-PR: Merge (merge commit — reason in `.claude/rules/dev/git.md` §1)

```
mcp__github__merge_pull_request(owner="yamakii", repo="garmin-performance-analysis", pullNumber={PR_NUMBER}, merge_method="merge")
```

Note: Branch deletion is handled by GitHub's auto-delete setting.

### Step 3-PR: ローカル同期 + クリーンアップ

`/workspace`（main の checkout）で `.claude/rules/dev/git.md` §2「マージ後」を実行する: ローカル main を
quiet fetch + ff-only で同期（`checkout main` / `git pull` は使わない）→ `bash scripts/cleanup-merged-worktrees.sh`。

> `worktree-agent-*`（`Agent(isolation: "worktree")` 由来）など ship 経由でない残留ブランチは
> `bash scripts/prune-merged-branches.sh` で一括掃除できる（`git branch -d` ベースで安全）。

cleanup の結果
（removed worktrees / deleted branches / skipped(理由付き)）をユーザーに報告する。**origin/main に
マージ済み かつ clean なものだけ**を削除し（`git worktree remove` は `--force` なし、`git branch -d`
で `-D` 禁止）、dirty・未マージは git が拒否＝残す。消せなかったものは warn のみでフローは止めない。

### Step 4-PR: Issue クローズ

If `--close` is specified, or PR body contains `Closes #N`:
- Extract issue number from PR body if not specified
- Execute Step 4 (Close Issue) with that number

If neither is present (a skip-level docs/rules PR shipped without an Issue, `dev-reference.md` §1),
there is nothing to close: report the merge and stop.

---

## Normal Flow (no PR)

1. **Review changes**: Run `git status --short` and `git diff --staged --stat`, then `git diff --staged -- <file>` only for the files you need to read, to understand what will be committed. If nothing is staged, show unstaged changes and ask what to stage.

2. **Commit**: Create a commit using Conventional Commits format. If the user provided a commit message as argument (before `--close`/`--pr`), use it. Otherwise, auto-generate from the diff.

   Format (the session attribution trailers are given by the harness at session start; use them verbatim):
   ```
   <type>: <description>

   <harness attribution trailer>
   ```

   If an issue number is known (`--close` or the branch name), put `Closes #<issue>` in the body:
   ```
   <type>: <description>

   Closes #<issue>

   <harness attribution trailer>
   ```

3. **Push**: the canonical push form in `.claude/rules/dev/git.md` §2 (no pre-push merge of origin/main).
   Pushing to `main` directly is blocked (branch protection + guard-push): a feature branch is merged only
   through a PR (PR Flow above). If no PR exists yet, create one with `mcp__github__create_pull_request`
   (body: `Closes #N` + `## Verification`) and continue with Step 1-PR.

4. **Close Issue** (if `--close` specified): After the PR is merged (the body's `Closes #` closes it; this step only covers the Change Log guard and an Issue that stayed open):

   a. **Change Log guard**: Check if the Issue body has a `## Change Log` section using `mcp__github__issue_read(method="get", owner="yamakii", repo="garmin-performance-analysis", issue_number={number})`.
      - If Change Log exists → proceed to close
      - If Change Log does NOT exist → append a minimal entry as fallback using `mcp__github__issue_write(method="update", ...)` with updated body containing:
        ```
        ## Change Log
        - YYYY-MM-DD (Ship): Closed via /ship
        ```
      - If update fails → warn and proceed (best-effort)

   b. **Close the Issue**:
      ```
      mcp__github__issue_write(method="update", owner="yamakii", repo="garmin-performance-analysis", issue_number={number}, state="closed")
      ```

   c. If the closed Issue is a sub-issue (has "Part of #XX" in body), show the Epic's updated progress using `mcp__github__issue_read(method="get", owner="yamakii", repo="garmin-performance-analysis", issue_number={epic-number})`.

## Arguments

$ARGUMENTS — Optional commit message and/or `--close <issue-number>` and/or `--pr <pr-number>` and/or `--validated`.

Examples:
- `/ship` — auto-diagnose state and execute appropriate step
- `/ship fix: correct form evaluation` — use provided message, push
- `/ship --close 51` — auto-generate message, push → PR → CI → merge, close #51
- `/ship feat: extract ApiClient --close 51` — use message, push, close #51
- `/ship --pr 42` — merge PR #42 via merge commit, sync local, cleanup worktree
- `/ship --pr 42 --close 51` — merge PR #42 + close Issue #51
- `/ship --pr 42 --validated` — merge PR #42 (Validation Agent PASS 済み。ci-guard success を待ってマージ)
- `/ship --pr 42 --validated --close 51` — merge + close (validated)
