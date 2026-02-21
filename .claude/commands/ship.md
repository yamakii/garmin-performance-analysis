---
allowed-tools: Bash, Read, Glob, Grep
description: Commit, quality check, and push changes
user-invocable: true
---

# /ship — Commit & Push Workflow

Run the full ship workflow for the current changes.

## Steps

1. **Review changes**: Run `git status` and `git diff --staged` to understand what will be committed. If nothing is staged, show unstaged changes and ask what to stage.

2. **Quality check**: Run `uv run pre-commit run --files <changed-files>` on all modified files. If any check fails, fix the issues and re-run.

3. **Commit**: Create a commit using Conventional Commits format. If the user provided a commit message as argument (before `--close`), use it. Otherwise, auto-generate from the diff.

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

4. **Push**: Run `git push` to push to remote. If no upstream is set, use `git push -u origin <branch>`.

5. **Merge & cleanup** (if on a feature branch):
   ```bash
   # Merge to main
   cd /home/yamakii/workspace/garmin-performance-analysis
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

6. **Close Issue** (if `--close` specified): After successful push, close the specified GitHub Issue:
   ```bash
   gh issue close {number}
   ```

   If the closed Issue is a sub-issue (has "Part of #XX" in body), show the Epic's updated progress:
   ```bash
   gh issue view {epic-number} --json body
   ```

## Arguments

$ARGUMENTS — Optional commit message and/or `--close <issue-number>`.

Examples:
- `/ship` — auto-generate commit message, push
- `/ship fix: correct form evaluation` — use provided message, push
- `/ship --close 51` — auto-generate message, push, close #51
- `/ship feat: extract ApiClient --close 51` — use message, push, close #51
