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

3. **Commit**: Create a commit using Conventional Commits format. If the user provided a commit message as argument, use it. Otherwise, auto-generate from the diff.

   Format:
   ```
   <type>: <description>

   Co-Authored-By: Claude <noreply@anthropic.com>
   ```

4. **Push**: Run `git push` to push to remote.

## Arguments

$ARGUMENTS — Optional commit message. If not provided, auto-generate from diff.
