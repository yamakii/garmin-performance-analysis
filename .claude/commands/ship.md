---
allowed-tools: Bash, Read, Glob, Grep, mcp__github__get_pull_request, mcp__github__get_pull_request_status, mcp__github__merge_pull_request, mcp__github__get_issue, mcp__github__update_issue
description: Commit and push changes
user-invocable: true
---

# /ship — Commit & Push Workflow

Run the full ship workflow for the current changes.

## Steps

0. **State diagnosis** (only when `$ARGUMENTS` is empty — no commit message, no `--close`, no `--pr`):

   Check the following in order. Execute from the first incomplete step found:

   a. **Open PR on current branch**: Use `mcp__github__list_pull_requests(owner="yamakii", repo="garmin-performance-analysis", head="yamakii:{branch}", state="open")`. If a PR exists and is open → go to Step 1-PR (PR flow).

   b. **Uncommitted changes**: Run `git status`. If there are staged or unstaged changes → go to Step 1 (normal flow).

   c. **Unpushed commits**: Run `git log origin/$(git branch --show-current)..HEAD --oneline`. If there are commits → go to Step 3 (Push).

   d. **Unmerged feature branch**: If currently on a `feature/*` branch, or `git branch --list 'feature/*'` shows unmerged feature branches → go to Step 4 (Merge & cleanup).

   e. **Unclosed Issue**: Extract issue numbers from recent commits:
      ```bash
      git log --oneline -5 | grep -oP '\(#\K[0-9]+(?=\))'
      ```
      For each extracted number, check if the issue is still open using `mcp__github__get_issue(owner="yamakii", repo="garmin-performance-analysis", issue_number=N)`. If any issue state is "open" → execute Step 5 (Close Issue) with that number.

   f. **All complete**: If none of the above apply → report 「全ステップ完了済みです。未完了の作業はありません。」 and stop.

   If `$ARGUMENTS` is not empty (commit message, `--close`, or `--pr` provided), skip Step 0 entirely and proceed as before.

---

## PR Flow (when `--pr` is specified or PR detected)

### Step 1-PR: CI 確認

```
mcp__github__get_pull_request_status(owner="yamakii", repo="garmin-performance-analysis", pull_number={PR_NUMBER})
mcp__github__get_pull_request(owner="yamakii", repo="garmin-performance-analysis", pull_number={PR_NUMBER})
```

**`--validated` フラグあり**（Validation Agent PASS 済み）:
- CI ステータスを確認するが、pending/running でもマージ可能
- CI failing の場合のみ WARNING を表示（ブロックしない）

**`--validated` フラグなし**（従来動作）:
- CI checks が全て pass していなければマージしない
- checks が failing → report to user and stop (do not merge)

### Step 2-PR: Merge (merge commit, TDD 履歴保持)

```
mcp__github__merge_pull_request(owner="yamakii", repo="garmin-performance-analysis", pull_number={PR_NUMBER}, merge_method="merge")
```

Note: Branch deletion is handled by GitHub's auto-delete setting.

### Step 3-PR: ローカル同期 + クリーンアップ

```bash
git checkout main
git pull

# Remove worktree if it exists
git worktree remove ../garmin-{name} 2>/dev/null || true
```

### Step 4-PR: Issue クローズ

If `--close` is specified, or PR body contains `Closes #N`:
- Extract issue number from PR body if not specified
- Execute Step 5 (Close Issue) with that number

---

## Normal Flow (no PR)

1. **Review changes**: Run `git status` and `git diff --staged` to understand what will be committed. If nothing is staged, show unstaged changes and ask what to stage.

2. **Commit**: Create a commit using Conventional Commits format. If the user provided a commit message as argument (before `--close`/`--pr`), use it. Otherwise, auto-generate from the diff.

   Format:
   ```
   <type>: <description>

   Co-Authored-By: Claude <noreply@anthropic.com>
   ```

   If `--close` is used with an issue number, include it in the commit message:
   ```
   <type>: <description> (#issue-number)

   Co-Authored-By: Claude <noreply@anthropic.com>
   ```

3. **Push**: Run `git push` to push to remote. If no upstream is set, use `git push -u origin <branch>`.

4. **Merge & cleanup** (if on a feature branch):
   ```bash
   # Merge to main
   cd $(git rev-parse --show-toplevel)
   git merge --no-ff feature/{name}

   # Push main
   git push

   # Delete remote and local feature branch
   git push origin --delete feature/{name}
   git branch -d feature/{name}

   # Remove worktree if it exists
   git worktree remove ../garmin-{name} 2>/dev/null || true
   ```

   If on main branch (no feature branch), skip this step.

5. **Close Issue** (if `--close` specified): After successful push:

   a. **Change Log guard**: Check if the Issue body has a `## Change Log` section using `mcp__github__get_issue(owner="yamakii", repo="garmin-performance-analysis", issue_number={number})`.
      - If Change Log exists → proceed to close
      - If Change Log does NOT exist → append a minimal entry as fallback using `mcp__github__update_issue` with updated body containing:
        ```
        ## Change Log
        - YYYY-MM-DD (Ship): Closed via /ship
        ```
      - If update fails → warn and proceed (best-effort)

   b. **Close the Issue**:
      ```
      mcp__github__update_issue(owner="yamakii", repo="garmin-performance-analysis", issue_number={number}, state="closed")
      ```

   c. If the closed Issue is a sub-issue (has "Part of #XX" in body), show the Epic's updated progress using `mcp__github__get_issue(owner="yamakii", repo="garmin-performance-analysis", issue_number={epic-number})`.

## Arguments

$ARGUMENTS — Optional commit message and/or `--close <issue-number>` and/or `--pr <pr-number>` and/or `--validated`.

Examples:
- `/ship` — auto-diagnose state and execute appropriate step
- `/ship fix: correct form evaluation` — use provided message, push
- `/ship --close 51` — auto-generate message, push, close #51
- `/ship feat: extract ApiClient --close 51` — use message, push, close #51
- `/ship --pr 42` — merge PR #42 via merge commit, sync local, cleanup worktree
- `/ship --pr 42 --close 51` — merge PR #42 + close Issue #51
- `/ship --pr 42 --validated` — merge PR #42 (Validation Agent PASS 済み、CI pending でも可)
- `/ship --pr 42 --validated --close 51` — merge + close (validated)
