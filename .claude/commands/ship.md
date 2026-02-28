---
allowed-tools: Bash, Read, Glob, Grep
description: Commit and push changes
user-invocable: true
---

# /ship — Commit & Push Workflow

Run the full ship workflow for the current changes.

## Steps

0. **State diagnosis** (only when `$ARGUMENTS` is empty — no commit message, no `--close`, no `--pr`):

   Check the following in order. Execute from the first incomplete step found:

   a. **Open PR on current branch**: Run `gh pr view --json number,state 2>/dev/null`. If a PR exists and is open → go to Step 1-PR (PR flow).

   b. **Uncommitted changes**: Run `git status`. If there are staged or unstaged changes → go to Step 1 (normal flow).

   c. **Unpushed commits**: Run `git log origin/$(git branch --show-current)..HEAD --oneline`. If there are commits → go to Step 3 (Push).

   d. **Unmerged feature branch**: If currently on a `feature/*` branch, or `git branch --list 'feature/*'` shows unmerged feature branches → go to Step 4 (Merge & cleanup).

   e. **Unclosed Issue**: Extract issue numbers from recent commits:
      ```bash
      git log --oneline -5 | grep -oP '\(#\K[0-9]+(?=\))'
      ```
      For each extracted number, check if the issue is still open:
      ```bash
      gh issue view {number} --json state --jq '.state'
      ```
      If any issue is OPEN → execute Step 5 (Close Issue) with that number.

   f. **All complete**: If none of the above apply → report 「全ステップ完了済みです。未完了の作業はありません。」 and stop.

   If `$ARGUMENTS` is not empty (commit message, `--close`, or `--pr` provided), skip Step 0 entirely and proceed as before.

---

## PR Flow (when `--pr` is specified or PR detected)

### Step 1-PR: CI 確認

```bash
gh pr checks {PR_NUMBER}
gh pr view {PR_NUMBER} --json mergeable,statusCheckRollup
```

If checks are failing, report to user and stop (do not merge).

### Step 2-PR: Merge (merge commit, TDD 履歴保持)

```bash
gh pr merge {PR_NUMBER} --merge --delete-branch
```

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

   a. **Change Log guard**: Check if the Issue body has a `## Change Log` section:
      ```bash
      CURRENT_BODY=$(gh issue view {number} --json body --jq '.body')
      ```
      - If Change Log exists → proceed to close
      - If Change Log does NOT exist → append a minimal entry as fallback:
        ```bash
        # Append Change Log section with minimal entry
        # - YYYY-MM-DD (Ship): Closed via /ship
        printf '%s' "$NEW_BODY" | gh issue edit {number} --body-file -
        ```
      - If `gh issue edit` fails → warn and proceed (best-effort, see `.claude/rules/dev/dev-standards.md`)

   b. **Close the Issue**:
      ```bash
      gh issue close {number}
      ```

   c. If the closed Issue is a sub-issue (has "Part of #XX" in body), show the Epic's updated progress:
      ```bash
      gh issue view {epic-number} --json body
      ```

## Arguments

$ARGUMENTS — Optional commit message and/or `--close <issue-number>` and/or `--pr <pr-number>`.

Examples:
- `/ship` — auto-diagnose state and execute appropriate step
- `/ship fix: correct form evaluation` — use provided message, push
- `/ship --close 51` — auto-generate message, push, close #51
- `/ship feat: extract ApiClient --close 51` — use message, push, close #51
- `/ship --pr 42` — merge PR #42 via merge commit, sync local, cleanup worktree
- `/ship --pr 42 --close 51` — merge PR #42 + close Issue #51
