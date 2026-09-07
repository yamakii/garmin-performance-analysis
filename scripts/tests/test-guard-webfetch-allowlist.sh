#!/usr/bin/env bash
# Self-test for .claude/hooks/guard-webfetch-allowlist.sh (#1035): the PreToolUse
# hook that turns a silently blocked WebFetch into an explained block.
#
# Feeds hook JSON on stdin against a temp allowlist (SANDBOX_ALLOWLIST), so it
# needs no container, no DNS and no network.
#
# Usage: bash scripts/tests/test-guard-webfetch-allowlist.sh   (run from repo root)
# Exit 0 if all cases pass; prints the failing expectation and exits 1 otherwise.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOOK="$ROOT/.claude/hooks/guard-webfetch-allowlist.sh"

failures=0
fail() {
  echo "  FAIL: $*" >&2
  failures=$((failures + 1))
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
printf '# comment\nduckdb.org\nGitHub.com  # trailing\ngithubusercontent.com\n' >"$tmp/allow.txt"

# run_hook ALLOWLIST URL  → prints the hook's exit code; stderr lands in $tmp/err
run_hook() {
  local json
  if [ -n "$2" ]; then
    json="{\"tool_name\":\"WebFetch\",\"tool_input\":{\"url\":\"$2\",\"prompt\":\"x\"}}"
  else
    json='{"tool_name":"WebFetch","tool_input":{"prompt":"x"}}'
  fi
  printf '%s' "$json" | SANDBOX_ALLOWLIST="$1" bash "$HOOK" 2>"$tmp/err"
  echo $?
}

# --- test_hook_allows_listed_apex ---------------------------------------------
if [ "$(run_hook "$tmp/allow.txt" "https://duckdb.org/docs/stable/sql")" = 0 ]; then
  echo "  ok: test_hook_allows_listed_apex"
else
  fail "test_hook_allows_listed_apex: $(cat "$tmp/err")"
fi

# --- test_hook_allows_subdomain -----------------------------------------------
if [ "$(run_hook "$tmp/allow.txt" "https://raw.githubusercontent.com/o/r/main/x")" = 0 ] \
   && [ "$(run_hook "$tmp/allow.txt" "https://API.GitHub.com/zen")" = 0 ]; then
  echo "  ok: test_hook_allows_subdomain"
else
  fail "test_hook_allows_subdomain: $(cat "$tmp/err")"
fi

# --- test_hook_blocks_unlisted ------------------------------------------------
rc="$(run_hook "$tmp/allow.txt" "https://readthedocs.io/en/latest/")"
if [ "$rc" = 2 ] && grep -q "readthedocs.io" "$tmp/err" && grep -q "allowed-domains.txt" "$tmp/err"; then
  echo "  ok: test_hook_blocks_unlisted"
else
  fail "test_hook_blocks_unlisted: rc=$rc stderr='$(cat "$tmp/err")'"
fi

# --- test_hook_no_false_suffix_match ------------------------------------------
if [ "$(run_hook "$tmp/allow.txt" "https://notduckdb.org/")" = 2 ]; then
  echo "  ok: test_hook_no_false_suffix_match"
else
  fail "test_hook_no_false_suffix_match: notduckdb.org was allowed"
fi

# --- test_hook_noop_outside_container -----------------------------------------
if [ "$(run_hook "$tmp/does-not-exist.txt" "https://readthedocs.io/")" = 0 ]; then
  echo "  ok: test_hook_noop_outside_container"
else
  fail "test_hook_noop_outside_container: blocked without an image-baked allowlist"
fi

# --- test_hook_noop_without_url -----------------------------------------------
if [ "$(run_hook "$tmp/allow.txt" "")" = 0 ]; then
  echo "  ok: test_hook_noop_without_url"
else
  fail "test_hook_noop_without_url"
fi

# --- test_hook_matches_shipped_allowlist --------------------------------------
# The real file must work with the hook too (same parser rules as dnsmasq_conf).
if [ "$(run_hook "$ROOT/docker/allowed-domains.txt" "https://developer.garmin.com/x")" = 0 ] \
   && [ "$(run_hook "$ROOT/docker/allowed-domains.txt" "https://example.com/")" = 2 ]; then
  echo "  ok: test_hook_matches_shipped_allowlist"
else
  fail "test_hook_matches_shipped_allowlist"
fi

if [ "$failures" -eq 0 ]; then
  echo "All guard-webfetch-allowlist tests passed"
  exit 0
fi
echo "$failures guard-webfetch-allowlist test(s) failed" >&2
exit 1
