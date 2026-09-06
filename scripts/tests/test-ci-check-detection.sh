#!/usr/bin/env bash
# Self-test for the change detection in scripts/ci-check.sh (#1003).
#
# Hermetic: every case builds a throwaway git repo in a tmpdir and copies
# ci-check.sh into its scripts/ dir, so the script's own ROOT resolves to that
# repo. `--detect-only` prints the decision and exits before running any check,
# so no venv, no network and no toolchain are needed.
#
# Output contract asserted here (one line each):
#   base=<ref|none>
#   web=<yes|no>
#
# Usage: bash scripts/tests/test-ci-check-detection.sh   (run from repo root)
# Exit 0 if all cases pass; prints failing expectations and exits 1 otherwise.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CI_CHECK="$SCRIPT_DIR/ci-check.sh"

failures=0
fail() { echo "  FAIL: $*" >&2; failures=$((failures + 1)); }

WEB_FILE="packages/garmin-web/src/app.py"
SERVER_FILE="packages/garmin-mcp-server/src/reader.py"

# make_repo <dir> — a repo on `main` with one commit touching both packages.
make_repo() {
  local dir="$1"
  mkdir -p "$dir/scripts" "$dir/$(dirname "$WEB_FILE")" "$dir/$(dirname "$SERVER_FILE")"
  cp "$CI_CHECK" "$dir/scripts/ci-check.sh"
  echo "web v1" >"$dir/$WEB_FILE"
  echo "server v1" >"$dir/$SERVER_FILE"
  git -C "$dir" -c init.defaultBranch=main init --quiet
  git -C "$dir" config user.email ci-check-test@example.invalid
  git -C "$dir" config user.name "ci-check test"
  git -C "$dir" add -A
  git -C "$dir" commit --quiet -m "initial"
}

# detect <dir> <key> — run --detect-only and echo the value of `key`.
detect() {
  local dir="$1" key="$2" out
  out="$(bash "$dir/scripts/ci-check.sh" --detect-only 2>/dev/null)"
  sed -n "s/^$key=//p" <<<"$out"
}

expect() {  # expect <label> <actual> <wanted>
  if [ "$2" != "$3" ]; then
    fail "$1: got '$2', want '$3'"
  fi
}

# --- an uncommitted edit to a tracked web file must be detected --------------
test_detects_uncommitted_web_edit() {
  local dir="$1"
  make_repo "$dir"
  echo "web v2 (uncommitted)" >"$dir/$WEB_FILE"

  expect "uncommitted web edit" "$(detect "$dir" web)" "yes"
}

# --- an untracked new web file must be detected ------------------------------
test_detects_untracked_web_file() {
  local dir="$1"
  make_repo "$dir"
  echo "brand new" >"$dir/packages/garmin-web/new.ts"

  expect "untracked web file" "$(detect "$dir" web)" "yes"
}

# --- a server-only change must NOT trigger the web checks --------------------
test_no_web_change_reports_no() {
  local dir="$1"
  make_repo "$dir"
  echo "server v2 (uncommitted)" >"$dir/$SERVER_FILE"

  expect "server-only change" "$(detect "$dir" web)" "no"
}

# --- a stale local `main` must not resurrect someone else's web commit -------
# origin/main carries a web commit the branch merely inherits; the branch itself
# touches no web file. The old `main...HEAD` test reported yes because local
# `main` was left behind that commit.
test_prefers_origin_main_over_stale_local_main() {
  local dir="$1"
  make_repo "$dir"
  local base_sha
  base_sha="$(git -C "$dir" rev-parse HEAD)"

  # Someone else's merged web change.
  echo "web v2 (merged upstream)" >"$dir/$WEB_FILE"
  git -C "$dir" commit --quiet -am "upstream web change"
  git -C "$dir" update-ref refs/remotes/origin/main HEAD

  # Our branch continues from it, touching only the server package...
  git -C "$dir" checkout --quiet -b feature
  echo "server v2" >"$dir/$SERVER_FILE"
  git -C "$dir" commit --quiet -am "server change"

  # ...while local `main` is still behind the upstream commit.
  git -C "$dir" branch --force main "$base_sha"

  expect "stale main: base" "$(detect "$dir" base)" "origin/main"
  expect "stale main: web" "$(detect "$dir" web)" "no"

  # Guard the regression itself: the old base really would have said yes.
  local old
  old="$(git -C "$dir" diff --name-only main...HEAD | grep -c '^packages/garmin-web/')"
  if [ "$old" -eq 0 ]; then
    fail "stale main: fixture no longer reproduces the old false positive"
  fi
}

# --- without an origin/main ref, fall back to local main ---------------------
test_falls_back_to_local_main_without_origin() {
  local dir="$1"
  make_repo "$dir"
  echo "web v2 (uncommitted)" >"$dir/$WEB_FILE"

  expect "no origin: base" "$(detect "$dir" base)" "main"
  expect "no origin: web" "$(detect "$dir" web)" "yes"
}

TMPROOT="$(mktemp -d)"
trap 'rm -rf "$TMPROOT"' EXIT

for t in \
  test_detects_uncommitted_web_edit \
  test_detects_untracked_web_file \
  test_no_web_change_reports_no \
  test_prefers_origin_main_over_stale_local_main \
  test_falls_back_to_local_main_without_origin; do
  echo "• $t"
  "$t" "$TMPROOT/$t"
done

if [ "$failures" -ne 0 ]; then
  echo "test-ci-check-detection: $failures failure(s)" >&2
  exit 1
fi

echo "test-ci-check-detection: all cases passed"
exit 0
