#!/usr/bin/env bash
# Self-test for scripts/cleanup-merged-worktrees.sh.
#
# Each test builds an independent temp git repo (with a local bare `origin` so
# that `origin/main` exists), sets up worktrees/branches, runs the cleanup
# script, and asserts the safe behavior. Independent temp repos make the tests
# parallel-safe and order-independent.
#
# Usage: bash scripts/tests/test-cleanup-merged-worktrees.sh   (run from repo root)
# Exit 0 if all cases pass; prints the failing expectation and exits 1 otherwise.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CLEANUP="$SCRIPT_DIR/cleanup-merged-worktrees.sh"

failures=0

fail() {
  echo "  FAIL: $*" >&2
  failures=$((failures + 1))
}

# Build a temp repo with a bare origin holding `main`. Echoes the work repo path.
setup_repo() {
  local base work bare
  base="$(mktemp -d)"
  work="$base/work"
  bare="$base/origin.git"

  git init --quiet --bare "$bare"

  git init --quiet -b main "$work"
  git -C "$work" config user.email "test@example.com"
  git -C "$work" config user.name "Test"
  git -C "$work" commit --quiet --allow-empty -m "init"
  git -C "$work" remote add origin "$bare"
  git -C "$work" push --quiet -u origin main 2>/dev/null

  echo "$work"
}

# Create a worktree under .claude/worktrees/<name> on a NEW branch <branch>.
add_worktree() {
  local work="$1" name="$2" branch="$3"
  git -C "$work" worktree add --quiet -b "$branch" ".claude/worktrees/$name" 2>/dev/null
}

# Make a worktree's <branch> merged into origin/main. The branch is checked out
# in the worktree at <wt_dir>, so commit there (the main worktree cannot check
# it out), then merge from main and push.
merge_worktree_branch_into_origin_main() {
  local work="$1" wt_dir="$2" branch="$3"
  git -C "$work/$wt_dir" commit --quiet --allow-empty -m "work on $branch"
  git -C "$work" merge --quiet --no-ff "$branch" -m "merge $branch"
  git -C "$work" push --quiet origin main 2>/dev/null
}

run_cleanup() {
  local work="$1"
  shift
  ( cd "$work" && bash "$CLEANUP" "$@" )
}

# ---------------------------------------------------------------------------

test_removes_merged_clean_worktree() {
  echo "test_removes_merged_clean_worktree"
  local work; work="$(setup_repo)"
  add_worktree "$work" "feat-x" "feat/x"
  merge_worktree_branch_into_origin_main "$work" ".claude/worktrees/feat-x" "feat/x"

  run_cleanup "$work" >/dev/null 2>&1

  [ -d "$work/.claude/worktrees/feat-x" ] && fail "worktree dir should be gone"
  if git -C "$work" worktree list --porcelain | grep -q "feat-x"; then
    fail "worktree should be unregistered"
  fi
}

test_keeps_dirty_worktree() {
  echo "test_keeps_dirty_worktree"
  local work; work="$(setup_repo)"
  add_worktree "$work" "feat-dirty" "feat/dirty"
  merge_worktree_branch_into_origin_main "$work" ".claude/worktrees/feat-dirty" "feat/dirty"
  # Introduce an uncommitted change in the worktree.
  echo "scratch" > "$work/.claude/worktrees/feat-dirty/dirty.txt"

  run_cleanup "$work" >/dev/null 2>&1

  [ -d "$work/.claude/worktrees/feat-dirty" ] || fail "dirty worktree dir should be kept"
  git -C "$work" worktree list --porcelain | grep -q "feat-dirty" || fail "dirty worktree should stay registered"
}

test_keeps_unmerged_branch() {
  echo "test_keeps_unmerged_branch"
  local work; work="$(setup_repo)"
  git -C "$work" checkout --quiet -b feat/unmerged
  git -C "$work" commit --quiet --allow-empty -m "unmerged work"
  git -C "$work" checkout --quiet main

  run_cleanup "$work" >/dev/null 2>&1

  git -C "$work" branch --list "feat/unmerged" | grep -q "feat/unmerged" \
    || fail "unmerged branch should be kept"
}

test_deletes_merged_branch() {
  echo "test_deletes_merged_branch"
  local work; work="$(setup_repo)"
  git -C "$work" checkout --quiet -b feat/merged
  git -C "$work" commit --quiet --allow-empty -m "merged work"
  git -C "$work" checkout --quiet main
  git -C "$work" merge --quiet --no-ff feat/merged -m "merge feat/merged"
  git -C "$work" push --quiet origin main 2>/dev/null

  run_cleanup "$work" >/dev/null 2>&1

  if git -C "$work" branch --list "feat/merged" | grep -q "feat/merged"; then
    fail "merged branch should be deleted"
  fi
}

test_never_touches_main_or_current() {
  echo "test_never_touches_main_or_current"
  local work; work="$(setup_repo)"
  # Current branch is a merged feature branch checked out in the main worktree.
  git -C "$work" checkout --quiet -b feat/current
  git -C "$work" commit --quiet --allow-empty -m "current work"
  git -C "$work" checkout --quiet main
  git -C "$work" merge --quiet --no-ff feat/current -m "merge feat/current"
  git -C "$work" push --quiet origin main 2>/dev/null
  git -C "$work" checkout --quiet feat/current   # current = feat/current (merged)

  run_cleanup "$work" >/dev/null 2>&1

  git -C "$work" branch --list "main" | grep -q "main" || fail "main must always be kept"
  git -C "$work" branch --list "feat/current" | grep -q "feat/current" \
    || fail "current branch must always be kept (even if merged)"
}

test_dry_run_makes_no_changes() {
  echo "test_dry_run_makes_no_changes"
  local work; work="$(setup_repo)"
  add_worktree "$work" "feat-dry" "feat/dry"
  merge_worktree_branch_into_origin_main "$work" ".claude/worktrees/feat-dry" "feat/dry"

  run_cleanup "$work" --dry-run >/dev/null 2>&1

  [ -d "$work/.claude/worktrees/feat-dry" ] || fail "--dry-run must not remove worktree"
  git -C "$work" worktree list --porcelain | grep -q "feat-dry" \
    || fail "--dry-run must keep worktree registered"
  git -C "$work" branch --list "feat/dry" | grep -q "feat/dry" \
    || fail "--dry-run must keep branch"
}

# A pid guaranteed not to be running (portable "dead holder").
DEAD_PID=999999

test_stale_locked_merged_worktree_removed() {
  echo "test_stale_locked_merged_worktree_removed"
  local work; work="$(setup_repo)"
  add_worktree "$work" "feat-stale" "feat/stale"
  merge_worktree_branch_into_origin_main "$work" ".claude/worktrees/feat-stale" "feat/stale"
  # Lock with a reason carrying a dead holder pid → stale.
  git -C "$work" worktree lock \
    --reason "claude agent x (pid $DEAD_PID start 0)" ".claude/worktrees/feat-stale"

  run_cleanup "$work" >/dev/null 2>&1

  [ -d "$work/.claude/worktrees/feat-stale" ] && fail "stale locked worktree should be removed"
  if git -C "$work" worktree list --porcelain | grep -q "feat-stale"; then
    fail "stale locked worktree should be unregistered"
  fi
  if git -C "$work" branch --list "feat/stale" | grep -q "feat/stale"; then
    fail "branch of stale locked worktree should be deleted"
  fi
}

test_active_locked_worktree_kept() {
  echo "test_active_locked_worktree_kept"
  local work; work="$(setup_repo)"
  add_worktree "$work" "feat-active" "feat/active"
  merge_worktree_branch_into_origin_main "$work" ".claude/worktrees/feat-active" "feat/active"
  # Spawn a live child and embed its pid in the lock reason → active.
  sleep 300 &
  local live_pid=$!
  git -C "$work" worktree lock \
    --reason "claude agent x (pid $live_pid start 0)" ".claude/worktrees/feat-active"

  run_cleanup "$work" >/dev/null 2>&1

  [ -d "$work/.claude/worktrees/feat-active" ] \
    || fail "active locked worktree should be kept"
  git -C "$work" worktree list --porcelain | grep -q "feat-active" \
    || fail "active locked worktree should stay registered"

  kill "$live_pid" 2>/dev/null
  wait "$live_pid" 2>/dev/null
}

test_locked_without_pid_kept() {
  echo "test_locked_without_pid_kept"
  local work; work="$(setup_repo)"
  add_worktree "$work" "feat-nopid" "feat/nopid"
  merge_worktree_branch_into_origin_main "$work" ".claude/worktrees/feat-nopid" "feat/nopid"
  # Lock reason without any pid → conservative keep.
  git -C "$work" worktree lock --reason "manual hold" ".claude/worktrees/feat-nopid"

  run_cleanup "$work" >/dev/null 2>&1

  [ -d "$work/.claude/worktrees/feat-nopid" ] \
    || fail "locked worktree without pid should be kept"
  git -C "$work" worktree list --porcelain | grep -q "feat-nopid" \
    || fail "locked worktree without pid should stay registered"
}

test_dry_run_does_not_unlock() {
  echo "test_dry_run_does_not_unlock"
  local work; work="$(setup_repo)"
  add_worktree "$work" "feat-dryst" "feat/dryst"
  merge_worktree_branch_into_origin_main "$work" ".claude/worktrees/feat-dryst" "feat/dryst"
  git -C "$work" worktree lock \
    --reason "claude agent x (pid $DEAD_PID start 0)" ".claude/worktrees/feat-dryst"

  run_cleanup "$work" --dry-run >/dev/null 2>&1

  [ -d "$work/.claude/worktrees/feat-dryst" ] \
    || fail "--dry-run must not remove stale locked worktree"
  # Still locked: porcelain should report the lock attribute.
  if ! git -C "$work" worktree list --porcelain | grep -q "^locked"; then
    fail "--dry-run must not unlock stale locked worktree"
  fi
}

# ---------------------------------------------------------------------------

test_removes_merged_clean_worktree
test_keeps_dirty_worktree
test_keeps_unmerged_branch
test_deletes_merged_branch
test_never_touches_main_or_current
test_dry_run_makes_no_changes
test_stale_locked_merged_worktree_removed
test_active_locked_worktree_kept
test_locked_without_pid_kept
test_dry_run_does_not_unlock

if [ "$failures" -ne 0 ]; then
  echo "test-cleanup-merged-worktrees: FAILED ($failures failure(s))" >&2
  exit 1
fi
echo "test-cleanup-merged-worktrees: all cases passed"
exit 0
