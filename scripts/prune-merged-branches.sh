#!/usr/bin/env bash
# Prune local branches left behind after PRs merge.
#
# Two classes are removed:
#   1. Local branches whose upstream is gone — the PR was merged and GitHub
#      auto-deleted the remote branch (`: gone]` in `git branch -vv`).
#   2. Merged `worktree-agent-*` branches — residue from Agent(isolation:
#      "worktree") runs whose worktree was auto-removed but branch left behind.
#
# Safe by construction: deletion uses `git branch -d`, which refuses to delete
# a branch not merged into HEAD. Unmerged work is never lost. main/master are
# always excluded.
set -uo pipefail

cd "$(git rev-parse --show-toplevel)" || exit 1

git fetch --prune --quiet origin 2>/dev/null || true

# 1. upstream-gone branches (PR merged + remote auto-deleted)
gone=$(git branch -vv | awk '/: gone]/ {print $1}' | grep -vx '*' || true)

# 2. merged worktree-agent-* branches (Agent isolation residue)
agent=$(git branch --merged main | sed 's/^[ *]*//' | grep -E '^worktree-agent-' || true)

candidates=$(printf '%s\n%s\n' "$gone" "$agent" | sort -u | grep -vE '^$|^main$|^master$' || true)

deleted=0
skipped=0
for b in $candidates; do
  if git branch -d "$b" 2>/dev/null; then
    echo "deleted: $b"
    deleted=$((deleted + 1))
  else
    echo "skipped (unmerged or in use): $b" >&2
    skipped=$((skipped + 1))
  fi
done

git worktree prune 2>/dev/null || true

echo "pruned ${deleted} branch(es), skipped ${skipped}."
