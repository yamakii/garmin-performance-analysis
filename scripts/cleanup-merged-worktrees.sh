#!/usr/bin/env bash
# Safe cleanup of merged worktrees + local branches left behind by the
# worktree + auto-merge flow (.claude/worktrees/* and feat/*, worktree-*).
#
# Safety is the top priority (see .claude/rules/dev/dev-reference.md §7):
#   - `git worktree remove` is used WITHOUT `--force` → dirty worktrees are
#     refused by git and kept.
#   - `git branch -d` is used (never `-D`) → unmerged branches are refused by
#     git and kept.
#   - merge judgement is against `origin/main`.
#   - "remove only merged & clean; when in doubt, keep" is guaranteed.
#   - best-effort: anything that cannot be removed is warned about only; the
#     script keeps going and does not abort.
#
# Usage: scripts/cleanup-merged-worktrees.sh [--dry-run]   (run from repo root)
#   --dry-run : print the plan only; make no changes.
#
# Exit code: 0 normally. Non-zero only on hard errors (e.g. not a git repo).
set -euo pipefail

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=1
elif [ -n "${1:-}" ]; then
  echo "usage: $(basename "$0") [--dry-run]" >&2
  exit 2
fi

# Resolve repo root (hard error if not a git repo).
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# Accumulators for the final summary.
removed_worktrees=()
deleted_branches=()
skipped=()

run() {
  # Echo + execute, unless --dry-run (then echo with a [dry-run] marker).
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] would run: $*"
    return 0
  fi
  "$@"
}

# Extract the holder pid embedded in a worktree lock reason, or empty if none.
# Claude Code lock reasons look like: "claude agent <id> (pid <N> start <T>)".
lock_reason_pid() {
  printf '%s' "$1" | sed -n 's/.*pid \([0-9]\{1,\}\).*/\1/p'
}

# 0 if the lock reason carries a pid whose process is currently alive; 1 for a
# dead pid or no extractable pid. Lock holders are same-user claude agents, so
# `kill -0` succeeds on a live holder (no EPERM in practice) and a live lock is
# correctly kept.
lock_pid_alive() {
  local reason="$1" pid
  pid="$(lock_reason_pid "$reason")"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

# 1. Refresh remote refs (best-effort; keep going if offline).
if [ "$DRY_RUN" -eq 1 ]; then
  echo "[dry-run] would run: git fetch origin --prune"
else
  git fetch origin --prune --quiet 2>/dev/null || echo "warn: git fetch origin --prune failed, continuing with stale refs"
fi

# 2. Prune worktree admin entries whose dirs are already gone.
run git worktree prune

# Branch currently checked out in the main worktree (repo root) — never delete.
current_branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")"

# 3. Walk worktrees under .claude/worktrees/ (exclude main worktree = repo root).
#    Parse `git worktree list --porcelain`: blocks of "worktree <path>" / "branch <ref>".
wt_path=""
wt_branch=""
wt_locked_reason=""
process_worktree() {
  local path="$1" branch="$2" locked_reason="$3"
  [ -z "$path" ] && return 0
  # Only manage worktrees under .claude/worktrees/ (relative to repo root).
  case "$path" in
    "$ROOT/.claude/worktrees/"*) ;;
    *) return 0 ;;
  esac
  # Never touch the main worktree itself.
  [ "$path" = "$ROOT" ] && return 0

  # Dirty check: keep anything with uncommitted changes.
  if [ -n "$(git -C "$path" status --porcelain 2>/dev/null)" ]; then
    skipped+=("$path (dirty, kept)")
    echo "warn: $path dirty, kept"
    return 0
  fi

  # Merge check: the worktree HEAD branch must be merged into origin/main.
  local short="${branch#refs/heads/}"
  if [ -z "$short" ]; then
    skipped+=("$path (detached HEAD, kept)")
    echo "warn: $path detached HEAD, kept"
    return 0
  fi
  if git merge-base --is-ancestor "$short" origin/main 2>/dev/null; then
    if [ -n "$locked_reason" ]; then
      # Merged & clean but locked: distinguish an active lock (holder alive →
      # keep) from a stale lock (holder gone → reclaim). Conservative: keep
      # whenever the holder may still be alive or no pid can be checked.
      if lock_pid_alive "$locked_reason"; then
        skipped+=("$path (locked active, kept)")
        echo "warn: $path locked (holder pid alive), kept"
      elif [ -n "$(lock_reason_pid "$locked_reason")" ]; then
        # Pid extracted but the process is gone → stale lock, safe to reclaim.
        if [ "$DRY_RUN" -eq 1 ]; then
          echo "[dry-run] would clear stale lock and remove: $path"
          skipped+=("$path (stale lock, would clear)")
        elif git worktree unlock "$path" 2>/dev/null && git worktree remove "$path"; then
          removed_worktrees+=("$path")
          echo "info: $path stale lock cleared, removed"
        else
          skipped+=("$path (stale lock clear failed, kept)")
          echo "warn: $path stale lock clear failed, kept"
        fi
      else
        # Locked with no pid in the reason → cannot verify liveness, keep.
        skipped+=("$path (locked unknown, kept)")
        echo "warn: $path locked (no pid in reason), kept"
      fi
    elif run git worktree remove "$path"; then
      removed_worktrees+=("$path")
    else
      skipped+=("$path (remove failed, kept)")
      echo "warn: $path worktree remove failed, kept"
    fi
  else
    skipped+=("$path ($short unmerged, kept)")
    echo "warn: $path branch $short not merged into origin/main, kept"
  fi
}

while IFS= read -r line; do
  case "$line" in
    "worktree "*) wt_path="${line#worktree }" ;;
    "branch "*) wt_branch="${line#branch }" ;;
    "locked "*) wt_locked_reason="${line#locked }" ;;
    "locked") wt_locked_reason="(no reason)" ;;
    "")
      process_worktree "$wt_path" "$wt_branch" "$wt_locked_reason"
      wt_path=""
      wt_branch=""
      wt_locked_reason=""
      ;;
  esac
done < <(git worktree list --porcelain)
# Flush the last block (porcelain output may not end with a blank line).
process_worktree "$wt_path" "$wt_branch" "$wt_locked_reason"

# 4. Delete local branches merged into origin/main (exclude main + current).
#    `git branch -d` refuses unmerged branches, so this is safe by construction.
while IFS= read -r b; do
  b="${b#"${b%%[![:space:]]*}"}"   # ltrim
  [ -z "$b" ] && continue
  case "$b" in
    main | master | "$current_branch") continue ;;
  esac
  if run git branch -d "$b"; then
    deleted_branches+=("$b")
  else
    skipped+=("branch $b (delete failed, kept)")
    echo "warn: branch $b delete failed, kept"
  fi
done < <(git branch --merged origin/main --format='%(refname:short)')

# 5. Summary (single block at the end).
echo ""
if [ "$DRY_RUN" -eq 1 ]; then
  echo "=== cleanup-merged-worktrees summary (dry-run) ==="
else
  echo "=== cleanup-merged-worktrees summary ==="
fi
echo "removed worktrees: ${#removed_worktrees[@]}"
for w in "${removed_worktrees[@]:-}"; do [ -n "$w" ] && echo "  - $w"; done
echo "deleted branches: ${#deleted_branches[@]}"
for d in "${deleted_branches[@]:-}"; do [ -n "$d" ] && echo "  - $d"; done
echo "skipped: ${#skipped[@]}"
for s in "${skipped[@]:-}"; do [ -n "$s" ] && echo "  - $s"; done

exit 0
